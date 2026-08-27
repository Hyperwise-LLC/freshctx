# Release process

1. Run `python scripts/release_check.py` on every supported Python version.
2. Build wheel and source distribution with `python -m build`.
3. Install the wheel into a clean environment and run an import smoke test plus all three demos.
4. Review dependency, secret, license, documentation, and compatibility results.
5. Confirm no repository, package, release, documentation site, or artifact has been made publicly available.
6. Record the commit SHA and approve a release candidate.
7. Obtain the user's explicit permission before changing visibility or publishing anything.

The private build workflow uploads only private CI artifacts. It contains no package-publishing or repository-visibility step.

Windows activation commands are not documentation-only. The CI workflow executes the PowerShell and Command Prompt activation paths on a real `windows-latest` runner and runs the installed-package quickstart. Any change to those README commands must keep that job aligned.
