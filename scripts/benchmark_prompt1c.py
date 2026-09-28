"""Local comparison harness; measures evidence checks, never external actions."""
from __future__ import annotations
import argparse
import json
import statistics
import tempfile
import time
from pathlib import Path
import freshctx
from freshctx import MemoryStore, SQLiteStore, guard, observe, reasoning, register_adapter
from freshctx.model import AdapterResult, ObservationToken

class Source:
    name = 'prompt1c_benchmark'
    thread_safe = True
    def __init__(self):
        self.calls = 0
        self.transient = False
    def observe(self, locator, **_options):
        return ObservationToken(self.name, str(locator), 'benchmark-version-1')
    def validate(self, _token):
        self.calls += 1
        if self.transient and self.calls % 2:
            return AdapterResult('indeterminate', error_code='benchmark_timeout', retryable=True)
        return AdapterResult('equivalent')

def summary(values):
    values = sorted(values)
    return {'samples': len(values), 'median_ms': statistics.median(values),
            'p95_ms': values[min(len(values)-1, int(len(values)*.95))],
            'min_ms': values[0], 'max_ms': values[-1]}

def measure(root, name, samples, *, persisted=False, lineage=False, retry=False, backoff_ms=0):
    store = SQLiteStore(root / (name+'.sqlite')) if persisted else MemoryStore()
    source = Source()
    register_adapter(source.name, source)
    audit = root / (name+'.jsonl')
    with guard(store=store, audit_path=audit):
        token = observe('resource:benchmark', adapter=source.name)
        with reasoning('tool_output', [token], metadata={'tool_invocation_id':'A','output_hash':'a'}) as a:
            pass
        with reasoning('tool_output', [a], metadata={'tool_invocation_id':'B','output_hash':'b'}) as b:
            pass
    options = {}
    kwargs = {}
    if lineage:
        options['protected_parameters'] = {'recipient': freshctx.ProtectedParameter((b.id,), freshctx.parameter_digest('recipient-1'))}
    if retry:
        kwargs['retry_policy'] = freshctx.RetryPolicy(max_attempts=2, max_elapsed_ms=1000, backoff_ms=backoff_ms)
    times=[]
    continued=0
    def marker(recipient):
        nonlocal continued
        continued += 1
        return recipient
    with guard(store=store, audit_path=audit, **kwargs) as ctx:
        for index in range(samples+10):
            source.calls=0
            source.transient=retry
            before=time.perf_counter_ns()
            assert ctx.run(marker, 'recipient-1', depends_on=[b], **options)=='recipient-1'
            elapsed=(time.perf_counter_ns()-before)/1_000_000
            assert source.calls==(2 if retry else 1)
            if index>=10:times.append(elapsed)
    result=summary(times)
    result.update({'persistence':'SQLite+JSONL' if persisted else 'MemoryStore+JSONL',
                   'lineage_required':lineage,'configured_backoff_ms':backoff_ms,
                   'verification_calls_per_boundary':2 if retry else 1,
                   'marker_calls':continued,'source_to_action_parameter_edges':3 if lineage else None})
    if hasattr(store, 'close'):
        store.close()
    return result

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--baseline-only',action='store_true')
    parser.add_argument('--samples',type=int,default=200)
    args=parser.parse_args()
    if args.samples<20:parser.error('at least 20 samples required')
    with tempfile.TemporaryDirectory(prefix='freshctx-bench-') as directory:
        root=Path(directory)
        results={
            'validation_memory':measure(root,'plain-memory',args.samples),
            'validation_sqlite':measure(root,'plain-sqlite',args.samples,persisted=True),
        }
        if not args.baseline_only:
            results.update({
                'lineage_memory':measure(root,'lineage-memory',args.samples,lineage=True),
                'lineage_sqlite':measure(root,'lineage-sqlite',args.samples,persisted=True,lineage=True),
                'retry_no_backoff':measure(root,'retry-zero',args.samples,lineage=True,retry=True),
                'retry_1ms_backoff':measure(root,'retry-one',args.samples,lineage=True,retry=True,backoff_ms=1),
            })
        print(json.dumps({'package_version':freshctx.__version__, 'source_file':freshctx.__file__,
                          'timer':'perf_counter_ns','warmup_samples':10,'results':results},indent=2))
if __name__=='__main__':main()
