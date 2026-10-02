import collections
import hmac
import http.client
import json
import os
import socket
import threading
import time
from contextlib import closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
from .core import Store, Problem, digest


class AgentConnection(http.client.HTTPConnection):
    def __init__(self, path):
        super().__init__("localhost", timeout=20)
        self.path = path

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self.path)


class Reconciler:
    def __init__(self, store, agent_path):
        self.store, self.path = store, agent_path
        self.lock = threading.Lock()
        self.last_success = 0

    def sync(self):
        with self.lock:
            desired = self.store.snapshot()
            with closing(AgentConnection(self.path)) as conn:
                conn.request("POST", "/sync", json.dumps(desired), {"Content-Type": "application/json"})
                response = conn.getresponse()
                result = json.loads(response.read(262144))
                if response.status != 200 or result.get("revision") != desired["revision"] or result.get("public_key") != self.store.node["public_key"]:
                    raise RuntimeError("Agent did not acknowledge expected configuration")
            if self.store.acknowledge(desired["revision"]):
                self.last_success = time.time()

    def loop(self):
        while True:
            try:
                self.sync()
            except Exception:
                pass  # /health reports staleness; credentials/configs never enter logs.
            time.sleep(5)


class Limiter:
    def __init__(self):
        self.lock = threading.Lock()
        self.requests = collections.deque()

    def allow(self):
        # Global public-endpoint limit works behind a proxy without trusting forwarded IPs.
        now = time.monotonic()
        with self.lock:
            while self.requests and self.requests[0] < now-60:
                self.requests.popleft()
            if len(self.requests) >= 120:
                return False
            self.requests.append(now)
            return True


class BoundedServer(ThreadingHTTPServer):
    daemon_threads = True
    def __init__(self, *args, **kwargs):
        self.slots = threading.BoundedSemaphore(64)
        super().__init__(*args, **kwargs)

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()


def make_server(store, admin_token, reconciler=None, address=("127.0.0.1", 8787)):
    if len(admin_token) < 32:
        raise ValueError("Use an admin token of at least 32 characters")
    admin_hash = digest(admin_token)
    limiter = Limiter()
    static = Path(__file__).parent/"static"

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            self.dispatch()

        def do_POST(self):
            self.dispatch()

        def bearer(self):
            value = self.headers.get("Authorization", "")
            return value[7:] if value.startswith("Bearer ") else ""

        def require_admin(self):
            if not hmac.compare_digest(digest(self.bearer()), admin_hash):
                raise Problem(401, "Unauthorized")

        def body(self):
            if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                raise Problem(415, "Use application/json")
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 1 <= length <= 16384:
                    raise Problem(413, "Request too large")
                value = json.loads(self.rfile.read(length))
                if not isinstance(value, dict):
                    raise ValueError()
                return value
            except (ValueError, TypeError):
                raise Problem(400, "Invalid JSON") from None

        def send(self, status, value, content_type="application/json"):
            payload = value if isinstance(value, bytes) else json.dumps(value).encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()
            self.wfile.write(payload)

        def dispatch(self):
            self.connection.settimeout(10)
            try:
                path = urlparse(self.path).path
                method = self.command
                if method == "GET" and path in ("/", "/app.js", "/style.css"):
                    name, content_type = {"/": ("index.html", "text/html; charset=utf-8"),
                        "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                        "/style.css": ("style.css", "text/css; charset=utf-8")}[path]
                    return self.send(200, (static/name).read_bytes(), content_type)
                if method == "GET" and path == "/health":
                    return self.send(200, {"controller": "up", "node_synced_recently": bool(
                        reconciler and time.time()-reconciler.last_success < 20)})
                if path.startswith("/v1/admin/"):
                    self.require_admin()
                else:
                    if not limiter.allow():
                        raise Problem(429, "Too many requests; retry in one minute")
                if method == "POST" and path == "/v1/admin/invitations":
                    body = self.body()
                    if set(body)-{"ttl"}:
                        raise Problem(400, "Unknown invitation field")
                    return self.send(201, store.invite(body.get("ttl", 600)))
                if method == "GET" and path == "/v1/admin/devices":
                    return self.send(200, {"devices": store.devices()})
                if method == "GET" and path == "/v1/admin/audit":
                    return self.send(200, {"events": store.audit()})
                if method == "POST" and path.startswith("/v1/admin/devices/") and path.endswith("/revoke"):
                    device_id = path.split("/")[4]
                    return self.send(202, store.revoke(device_id))
                if method == "POST" and path == "/v1/enroll":
                    return self.send(202, store.enroll(self.body()))
                if method == "GET" and path.startswith("/v1/devices/"):
                    return self.send(200, store.device(path.split("/")[-1], self.bearer()))
                raise Problem(404, "Not found")
            except Problem as problem:
                self.send(problem.status, {"error": str(problem)})
            except (KeyError, TypeError, ValueError):
                self.send(400, {"error": "Invalid request"})
            except Exception:
                self.send(503, {"error": "Service temporarily unavailable"})
    return BoundedServer(address, Handler)


if __name__ == "__main__":
    os.umask(0o077)
    settings = json.loads(Path(os.environ.get("NEXUS_NODE", "/etc/nexus/public-node.json")).read_text())
    store = Store(os.environ.get("NEXUS_DB", "/var/lib/nexus/nexus.db"), settings)
    reconciler = Reconciler(store, os.environ.get("NEXUS_AGENT", "/run/nexus/agent.sock"))
    threading.Thread(target=reconciler.loop, daemon=True).start()
    make_server(store, os.environ["NEXUS_ADMIN_TOKEN"], reconciler).serve_forever()
