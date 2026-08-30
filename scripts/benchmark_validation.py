"""Reproducible synchronous/concurrent validation benchmark.

This is a measurement harness, not a production-performance claim.
"""

import argparse
import json
import statistics
import time

from freshctx import MemoryStore, guard, observe, reasoning, register_adapter
from freshctx.model import AdapterResult, ObservationToken


class DelayedAdapter:
    name = "benchmark-delay"
    thread_safe = True

    def __init__(self, delay_ms):
        self.delay = delay_ms / 1000
        self.calls = 0

    def observe(self, locator, **_options):
        return ObservationToken(self.name, str(locator), str(locator))

    def validate(self, token):
        self.calls += 1
        time.sleep(self.delay)
        return AdapterResult("equivalent", evidence={"locator": token.locator})


def percentile(values, fraction):
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round((len(ordered) - 1) * fraction))]


def run(width, workers, delay_ms, iterations, shape):
    adapter = DelayedAdapter(delay_ms)
    register_adapter(adapter.name, adapter)
    store = MemoryStore()
    with guard(store=store, audit_path="/dev/null"):
        tokens = [observe(f"dependency-{index}", adapter=adapter.name) for index in range(width)]
        if shape == "wide":
            with reasoning("wide-benchmark", tokens) as node:
                pass
        else:
            current = tokens[0]
            for index, token in enumerate(tokens[1:], start=1):
                with reasoning(f"deep-benchmark-{index}", [current, token]) as link:
                    pass
                current = link
            node = current
    timings = []
    for _ in range(iterations):
        started = time.perf_counter()
        with guard(store=store, audit_path="/dev/null", validation_workers=workers, max_graph_depth=max(100, width * 2)) as ctx:
            result = ctx.check(node)
        timings.append((time.perf_counter() - started) * 1000)
    return {
        "width": width,
        "shape": shape,
        "workers": workers,
        "source_delay_ms": delay_ms,
        "iterations": iterations,
        "adapter_calls": adapter.calls,
        "state": result.state.value,
        "mean_ms": round(statistics.mean(timings), 3),
        "p50_ms": round(percentile(timings, 0.50), 3),
        "p95_ms": round(percentile(timings, 0.95), 3),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--width", type=int, default=8)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--delay-ms", type=float, default=25)
    parser.add_argument("--iterations", type=int, default=20)
    args = parser.parse_args()
    results = {}
    for shape in ("wide", "deep"):
        results[f"{shape}_sequential"] = run(args.width, 1, args.delay_ms, args.iterations, shape)
        results[f"{shape}_concurrent"] = run(args.width, args.workers, args.delay_ms, args.iterations, shape)
    print(json.dumps(results, indent=2))
