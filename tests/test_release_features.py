import json
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from freshctx import FreshnessBlocked, FreshnessState, MemoryStore, guard, observe, reasoning, register_adapter
from freshctx.adapters import MCPAdapter, PostgresAdapter
from freshctx.model import ReasoningNode
from freshctx.redaction import REDACTED, redact


class CoreReleaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name); self.audit = self.root / "audit.jsonl"; self.store = MemoryStore()
        self.source = self.root / "source.txt"; self.source.write_text("one")
    def tearDown(self): self.tmp.cleanup()

    def token(self):
        with guard(store=self.store, audit_path=self.audit) as ctx:
            token = observe(self.source); ctx.protect(depends_on=[token])
        return token

    def test_protected_action_is_not_called_when_stale(self):
        token = self.token(); self.source.write_text("two"); calls = []
        with self.assertRaises(FreshnessBlocked):
            with guard(store=self.store, audit_path=self.audit) as ctx:
                ctx.run(lambda: calls.append("called"), depends_on=[token])
        self.assertEqual(calls, [])

    def test_protected_action_runs_when_current(self):
        token = self.token(); calls = []
        with guard(store=self.store, audit_path=self.audit) as ctx:
            value = ctx.run(lambda x: calls.append(x) or "ok", "called", depends_on=[token])
        self.assertEqual(value, "ok"); self.assertEqual(calls, ["called"])

    def test_cycle_and_missing_dependency_are_unverifiable(self):
        a = ReasoningNode("a", ("b",), "a", id="a"); b = ReasoningNode("b", ("a",), "b", id="b")
        self.store.put_reasoning(a); self.store.put_reasoning(b)
        with guard(policy="allow", store=self.store, audit_path=self.audit) as ctx:
            cycle = ctx.check("a"); missing = ctx.check("missing")
        self.assertEqual(cycle.state, FreshnessState.UNVERIFIABLE); self.assertIn("cycle", cycle.causes)
        self.assertEqual(missing.state, FreshnessState.UNVERIFIABLE); self.assertIn("missing_dependency", missing.causes)

    def test_audit_failure_blocks_before_action(self):
        token = self.token(); calls = []; bad_audit = self.root / "audit-directory"; bad_audit.mkdir()
        with self.assertRaises(FreshnessBlocked) as raised:
            with guard(store=self.store, audit_path=bad_audit) as ctx:
                ctx.run(lambda: calls.append(True), depends_on=[token])
        self.assertEqual(calls, []); self.assertEqual(raised.exception.result.state, FreshnessState.UNVERIFIABLE)
        self.assertIn("audit_failure", raised.exception.result.causes)

    def test_redaction_removes_common_secrets(self):
        value = redact({"Authorization": "Bearer abc123", "password": "secret", "url": "https://u:p@example.test/x?token=abc&ok=1"})
        encoded = json.dumps(value)
        self.assertNotIn("abc123", encoded); self.assertNotIn('"secret"', encoded); self.assertIn(REDACTED, encoded)

    def test_refresh_replaces_stale_subject_once(self):
        token = self.token(); self.source.write_text("two"); calls = []; refreshes = []
        with guard(policy="refresh", store=self.store, audit_path=self.audit) as ctx:
            def refresh(_result):
                refreshes.append(True)
                return observe(self.source)
            ctx.run(lambda: calls.append(True), depends_on=[token], refresh=refresh)
        self.assertEqual(refreshes, [True]); self.assertEqual(calls, [True]); self.assertEqual(ctx.result.state, FreshnessState.CURRENT)

    def test_concurrent_guards_do_not_leak_dependencies(self):
        files = []
        for index in range(8):
            path = self.root / f"{index}.txt"; path.write_text(str(index)); files.append(path)
        def run_one(index):
            with guard(store=self.store, run_id=f"run-{index}", audit_path=self.root / f"audit-{index}.jsonl") as ctx:
                token = observe(files[index]); ctx.protect(depends_on=[token])
            return ctx.run_id, ctx.result.subject_id, token.id, ctx.result.state
        with ThreadPoolExecutor(max_workers=4) as pool: results = list(pool.map(run_one, range(8)))
        self.assertEqual({run for run, *_ in results}, {f"run-{i}" for i in range(8)})
        self.assertTrue(all(subject == token for _, subject, token, _ in results)); self.assertTrue(all(state is FreshnessState.CURRENT for *_, state in results))


class _HTTPHandler(BaseHTTPRequestHandler):
    body = b"one"; etag = '"v1"'; slow = False
    def do_GET(self):
        if type(self).slow: time.sleep(0.15)
        if self.headers.get("If-None-Match") == type(self).etag:
            self.send_response(304); self.send_header("ETag", type(self).etag); self.end_headers(); return
        self.send_response(200); self.send_header("ETag", type(self).etag); self.end_headers(); self.wfile.write(type(self).body)
    def log_message(self, *_args): pass


class HTTPAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), _HTTPHandler); cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True); cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}/resource"
    @classmethod
    def tearDownClass(cls): cls.server.shutdown(); cls.server.server_close(); cls.thread.join()
    def setUp(self):
        _HTTPHandler.body=b"one"; _HTTPHandler.etag='"v1"'; _HTTPHandler.slow=False
        self.tmp=tempfile.TemporaryDirectory(); self.store=MemoryStore(); self.audit=Path(self.tmp.name)/"audit.jsonl"
    def tearDown(self): self.tmp.cleanup()
    def test_conditional_304_is_current_and_changed_etag_is_stale(self):
        with guard(store=self.store,audit_path=self.audit) as ctx:
            token=observe(self.url,adapter="http",timeout=.5);ctx.protect(depends_on=[token])
        with guard(store=self.store,audit_path=self.audit) as ctx: current=ctx.check(token)
        self.assertEqual(current.state,FreshnessState.CURRENT);self.assertEqual(current.adapter_results[0]["evidence"]["status"],304)
        _HTTPHandler.body=b"two";_HTTPHandler.etag='"v2"'
        with guard(policy="allow",store=self.store,audit_path=self.audit) as ctx: stale=ctx.check(token)
        self.assertEqual(stale.state,FreshnessState.STALE_SOURCE)
    def test_timeout_is_unverifiable(self):
        with guard(store=self.store,audit_path=self.audit) as ctx:
            token=observe(self.url,adapter="http",timeout=.05);ctx.protect(depends_on=[token])
        _HTTPHandler.slow=True
        with guard(policy="allow",store=self.store,audit_path=self.audit) as ctx: result=ctx.check(token)
        self.assertEqual(result.state,FreshnessState.UNVERIFIABLE)


class _Cursor:
    description=[("id",),("value",)]
    def __init__(self,state):self.state=state
    def __enter__(self):return self
    def __exit__(self,*_):pass
    def execute(self,query,params=None):self.query=query
    def fetchall(self):return list(self.state["rows"])
class _Connection:
    def __init__(self,state):self.state=state
    def cursor(self):return _Cursor(self.state)
    def close(self):pass


class ExternalAdapterContractTests(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.audit=Path(self.tmp.name)/"audit.jsonl";self.store=MemoryStore()
    def tearDown(self):self.tmp.cleanup()
    def test_postgres_unordered_rows_ignore_order_but_detect_data_change(self):
        state={"rows":[(1,"a"),(2,"b")]}; adapter=PostgresAdapter(connect=lambda _dsn:_Connection(state));register_adapter("postgres-test",adapter)
        adapter.name="postgres-test"
        with guard(store=self.store,audit_path=self.audit) as ctx:
            token=observe("postgres://user:password@db/app",adapter="postgres-test",query="select id,value from items where secret = %s",params=["sensitive-business-value"],ordered=False);ctx.protect(depends_on=[token])
        self.assertNotIn("password",token.locator);self.assertNotIn("sensitive-business-value",repr(token));state["rows"].reverse()
        with guard(store=self.store,audit_path=self.audit) as ctx:self.assertEqual(ctx.check(token).state,FreshnessState.CURRENT)
        state["rows"]=[(1,"changed")]
        with guard(policy="allow",store=self.store,audit_path=self.audit) as ctx:self.assertEqual(ctx.check(token).state,FreshnessState.STALE_SOURCE)
    def test_mcp_safe_reader_detects_change_and_non_idempotent_is_unverifiable(self):
        state={"value":1};adapter=MCPAdapter();adapter.name="mcp-test";register_adapter("mcp-test",adapter)
        with guard(store=self.store,audit_path=self.audit) as ctx:
            token=observe("server-1",adapter="mcp-test",name="read_config",arguments={"token":"secret"},reader=lambda:dict(state),safe=True);ctx.protect(depends_on=[token])
        self.assertEqual(token.metadata["arguments"]["token"],REDACTED);state["value"]=2
        with guard(policy="allow",store=self.store,audit_path=self.audit) as ctx:self.assertEqual(ctx.check(token).state,FreshnessState.STALE_SOURCE)
        with guard(policy="allow",store=self.store,audit_path=self.audit) as ctx:
            unsafe=observe("server-1",adapter="mcp-test",name="send_email",safe=False);result=ctx.check(unsafe)
        self.assertEqual(result.state,FreshnessState.UNVERIFIABLE)


if __name__=="__main__":unittest.main()
