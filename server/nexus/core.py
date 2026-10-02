import base64
import hashlib
import hmac
import ipaddress
import json
import re
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path


class Problem(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def key(value):
    try:
        raw = base64.b64decode(value, validate=True)
        if len(raw) != 32 or raw == bytes(32) or base64.b64encode(raw).decode() != value:
            raise ValueError()
    except (ValueError, TypeError):
        raise Problem(400, "Invalid WireGuard public key") from None
    return value


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def secret(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{32,128}", value):
        raise Problem(400, "Invalid credential format")
    return value


class Store:
    def __init__(self, path, node, clock=time.time):
        self.path, self.node, self.clock = str(path), node, clock
        key(node["public_key"])
        if not re.fullmatch(r"(?:[A-Za-z0-9.-]+|\[[0-9a-fA-F:]+\]):[0-9]{1,5}", node["endpoint"]):
            raise ValueError("Invalid endpoint")
        if not 1 <= int(node["endpoint"].rsplit(":", 1)[1]) <= 65535:
            raise ValueError("Invalid port")
        for addr in node["dns"]:
            ipaddress.ip_address(addr)
        if not node["dns"]:
            raise ValueError("DNS must be explicit")
        self.v4 = ipaddress.ip_network(node.get("ipv4", "10.77.0.0/24"))
        self.v6 = ipaddress.ip_network(node.get("ipv6", "fd77:77:77::/64"))
        if self.v4.version != 4 or self.v6.version != 6 or self.v4.num_addresses < 8:
            raise ValueError("Invalid node subnets")
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.db() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS meta (id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER NOT NULL);
                INSERT OR IGNORE INTO meta VALUES(1,0);
                CREATE TABLE IF NOT EXISTS invites (
                  hash TEXT PRIMARY KEY, expires REAL NOT NULL, device_id TEXT);
                CREATE TABLE IF NOT EXISTS devices (
                  id TEXT PRIMARY KEY, name TEXT NOT NULL, public_key TEXT NOT NULL UNIQUE,
                  secret_hash TEXT NOT NULL, slot INTEGER NOT NULL UNIQUE,
                  desired TEXT NOT NULL CHECK(desired IN ('active','revoked')),
                  applied TEXT NOT NULL CHECK(applied IN ('pending','active','revoked')),
                  created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS audit (
                  id INTEGER PRIMARY KEY AUTOINCREMENT, time REAL NOT NULL,
                  kind TEXT NOT NULL, device_id TEXT);
            """)

    @contextmanager
    def db(self, write=False):
        db = sqlite3.connect(self.path, timeout=15, isolation_level=None)
        db.row_factory = sqlite3.Row
        try:
            if write:
                db.execute("BEGIN IMMEDIATE")
            yield db
            if write:
                db.commit()
        except BaseException:
            if write:
                db.rollback()
            raise
        finally:
            db.close()

    def event(self, db, kind, device_id=None):
        db.execute("INSERT INTO audit(time,kind,device_id) VALUES(?,?,?)", (self.clock(), kind, device_id))

    def invite(self, ttl=600):
        if type(ttl) is not int or not 60 <= ttl <= 3600:
            raise Problem(400, "Invitation lifetime must be 60–3600 seconds")
        token = secrets.token_urlsafe(32)
        with self.db(True) as db:
            db.execute("INSERT INTO invites VALUES(?,?,NULL)", (digest(token), self.clock()+ttl))
            self.event(db, "invite_created")
        return {"token": token, "expires_at": self.clock()+ttl}

    def enroll(self, data):
        if set(data) != {"token", "public_key", "device_secret", "name"}:
            raise Problem(400, "Only token, public_key, device_secret and name are accepted")
        token, public, credential = secret(data["token"]), key(data["public_key"]), secret(data["device_secret"])
        name = data["name"]
        if not isinstance(name, str) or not 1 <= len(name) <= 64 or any(ord(c)<32 for c in name):
            raise Problem(400, "Invalid device name")
        with self.db(True) as db:
            invitation = db.execute("SELECT * FROM invites WHERE hash=?", (digest(token),)).fetchone()
            if not invitation or invitation["expires"] < self.clock():
                raise Problem(403, "Invitation invalid or expired")
            if invitation["device_id"]:
                row = db.execute("SELECT * FROM devices WHERE id=?", (invitation["device_id"],)).fetchone()
                if row["public_key"] != public or not hmac.compare_digest(row["secret_hash"], digest(credential)):
                    raise Problem(409, "Invitation already redeemed")
                return self.public(row)
            used = {r[0] for r in db.execute("SELECT slot FROM devices")}
            # Never recycle a revoked address/key in this beta; avoids stale-profile reuse.
            slot = next((s for s in range(2, min(self.v4.num_addresses-1, 1002)) if s not in used), None)
            if slot is None:
                raise Problem(409, "Node capacity reached")
            device_id = secrets.token_hex(16)
            try:
                db.execute("INSERT INTO devices VALUES(?,?,?,?,?,'active','pending',?)",
                           (device_id, name, public, digest(credential), slot, self.clock()))
            except sqlite3.IntegrityError:
                raise Problem(409, "Public key already enrolled") from None
            db.execute("UPDATE invites SET device_id=? WHERE hash=?", (device_id, digest(token)))
            db.execute("UPDATE meta SET revision=revision+1")
            self.event(db, "device_enrolled", device_id)
            return self.public(db.execute("SELECT * FROM devices WHERE id=?", (device_id,)).fetchone())

    def public(self, row):
        result = {k: row[k] for k in ("id", "name", "desired", "applied", "created")}
        if row["desired"] == "active":
            result["profile"] = {
                "addresses": [f"{self.v4[row['slot']]}/32", f"{self.v6[row['slot']]}/128"],
                "server_public_key": self.node["public_key"], "endpoint": self.node["endpoint"],
                "dns": self.node["dns"], "allowed_ips": ["0.0.0.0/0", "::/0"], "keepalive": 25}
        return result

    def device(self, device_id, credential):
        with self.db() as db:
            row = db.execute("SELECT * FROM devices WHERE id=?", (device_id,)).fetchone()
            if not row or not isinstance(credential, str) or not hmac.compare_digest(row["secret_hash"], digest(credential)):
                raise Problem(401, "Unauthorized")
            return self.public(row)

    def revoke(self, device_id):
        with self.db(True) as db:
            row = db.execute("SELECT * FROM devices WHERE id=?", (device_id,)).fetchone()
            if not row:
                raise Problem(404, "Device not found")
            if row["desired"] != "revoked":
                db.execute("UPDATE devices SET desired='revoked',applied='pending' WHERE id=?", (device_id,))
                db.execute("UPDATE meta SET revision=revision+1")
                self.event(db, "revocation_requested", device_id)
            return self.public(db.execute("SELECT * FROM devices WHERE id=?", (device_id,)).fetchone())

    def snapshot(self):
        with self.db(True) as db:
            revision = db.execute("SELECT revision FROM meta").fetchone()[0]
            peers = [{"public_key": r["public_key"], "ipv4": str(self.v4[r["slot"]]),
                      "ipv6": str(self.v6[r["slot"]])}
                     for r in db.execute("SELECT * FROM devices WHERE desired='active' ORDER BY slot")]
            return {"revision": revision, "peers": peers}

    def acknowledge(self, revision):
        with self.db(True) as db:
            if db.execute("SELECT revision FROM meta").fetchone()[0] != revision:
                return False
            for row in db.execute("SELECT id,desired FROM devices WHERE applied!=desired").fetchall():
                self.event(db, "peer_applied" if row["desired"] == "active" else "peer_removed", row["id"])
            db.execute("UPDATE devices SET applied=desired")
            return True

    def devices(self):
        with self.db() as db:
            return [self.public(r) for r in db.execute("SELECT * FROM devices ORDER BY created DESC")]

    def audit(self):
        with self.db() as db:
            return [dict(r) for r in db.execute("SELECT * FROM audit ORDER BY id DESC LIMIT 200")]
