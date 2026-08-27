import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory

from freshctx import FreshnessStatus, MemoryStore, guard, observe


class ConfigAPI(BaseHTTPRequestHandler):
    body = b'{"region":"us-east-1"}'
    etag = '"config-v1"'

    def do_GET(self):
        self.send_response(200)
        self.send_header("ETag", type(self).etag)
        self.end_headers()
        self.wfile.write(type(self).body)

    def log_message(self, *_args):
        pass


server = ThreadingHTTPServer(("127.0.0.1", 0), ConfigAPI)
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()

try:
    with TemporaryDirectory() as directory:
        store = MemoryStore()
        audit = Path(directory) / "audit.jsonl"
        url = f"http://127.0.0.1:{server.server_port}/config"
        with guard(store=store, audit_path=audit):
            token = observe(url, adapter="http", timeout=1.0)
        ConfigAPI.body = b'{"region":"eu-west-1"}'
        ConfigAPI.etag = '"config-v2"'
        with guard(policy="allow", store=store, audit_path=audit) as ctx:
            result = ctx.check(token)
        assert result.state is FreshnessStatus.STALE_SOURCE
        print(result.state.value)
finally:
    server.shutdown()
    server.server_close()
    thread.join()
