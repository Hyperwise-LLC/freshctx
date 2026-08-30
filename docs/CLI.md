# FreshCtx command-line tools

Install the package, then run commands as `freshctx ...` or `python -m freshctx ...`.

## Check a stored subject

```console
freshctx check SUBJECT_ID --store .freshctx/freshctx.db
```

The command prints the complete `CheckResult` as JSON. Exit code 0 means `CURRENT`; exit code 2 means stale, unverifiable, or invalid input. External adapters may require process-local validation inputs and therefore fail closed after restart.

## Summarize audit evidence

```console
freshctx audit --audit .freshctx/audit.jsonl
```

The command validates each JSONL line and reports event counts. It does not alter or upload the audit file.

## Diagnose installation and storage

```console
freshctx doctor --store .freshctx/freshctx.db
```

The report includes package version, Python version, supported schema version, store schema version, and SQLite integrity status.
