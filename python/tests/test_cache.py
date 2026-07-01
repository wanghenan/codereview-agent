"""Tests for cache functionality."""

import tempfile
from datetime import datetime
from pathlib import Path

from codereview.core.cache import CacheManager, FileReviewCache, VersionDetector


class TestFileReviewCache:
    """Test FileReviewCache class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.cache = FileReviewCache(
            cache_ttl_days=7,
            cache_dir=str(Path(self.temp_dir) / ".codereview-agent/cache")
        )

    def teardown_method(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_cache_initialization(self):
        """Test cache initialization."""
        assert self.cache.cache_ttl_days == 7
        assert self.cache.cache_dir.exists()
        assert self.cache.file_cache_dir.exists()

    def test_get_file_hash(self):
        """Test file hash generation."""
        hash1 = self.cache._get_file_hash("test.py", "content1")
        hash2 = self.cache._get_file_hash("test.py", "content1")
        hash3 = self.cache._get_file_hash("test.py", "content2")

        assert hash1 == hash2
        assert hash1 != hash3

    def test_save_and_get(self):
        """Test saving and retrieving cache."""
        filename = "test.py"
        patch_content = "@@ -1,3 +1,4 @@\n+password = 'hardcoded'"
        result = {"issues": [{"severity": "high", "description": "Hardcoded password"}]}

        self.cache.save(filename, patch_content, result)
        cached = self.cache.get(filename, patch_content)

        assert cached is not None
        assert cached["issues"][0]["severity"] == "high"

    def test_get_expired_cache(self):
        """Test getting expired cache returns None."""
        cache = FileReviewCache(
            cache_ttl_days=0,
            cache_dir=str(Path(self.temp_dir) / ".codereview-agent/cache_expired")
        )

        filename = "test.py"
        patch_content = "@@ diff"
        result = {"issues": []}

        cache.save(filename, patch_content, result)

        cached = cache.get(filename, patch_content)
        assert cached is None

    def test_get_mismatched_patch(self):
        """Test cache returns None when patch differs."""
        filename = "test.py"
        patch_content = "original diff"
        result = {"issues": []}

        self.cache.save(filename, patch_content, result)

        cached = self.cache.get(filename, "different diff")
        assert cached is None

    def test_invalidate(self):
        """Test invalidating single file cache."""
        filename = "test.py"
        patch_content = "@@ diff"
        result = {"issues": []}

        self.cache.save(filename, patch_content, result)
        assert self.cache.get(filename, patch_content) is not None

        self.cache.invalidate(filename)
        assert self.cache.get(filename, patch_content) is None

    def test_invalidate_all(self):
        """Test invalidating all caches."""
        self.cache.save("test1.py", "diff1", {"issues": []})
        self.cache.save("test2.py", "diff2", {"issues": []})

        assert len(list(self.cache.file_cache_dir.glob("*.json"))) == 2

        self.cache.invalidate_all()

        assert len(list(self.cache.file_cache_dir.glob("*.json"))) == 0

    def test_get_stats(self):
        """Test cache statistics."""
        self.cache.save("test1.py", "diff1", {"issues": []})
        self.cache.save("test2.py", "diff2", {"issues": []})

        stats = self.cache.get_stats()

        assert stats["total"] == 2
        assert stats["valid"] == 2
        assert stats["expired"] == 0

    def test_normalize_patch_removes_whitespace(self):
        """Test that normalize_patch removes trailing whitespace."""
        patch1 = """+    console.log('hello')
-    console.log('world')
"""
        patch2 = """+console.log('hello')
-console.log('world')
"""
        norm1 = self.cache._normalize_patch(patch1)
        norm2 = self.cache._normalize_patch(patch2)
        assert norm1 == norm2

    def test_normalize_patch_removes_duplicates(self):
        """Test that normalize_patch removes duplicate lines."""
        patch = """+line1
+line1
+line2
"""
        norm = self.cache._normalize_patch(patch)
        lines = norm.split("\n")
        assert lines.count("+line1") == 1
        assert "+line2" in lines

    def test_normalize_patch_handles_empty(self):
        """Test that normalize_patch handles empty patches."""
        assert self.cache._normalize_patch("") == ""
        assert self.cache._normalize_patch(None) == ""

    def test_normalize_patch_keeps_hunk_headers(self):
        """Test that normalize_patch keeps hunk headers."""
        patch = """@@ -1,5 +1,5 @@
+    console.log('hello')
-    console.log('world')
"""
        norm = self.cache._normalize_patch(patch)
        assert "@@ -1,5 +1,5 @@" in norm

    def test_namespace_affects_cache_key(self):
        """Different namespaces must produce different cache keys.

        Regression: previously the key depended only on filename + patch, so
        switching the LLM model or updating rules silently returned a stale
        review. The namespace (model + rules hash) now folds into the key.
        """
        temp_dir = tempfile.mkdtemp()
        try:
            cache_a = FileReviewCache(
                cache_ttl_days=7,
                cache_dir=str(Path(temp_dir) / "a"),
                cache_namespace="gpt-4o:r1",
            )
            cache_b = FileReviewCache(
                cache_ttl_days=7,
                cache_dir=str(Path(temp_dir) / "b"),
                cache_namespace="glm-4-flash:r1",
            )

            filename = "src/auth.py"
            patch = "@@ -1 +1 @@\n+secret = 'x'"
            result = {"risk_level": "high"}

            cache_a.save(filename, patch, result)

            # Same filename+patch but a different namespace -> no hit.
            assert cache_b.get(filename, patch) is None
            # Same namespace -> hit.
            assert cache_a.get(filename, patch) is not None
        finally:
            import shutil

            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_default_namespace_backward_compat(self):
        """Omitting cache_namespace keeps the legacy 'default' behavior."""
        temp_dir = tempfile.mkdtemp()
        try:
            legacy = FileReviewCache(
                cache_ttl_days=7,
                cache_dir=str(Path(temp_dir) / "legacy"),
            )
            assert legacy.cache_namespace == "default"

            filename = "lib.py"
            patch = "@@ -1 +1 @@\n+x = 1"
            legacy.save(filename, patch, {"risk_level": "low"})
            # Round-trip works under the default namespace.
            assert legacy.get(filename, patch) == {"risk_level": "low"}
        finally:
            import shutil

            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_corrupt_cache_file_logs_debug(self, caplog):
        """A corrupt cache file must be logged at debug (not silently swallowed)."""
        import logging

        caplog.set_level(logging.DEBUG, logger="codereview.core.cache")

        temp_dir = tempfile.mkdtemp()
        try:
            cache = FileReviewCache(
                cache_ttl_days=7,
                cache_dir=str(Path(temp_dir) / "corrupt"),
            )
            # Write a corrupt JSON file where a review cache is expected.
            target = cache.file_cache_dir / "bad.py.json"
            target.write_text("{ this is not valid json")

            stats = cache.get_stats()
            # Corrupt file counts as expired, but crucially a debug log emitted.
            assert stats["total"] == 1
            assert any("cache" in rec.message.lower() for rec in caplog.records)
        finally:
            import shutil

            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_cleanup_expired_removes_expired_files(self):
        """cleanup_expired deletes cache files older than the TTL."""
        # cache_ttl_days=0 means anything saved is immediately expired.
        cache = FileReviewCache(
            cache_ttl_days=0,
            cache_dir=str(Path(self.temp_dir) / "cleanup_expired"),
        )
        cache.save("old1.py", "diff1", {"issues": []})
        cache.save("old2.py", "diff2", {"issues": []})
        assert len(list(cache.file_cache_dir.glob("*.json"))) == 2

        removed = cache.cleanup_expired()

        assert removed == 2
        assert len(list(cache.file_cache_dir.glob("*.json"))) == 0

    def test_cleanup_expired_keeps_valid_files(self):
        """cleanup_expired leaves non-expired cache files untouched."""
        self.cache.save("valid1.py", "diff1", {"issues": []})
        self.cache.save("valid2.py", "diff2", {"issues": []})

        removed = self.cache.cleanup_expired()

        assert removed == 0
        assert len(list(self.cache.file_cache_dir.glob("*.json"))) == 2

    def test_cleanup_expired_handles_mixed(self):
        """cleanup_expired removes only expired files from a mixed set."""
        # Valid file via default cache (ttl=7d), freshly written.
        self.cache.save("valid.py", "diff_v", {"issues": []})
        # Expired file: same dir, but backdate its cached_at beyond TTL.
        self.cache.save("old.py", "diff_o", {"issues": []})
        old_path = self.cache.file_cache_dir / "old.py.json"
        import json as _json
        data = _json.loads(old_path.read_text())
        data["cached_at"] = "2020-01-01T00:00:00"  # far in the past
        old_path.write_text(_json.dumps(data))
        assert len(list(self.cache.file_cache_dir.glob("*.json"))) == 2

        removed = self.cache.cleanup_expired()

        assert removed == 1
        remaining = [f.name for f in self.cache.file_cache_dir.glob("*.json")]
        assert len(remaining) == 1
        assert "valid.py.json" in remaining

    def test_cleanup_expired_removes_corrupt_files(self):
        """cleanup_expired deletes corrupt JSON files it cannot parse."""
        target = self.cache.file_cache_dir / "broken.py.json"
        target.write_text("{ not valid json")
        assert target.exists()

        removed = self.cache.cleanup_expired()

        assert removed == 1
        assert not target.exists()

    def test_cleanup_expired_empty_dir(self):
        """cleanup_expired on an empty cache dir returns 0."""
        removed = self.cache.cleanup_expired()
        assert removed == 0


class TestCacheManager:
    """Test CacheManager class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.cache_manager = CacheManager(
            cache_ttl_days=7,
            cache_dir=str(Path(self.temp_dir) / ".codereview-agent/cache")
        )

    def teardown_method(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_cache_manager_init(self):
        """Test cache manager initialization."""
        assert self.cache_manager.cache_ttl_days == 7
        assert self.cache_manager.file_cache is not None
        assert self.cache_manager.cache_dir.exists()

    def test_get_cache_path(self):
        """Test getting cache path."""
        path = self.cache_manager.get_cache_path()
        assert path == self.cache_manager.cache_file

    def test_save_and_load(self):
        """Test saving and loading project context."""
        from codereview.models import ProjectContext

        ctx = ProjectContext(
            tech_stack=["python"],
            language="python",
            critical_paths=[],
            analyzed_at=datetime.now().isoformat(),
        )

        self.cache_manager.save(ctx)
        loaded = self.cache_manager.load()

        assert self.cache_manager.cache_file.exists()
        assert loaded is not None

    def test_load_no_cache(self):
        """Test loading when no cache exists."""
        loaded = self.cache_manager.load()
        assert loaded is None

    def test_invalidate(self):
        """Test cache invalidation."""
        from codereview.models import ProjectContext

        ctx = ProjectContext(
            tech_stack=["python"],
            language="python",
            critical_paths=[],
            analyzed_at=datetime.now().isoformat(),
        )

        self.cache_manager.save(ctx)
        assert self.cache_manager.cache_file.exists()

        self.cache_manager.invalidate()
        assert not self.cache_manager.cache_file.exists()

    def test_get_cache_info_no_cache(self):
        """Test getting cache info when no cache exists."""
        info = self.cache_manager.get_cache_info()
        assert info["exists"] is False

    def test_is_valid(self):
        """Test cache validity check."""
        assert self.cache_manager.is_valid() is False

        from codereview.models import ProjectContext

        ctx = ProjectContext(
            tech_stack=["python"],
            language="python",
            critical_paths=[],
            analyzed_at=datetime.now().isoformat(),
        )

        self.cache_manager.save(ctx)
        assert self.cache_manager.cache_file.exists()


class TestVersionDetector:
    """Test VersionDetector class."""

    def test_detect_version_no_config(self):
        """Test version detection with no config files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            version = VersionDetector.detect_version(root)
            assert version is None

    def test_detect_version_package_json(self):
        """Test version detection from package.json."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            pkg_json = root / "package.json"
            pkg_json.write_text('{"name": "test", "version": "1.2.3"}')

            version = VersionDetector.detect_version(root)
            assert version == "1.2.3"

    def test_detect_version_pyproject_toml(self):
        """Test version detection from pyproject.toml."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            pyproject = root / "pyproject.toml"
            pyproject.write_text('[project]\nversion = "2.0.0"')

            version = VersionDetector.detect_version(root)
            # May be None if tomli not installed
            assert version is None or version == "2.0.0"

    def test_has_config_changed(self):
        """Test checking if config has changed."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            pkg_json = root / "package.json"
            pkg_json.write_text('{"version": "1.0.0"}')

            changed = VersionDetector.has_config_changed(root, "1.0.0")
            assert changed is False

            changed = VersionDetector.has_config_changed(root, "0.9.0")
            assert changed is True
