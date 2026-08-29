# Release process

1. Run `python scripts/release_check.py` on every supported Python version.
2. Build wheel and source distribution with `python -m build`.
3. Install the wheel into a clean environment and run an import smoke test plus all three demos.
4. Review dependency, secret, license, documentation, and compatibility results.
5. Run `python -m twine check dist/*` and verify the package metadata on TestPyPI when practical.
6. Record the commit SHA and approve the release candidate.
7. Publish with a scoped PyPI API token or GitHub trusted publishing.
8. Install `freshctx` by name in a new environment and rerun the smoke tests.

The release workflow builds and uploads CI artifacts. PyPI publication remains a separate, explicitly authorized release step.

Windows activation commands are not documentation-only. The CI workflow executes the PowerShell and Command Prompt activation paths on a real `windows-latest` runner and runs the installed-package quickstart. Any change to those README commands must keep that job aligned.
