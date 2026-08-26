.PHONY: test compile release-check build clean

test:
	python -m unittest discover -s tests -v

compile:
	python -m compileall -q src tests

release-check:
	python scripts/release_check.py

build: release-check
	python -m build

clean:
	python -c 'import shutil; [shutil.rmtree(p, ignore_errors=True) for p in ("build", "dist", "src/freshctx.egg-info")]'
