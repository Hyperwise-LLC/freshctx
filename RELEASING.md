# Release process

1. Run `python scripts/release_check.py` on every supported Python version.
2. Build wheel and source distribution with `python -m build`.
3. Install the wheel into a clean environment and run an import smoke test plus all three demos.
4. Review dependency, secret, license, documentation, and compatibility results.
5. Confirm the repository, package, release, documentation site, and artifacts remain private.
6. Record the commit SHA and approve a release candidate.
7. Obtain the user's explicit permission before changing visibility or publishing anything.

The private build workflow uploads only private CI artifacts. It contains no package-publishing or repository-visibility step.
