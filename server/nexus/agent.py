"""Local Unix-socket peer reconciliation; no arbitrary command or file APIs."""
import argparse
import grp
import ipaddress
import json
import os
import re
import socketserver
import subprocess
import tempfile
import threading
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from .core import Problem, key


def atomic(path, text):
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".nexus-")
    try:
        with os.fdopen(fd, "w") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class Engine:
    def __init__(self, directory, interface="nexus0", runner=None):
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,15}", interface):
            raise ValueError("Invalid interface")
        self.directory, self.interface = Path(directory), interface
        self.runner = runner or self.run
        self.lock = threading.Lock()
        self.settings = json.loads((self.directory/"node.json").read_text())
        self.v4 = ipaddress.ip_network(self.settings["ipv4"])
        self.v6 = ipaddress.ip_network(self.settings["ipv6"])
        self.private_key = key((self.directory/"private.key").read_text().strip())
        self.port = int(self.settings["port"])
        if not 1 <= self.port <= 65535:
            raise ValueError("Invalid port")
        self.persistent = self.directory/f"{interface}.conf"
        if not self.persistent.exists():
            raise ValueError("Bootstrap the interface before starting the agent")

    @staticmethod
    def run(argv):
        return subprocess.run(argv, check=True, capture_output=True, text=True, timeout=15).stdout

    def validate(self, data):
        if set(data) != {"revision", "peers"} or type(data["revision"]) is not int or data["revision"] < 0:
            raise Problem(400, "Invalid reconciliation request")
        if not isinstance(data["peers"], list) or len(data["peers"]) > 1000:
            raise Problem(400, "Too many peers")
        seen = set()
        for peer in data["peers"]:
            if not isinstance(peer, dict) or set(peer) != {"public_key", "ipv4", "ipv6"}:
                raise Problem(400, "Invalid peer")
            key(peer["public_key"])
            try:
                addresses = [ipaddress.ip_address(peer["ipv4"]), ipaddress.ip_address(peer["ipv6"])]
            except ValueError:
                raise Problem(400, "Invalid peer address") from None
            for addr, network in zip(addresses, [self.v4, self.v6]):
                if addr not in network or int(addr)-int(network.network_address) < 2 or addr == network.broadcast_address:
                    raise Problem(400, "Peer address outside allocation range")
                if str(addr) in seen:
                    raise Problem(400, "Duplicate address")
                seen.add(str(addr))
            if peer["public_key"] in seen:
                raise Problem(400, "Duplicate peer key")
            seen.add(peer["public_key"])

    def render(self, peers, persistent=False):
        text = f"[Interface]\nPrivateKey = {self.private_key}\nListenPort = {self.port}\n"
        if persistent:
            text += f"Address = {self.v4[1]}/{self.v4.prefixlen}, {self.v6[1]}/{self.v6.prefixlen}\n"
        for peer in peers:
            text += f"\n[Peer]\nPublicKey = {peer['public_key']}\nAllowedIPs = {peer['ipv4']}/32, {peer['ipv6']}/128\n"
        return text

    def reconcile(self, data):
        self.validate(data)
        with self.lock:
            live = self.directory/"candidate.live"
            rollback = self.directory/"rollback.live"
            original = self.persistent.read_text()
            atomic(rollback, self.runner(["/usr/bin/wg", "showconf", self.interface]))
            atomic(live, self.render(data["peers"]))
            try:
                self.runner(["/usr/bin/wg", "syncconf", self.interface, str(live)])
                atomic(self.persistent, self.render(data["peers"], persistent=True))
            except Exception:
                # Both persistent and kernel state must revert before reporting failure.
                atomic(self.persistent, original)
                self.runner(["/usr/bin/wg", "syncconf", self.interface, str(rollback)])
                raise
            finally:
                live.unlink(missing_ok=True)
                rollback.unlink(missing_ok=True)
            return {"revision": data["revision"], "public_key": self.runner(
                ["/usr/bin/wg", "show", self.interface, "public-key"]).strip()}


class UnixServer(socketserver.UnixStreamServer):
    pass


def serve(engine, path, group):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass  # Requests can contain enrollment/management secrets; do not log them.

        def do_POST(self):
            self.connection.settimeout(10)
            status, result = 200, {}
            try:
                if self.path != "/sync":
                    raise Problem(404, "Not found")
                length = int(self.headers.get("Content-Length", "0"))
                if not 1 <= length <= 262144:
                    raise Problem(413, "Request too large")
                result = engine.reconcile(json.loads(self.rfile.read(length)))
            except Problem as failure:
                status, result = failure.status, {"error": str(failure)}
            except (ValueError, TypeError, KeyError):
                status, result = 400, {"error": "Invalid request"}
            except Exception:
                status, result = 503, {"error": "Node update failed"}
            payload = json.dumps(result).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)
    with UnixServer(str(path), Handler) as server:
        os.chown(path, 0, grp.getgrnam(group).gr_gid)
        os.chmod(path, 0o660)
        server.serve_forever()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", default="/etc/nexus")
    parser.add_argument("--socket", default="/run/nexus/agent.sock")
    parser.add_argument("--group", default="nexus")
    args = parser.parse_args()
    os.umask(0o077)
    serve(Engine(args.directory), args.socket, args.group)
