# Clean PyPI reproduction

The official PyPI wheel `freshctx==0.1.1` was independently installed on 2026-08-30 from `https://pypi.org/simple` into new environments outside the repository checkout. The source baseline was repository SHA `fc682d8f6da65de124b2071fa4fa85b38d72f115`, also version `0.1.1`.

## Command and expected result

```console
python -m pip install --index-url https://pypi.org/simple freshctx
cd /tmp
/path/to/isolated/python /path/to/repository/scripts/clean_install_probe.py
```

The probe expects a declared filesystem dependency to begin valid, reasoning to be created, the file to change, pre-action revalidation to return `STALE_REASONING`, policy to return `block`, and JSONL to contain no `action_allowed` event.

## Actual matrix

| Python | Installed version | Import location | State | Policy | `action_allowed` events |
|---|---|---|---|---|---|
| 3.11.15 | 0.1.1 | isolated `pypi311/lib/python3.11/site-packages/freshctx/__init__.py` | `STALE_REASONING` | `block` | 0 |
| 3.13.13 | 0.1.1 | isolated `pypi313/lib/python3.13/site-packages/freshctx/__init__.py` | `STALE_REASONING` | `block` | 0 |

The emitted `policy_applied` event used schema version 1 and contained the current fields `event_id`, `run_id`, `event_type`, `timestamp`, `subject_id`, and `details`. Details contained `state: STALE_REASONING`, `policy_decision: block`, the changed token cause, and adapter evidence with `outcome: changed`.

Python 3.10 and 3.12 interpreters were not installed on the measurement host, so local clean-install results are not claimed for them. The authoritative GitHub Actions matrix runs the repository tests on 3.10, 3.11, 3.12, and 3.13; the starting remote HEAD had a successful matrix run. PyPI and repository versions match. No packaging defect or runtime discrepancy was observed, so no packaging change was made.
