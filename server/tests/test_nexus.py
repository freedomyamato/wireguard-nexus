import base64
import concurrent.futures
import http.client
import json
import tempfile
import threading
import unittest
from contextlib import closing
import socketserver
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest.mock import patch
from pathlib import Path
from nexus.core import Store, Problem
from nexus.agent import Engine
from nexus.api import make_server, Reconciler


def pub(n):
    return base64.b64encode(bytes([n])*32).decode()


NODE = {"public_key":pub(7),"endpoint":"vpn.example.com:51821","dns":["1.1.1.1"],
        "ipv4":"10.77.0.0/24","ipv6":"fd77:77:77::/64"}


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.now = 1000
        self.store = Store(Path(self.temp.name)/"db.sqlite", NODE, lambda:self.now)
    def tearDown(self):
        self.temp.cleanup()
    def data(self, token, n=1):
        return {"token":token,"public_key":pub(n),"device_secret":"x"*32,"name":"Test phone"}
    def test_retry_and_single_use(self):
        token=self.store.invite()["token"]
        first=self.store.enroll(self.data(token))
        self.assertEqual(first,self.store.enroll(self.data(token)))
        with self.assertRaises(Problem) as error:self.store.enroll(self.data(token,2))
        self.assertEqual(error.exception.status,409)
        self.assertEqual(len(self.store.devices()),1)
    def test_expired_invite(self):
        token=self.store.invite()["token"];self.now+=601
        with self.assertRaises(Problem):self.store.enroll(self.data(token))
        self.assertEqual(self.store.devices(),[])
    def test_atomic_concurrent_redemption(self):
        token=self.store.invite()["token"]
        def redeem(n):
            try:return self.store.enroll(self.data(token,n))["id"]
            except Problem:return None
        with concurrent.futures.ThreadPoolExecutor(8) as pool:
            results=list(pool.map(redeem,range(1,9)))
        self.assertEqual(sum(x is not None for x in results),1)
    def test_stale_ack_does_not_confirm_revocation(self):
        first=self.store.enroll(self.data(self.store.invite()["token"]))
        snapshot=self.store.snapshot()
        self.store.revoke(first["id"])
        self.assertFalse(self.store.acknowledge(snapshot["revision"]))
        device=self.store.device(first["id"],"x"*32)
        self.assertEqual(device["applied"],"pending")
        self.assertNotIn("profile",device)
        desired=self.store.snapshot();self.assertEqual(desired["peers"],[])
        self.assertTrue(self.store.acknowledge(desired["revision"]))
        self.assertEqual(self.store.devices()[0]["applied"],"revoked")
    def test_device_credentials_and_no_private_key_fields(self):
        token=self.store.invite()["token"]
        data=self.data(token);data["private_key"]=pub(3)
        with self.assertRaises(Problem):self.store.enroll(data)
        device=self.store.enroll(self.data(token))
        with self.assertRaises(Problem):self.store.device(device["id"],"wrong")
        response=json.dumps(self.store.devices()+self.store.audit())
        for forbidden in [token,"x"*32,"secret_hash","private_key"]:self.assertNotIn(forbidden,response)


class AgentTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)
        (self.path/"node.json").write_text(json.dumps({**NODE,"port":51821}))
        (self.path/"private.key").write_text(pub(5))
        (self.path/"nexus0.conf").write_text("original persistent\n")
        self.calls=[]
        def run(argv):
            self.calls.append(argv)
            if argv[1]=="showconf":return "original live\n"
            if argv[1]=="show":return pub(7)
            return ""
        self.engine=Engine(self.path,runner=run)
        self.desired={"revision":1,"peers":[{"public_key":pub(1),"ipv4":"10.77.0.2","ipv6":"fd77:77:77::2"}]}
    def tearDown(self):self.temp.cleanup()
    def test_apply_and_persist(self):
        self.assertEqual(self.engine.reconcile(self.desired)["revision"],1)
        config=(self.path/"nexus0.conf").read_text()
        self.assertIn("AllowedIPs = 10.77.0.2/32, fd77:77:77::2/128",config)
        self.assertEqual((self.path/"nexus0.conf").stat().st_mode&0o777,0o600)
    def test_rollback_on_live_failure(self):
        old=self.engine.runner
        def run(argv):
            if argv[1]=="syncconf" and argv[-1].endswith("candidate.live"):raise RuntimeError("injected")
            return old(argv)
        self.engine.runner=run
        with self.assertRaises(RuntimeError):self.engine.reconcile(self.desired)
        self.assertEqual((self.path/"nexus0.conf").read_text(),"original persistent\n")
        self.assertTrue(any(c[-1].endswith("rollback.live") for c in self.calls))
    def test_reject_arbitrary_routes_before_commands(self):
        self.desired["peers"][0]["ipv4"]="169.254.169.254"
        with self.assertRaises(Problem):self.engine.reconcile(self.desired)
        self.assertEqual(self.calls,[])
    def test_reject_command_fields_and_duplicate_addresses(self):
        self.desired["command"]="echo unsafe"
        with self.assertRaises(Problem):self.engine.reconcile(self.desired)
        del self.desired["command"]
        self.desired["peers"].append({**self.desired["peers"][0],"public_key":pub(2)})
        with self.assertRaises(Problem):self.engine.reconcile(self.desired)


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.store=Store(Path(self.temp.name)/"db",NODE)
        self.server=make_server(self.store,"a"*40,address=("127.0.0.1",0))
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.temp.cleanup()
    def request(self,path,method="GET",data=None,token=""):
        with closing(http.client.HTTPConnection(*self.server.server_address)) as conn:
            conn.request(method,path,json.dumps(data) if data is not None else None,
                {"Content-Type":"application/json","Authorization":"Bearer "+token})
            response=conn.getresponse();payload=response.read()
            self.assertEqual(response.getheader("Cache-Control"),"no-store")
            return response.status,json.loads(payload)
    def test_real_http_enrollment_and_owner_check(self):
        self.assertEqual(self.request("/v1/admin/devices")[0],401)
        status,invite=self.request("/v1/admin/invitations","POST",{},"a"*40)
        self.assertEqual(status,201)
        status,device=self.request("/v1/enroll","POST",{"token":invite["token"],"public_key":pub(1),"device_secret":"b"*32,"name":"Phone"})
        self.assertEqual(status,202)
        self.assertEqual(self.request("/v1/devices/"+device["id"],token="wrong")[0],401)
        self.assertEqual(self.request("/v1/devices/"+device["id"],token="b"*32)[0],200)
        status,revoked=self.request("/v1/admin/devices/"+device["id"]+"/revoke","POST",{},"a"*40)
        self.assertEqual(status,202);self.assertEqual(revoked["desired"],"revoked")
    def test_malformed_json(self):
        self.assertEqual(self.request("/v1/enroll","POST",[])[0],400)


class ReconciliationTests(unittest.TestCase):
    def test_unix_node_acknowledges_real_http_enrollment_and_revocation(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)
            store=Store(path/"db",NODE)
            device=store.enroll({"token":store.invite()["token"],"public_key":pub(1),
                                "device_secret":"x"*32,"name":"Phone"})
            observed=[]
            class Handler(BaseHTTPRequestHandler):
                def log_message(self,*_):pass
                def do_POST(self):
                    data=json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                    observed.append(data)
                    payload=json.dumps({"revision":data["revision"],"public_key":pub(7)}).encode()
                    self.send_response(200);self.send_header("Content-Length",str(len(payload)))
                    self.end_headers();self.wfile.write(payload)
            try:
                server=socketserver.UnixStreamServer(str(path/"agent.sock"),Handler)
            except PermissionError:
                self.skipTest("Runtime denies Unix sockets; run this test on a Linux host or GitHub Actions")
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                reconciler=Reconciler(store,str(path/"agent.sock"))
                reconciler.sync()
                self.assertEqual(store.devices()[0]["applied"],"active")
                self.assertGreater(reconciler.last_success,0)
                store.revoke(device["id"]);reconciler.sync()
                self.assertEqual(observed[-1]["peers"],[])
                self.assertEqual(store.devices()[0]["applied"],"revoked")
            finally:
                server.shutdown();server.server_close();thread.join()

    def test_missing_agent_leaves_peer_pending(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory);store=Store(path/"db",NODE)
            store.enroll({"token":store.invite()["token"],"public_key":pub(1),
                          "device_secret":"x"*32,"name":"Phone"})
            reconciler=Reconciler(store,str(path/"missing.sock"))
            with self.assertRaises(OSError):reconciler.sync()
            self.assertEqual(store.devices()[0]["applied"],"pending")
            self.assertEqual(reconciler.last_success,0)

    def test_reconciliation_wire_protocol_and_key_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            store=Store(Path(directory)/"db",NODE)
            device=store.enroll({"token":store.invite()["token"],"public_key":pub(1),
                                "device_secret":"x"*32,"name":"Phone"})
            observed=[]
            class Handler(BaseHTTPRequestHandler):
                public_key=pub(8)
                def log_message(self,*_):pass
                def do_POST(self):
                    data=json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                    observed.append(data)
                    payload=json.dumps({"revision":data["revision"],"public_key":self.public_key}).encode()
                    self.send_response(200);self.send_header("Content-Length",str(len(payload)))
                    self.end_headers();self.wfile.write(payload)
            server=HTTPServer(("127.0.0.1",0),Handler)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                # Actual HTTP wire protocol; transport replaced because this runtime bans AF_UNIX.
                with patch("nexus.api.AgentConnection",lambda _:http.client.HTTPConnection(*server.server_address)):
                    reconciler=Reconciler(store,"test transport")
                    with self.assertRaises(RuntimeError):reconciler.sync()
                    self.assertEqual(store.devices()[0]["applied"],"pending")
                    Handler.public_key=pub(7);reconciler.sync()
                    self.assertEqual(store.devices()[0]["applied"],"active")
                    store.revoke(device["id"]);reconciler.sync()
                    self.assertEqual(observed[-1]["peers"],[])
                    self.assertEqual(store.devices()[0]["applied"],"revoked")
            finally:
                server.shutdown();server.server_close();thread.join()


if __name__=="__main__":unittest.main()
