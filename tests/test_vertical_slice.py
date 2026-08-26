import tempfile
import subprocess
import unittest
from pathlib import Path

from freshctx import FreshnessBlocked, FreshnessState, MemoryStore, guard, observe, reasoning


class VerticalSliceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name); self.config = self.root / "config.yaml"; self.config.write_text("target: staging\n")
        self.audit = self.root / "audit.jsonl"; self.store = MemoryStore()
    def tearDown(self): self.tmp.cleanup()

    def build_reasoning(self):
        with guard(store=self.store, audit_path=self.audit) as ctx:
            token = observe(self.config)
            with reasoning("deployment_target", [token]) as node: pass
            ctx.protect(depends_on=[node])
        return token, node

    def test_current_allows(self):
        token, node = self.build_reasoning()
        with guard(store=self.store, audit_path=self.audit) as ctx:
            ctx.protect(depends_on=[node])
        self.assertEqual(ctx.result.state, FreshnessState.CURRENT)

    def test_changed_file_marks_source_and_reasoning_stale_and_blocks(self):
        token, node = self.build_reasoning(); self.config.write_text("target: production\n")
        with guard(store=self.store, audit_path=self.audit) as source_guard:
            source_guard.protect(depends_on=[token])
            source_result = source_guard.check(token)
            self.assertEqual(source_result.state, FreshnessState.STALE_SOURCE)
            source_guard.protected.clear()
        with self.assertRaises(FreshnessBlocked) as raised:
            with guard(store=self.store, audit_path=self.audit) as ctx: ctx.protect(depends_on=[node])
        self.assertEqual(raised.exception.result.state, FreshnessState.STALE_REASONING)
        self.assertIn(token.id, raised.exception.result.causes)

    def test_missing_file_is_stale_source(self):
        token, _ = self.build_reasoning(); self.config.unlink()
        with self.assertRaises(FreshnessBlocked) as raised:
            with guard(store=self.store, audit_path=self.audit) as ctx: ctx.protect(depends_on=[token])
        self.assertEqual(raised.exception.result.state, FreshnessState.STALE_SOURCE)


class GitAdapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name); self.repo = self.root / "repo"; self.repo.mkdir(); self.audit = self.root / "audit.jsonl"; self.store = MemoryStore()
        self.git("init", "-q"); self.git("config", "user.email", "freshctx@example.invalid"); self.git("config", "user.name", "FreshCtx Tests")
        (self.repo / "config.yaml").write_text("target: staging\n"); (self.repo / "notes.txt").write_text("one\n")
        self.git("add", "."); self.git("commit", "-qm", "initial")
    def tearDown(self): self.tmp.cleanup()
    def git(self, *args): return subprocess.run(["git", "-C", str(self.repo), *args], check=True, capture_output=True, text=True).stdout.strip()

    def test_path_scope_ignores_unrelated_commit_but_repo_scope_stales(self):
        with guard(store=self.store, audit_path=self.audit) as ctx:
            path_token = observe(self.repo, adapter="git", scope="path", path="config.yaml")
            repo_token = observe(self.repo, adapter="git", scope="repository")
            ctx.protect(depends_on=[path_token]); ctx.protected.clear()
        (self.repo / "notes.txt").write_text("two\n"); self.git("add", "notes.txt"); self.git("commit", "-qm", "unrelated change")
        with guard(store=self.store, audit_path=self.audit) as ctx:
            path_result = ctx.check(path_token)
            repo_result = ctx.check(repo_token)
        self.assertEqual(path_result.state, FreshnessState.CURRENT)
        self.assertEqual(repo_result.state, FreshnessState.STALE_SOURCE)

    def test_path_change_is_stale_source(self):
        with guard(store=self.store, audit_path=self.audit) as ctx:
            token = observe(self.repo, adapter="git", scope="path", path="config.yaml")
            ctx.protect(depends_on=[token]); ctx.protected.clear()
        (self.repo / "config.yaml").write_text("target: production\n")
        with guard(store=self.store, audit_path=self.audit) as ctx:
            result = ctx.check(token)
        self.assertEqual(result.state, FreshnessState.STALE_SOURCE)


if __name__ == "__main__": unittest.main()
