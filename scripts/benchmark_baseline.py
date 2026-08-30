"""Reproducible FreshCtx baseline benchmarks; does not optimize runtime behavior."""

from __future__ import annotations

import argparse
import json
import platform
import statistics
import subprocess
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from freshctx import MemoryStore, guard, observe, reasoning, register_adapter
from freshctx.adapters import MCPAdapter
from freshctx.model import AdapterResult, ObservationToken


class StableAdapter:
    name = "benchmark-stable"

    def observe(self, locator, **_options):
        return ObservationToken(self.name, str(locator), str(locator))

    def validate(self, token):
        return AdapterResult("equivalent", evidence={"benchmark": True})


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("ETag", '"baseline"')
        self.end_headers()
        self.wfile.write(b"baseline")

    def log_message(self, *_args):
        pass


def stats(samples):
    ordered = sorted(samples)
    return {
        "iterations": len(samples),
        "median_ms": statistics.median(samples),
        "mean_ms": statistics.mean(samples),
        "min_ms": ordered[0],
        "p95_ms": ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))],
        "max_ms": ordered[-1],
    }


def measure(callback, iterations, warmups=2):
    for _ in range(warmups):
        callback()
    samples = []
    for _ in range(iterations):
        start = time.perf_counter_ns()
        callback()
        samples.append((time.perf_counter_ns() - start) / 1_000_000)
    return stats(samples)


def check(store, audit, subject):
    with guard(policy="allow", store=store, audit_path=audit) as ctx:
        return ctx.check(subject)


def internal_graphs(root, iterations, depth, width):
    register_adapter(StableAdapter.name, StableAdapter())
    audit = root / "internal.jsonl"
    results = {}

    deep_store = MemoryStore()
    with guard(store=deep_store, audit_path=audit):
        leaf = observe("deep-leaf", adapter=StableAdapter.name)
        subject = leaf
        for index in range(depth):
            with reasoning(f"deep-{index}", [subject]) as node:
                pass
            subject = node
    results["deep_graph"] = {"topology": {"depth": depth, "dependency_count": 1}, **measure(lambda: check(deep_store, audit, subject), iterations)}

    wide_store = MemoryStore()
    with guard(store=wide_store, audit_path=audit):
        leaves = [observe(f"wide-{index}", adapter=StableAdapter.name) for index in range(width)]
        with reasoning("wide-root", leaves) as wide_subject:
            pass
    results["wide_graph"] = {"topology": {"depth": 1, "dependency_count": width}, **measure(lambda: check(wide_store, audit, wide_subject), iterations)}

    shared_store = MemoryStore()
    with guard(store=shared_store, audit_path=audit):
        shared = observe("shared", adapter=StableAdapter.name)
        paths = []
        for index in range(width):
            with reasoning(f"shared-path-{index}", [shared]) as node:
                pass
            paths.append(node)
        with reasoning("shared-root", paths) as shared_subject:
            pass
    results["shared_dependency_paths"] = {"topology": {"reasoning_paths": width, "unique_dependency_count": 1}, **measure(lambda: check(shared_store, audit, shared_subject), iterations)}
    return results


def adapter_benchmarks(root, iterations):
    results = {}
    audit = root / "adapters.jsonl"

    source = root / "filesystem.txt"
    source.write_bytes(b"x" * 4096)
    fs_store = MemoryStore()
    with guard(store=fs_store, audit_path=audit):
        fs_token = observe(source)
    results["filesystem_validation"] = {"config": {"bytes": 4096}, **measure(lambda: check(fs_store, audit, fs_token), iterations)}

    repo = root / "git-repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "benchmark@example.invalid"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "FreshCtx Benchmark"], check=True)
    (repo / "evidence.txt").write_text("baseline\n")
    subprocess.run(["git", "-C", str(repo), "add", "evidence.txt"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "baseline"], check=True)
    git_store = MemoryStore()
    with guard(store=git_store, audit_path=audit):
        git_token = observe(repo, adapter="git", scope="path", path="evidence.txt")
    results["git_validation"] = {"config": {"scope": "path"}, **measure(lambda: check(git_store, audit, git_token), iterations)}

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        http_store = MemoryStore()
        with guard(store=http_store, audit_path=audit):
            http_token = observe(f"http://127.0.0.1:{server.server_port}/evidence", adapter="http")
        results["http_validation_local"] = {"config": {"transport": "loopback", "external_latency_included": True}, **measure(lambda: check(http_store, audit, http_token), iterations)}
    finally:
        server.shutdown(); server.server_close(); thread.join()

    value = {"version": 1}
    mcp = MCPAdapter(); mcp.name = "benchmark-mcp"; register_adapter(mcp.name, mcp)
    mcp_store = MemoryStore()
    with guard(store=mcp_store, audit_path=audit):
        mcp_token = observe("simulated-local-reader", adapter=mcp.name, name="read_evidence", reader=lambda: value, safe=True)
    results["mcp_reader_validation"] = {"config": {"reader": "in_process", "transport_latency": False}, **measure(lambda: check(mcp_store, audit, mcp_token), iterations)}
    results["postgres_validation"] = {"status": "not_run", "limitation": "No disposable Postgres service was available; results are not fabricated."}
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=30)
    parser.add_argument("--depth", type=int, default=50)
    parser.add_argument("--width", type=int, default=100)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="freshctx-benchmark-") as directory:
        root = Path(directory)
        payload = {
            "method": "time.perf_counter_ns; two warmups excluded; each check writes JSONL audit evidence",
            "warm_cold": "warm process and adapter state; filesystem cache not flushed",
            "environment": {"python": platform.python_version(), "platform": platform.platform(), "machine": platform.machine()},
            "repository_sha": subprocess.run(["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip(),
            "parameters": {"iterations": args.iterations, "depth": args.depth, "width": args.width},
            "internal_processing": internal_graphs(root, args.iterations, args.depth, args.width),
            "adapter_validation": adapter_benchmarks(root, args.iterations),
            "limitations": ["Single machine and process; not a capacity claim.", "HTTP uses loopback and includes request latency.", "MCP exercises the current safe-reader contract without a transport.", "Postgres is omitted without real infrastructure."],
        }
    encoded = json.dumps(payload, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")


if __name__ == "__main__":
    main()
