"""Cache manager for project context."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from codereview.models import ProjectContext


class CacheManager:
    """Manage project context cache."""

    CACHE_DIR = Path(".codereview-agent/cache")
    CACHE_FILE = CACHE_DIR / "project-context.json"

    def __init__(self, cache_ttl_days: int = 7):
        """Initialize cache manager.

        Args:
            cache_ttl_days: Cache time-to-live in days
        """
        self.cache_ttl_days = cache_ttl_days
        self._ensure_cache_dir()

    def _ensure_cache_dir(self) -> None:
        """Ensure cache directory exists."""
        self.CACHE_DIR.mkdir(parents=True, exist_ok=True)

    def get_cache_path(self) -> Path:
        """Get path to cache file."""
        return self.CACHE_FILE

    def load(self) -> Optional[ProjectContext]:
        """Load cached project context if valid.

        Returns:
            Cached context if valid, None otherwise
        """
        if not self.CACHE_FILE.exists():
            return None

        try:
            with open(self.CACHE_FILE) as f:
                data = json.load(f)

            # Check if cache is expired
            cached_at = datetime.fromisoformat(data["analyzed_at"])
            ttl = timedelta(days=self.cache_ttl_days)
            if datetime.now() - cached_at > ttl:
                return None

            return ProjectContext(**data)
        except (json.JSONDecodeError, KeyError, ValueError):
            # Invalid cache, treat as no cache
            return None

    def save(self, context: ProjectContext) -> None:
        """Save project context to cache.

        Args:
            context: Project context to cache
        """
        context.analyzed_at = datetime.now().isoformat()

        self._ensure_cache_dir()

        with open(self.CACHE_FILE, "w") as f:
            json.dump(context.model_dump(), f, indent=2)

    def invalidate(self) -> None:
        """Invalidate the cache."""
        if self.CACHE_FILE.exists():
            self.CACHE_FILE.unlink()

    def get_cache_info(self) -> dict:
        """Get information about the current cache.

        Returns:
            Cache info dict with timestamp and version
        """
        if not self.CACHE_FILE.exists():
            return {"exists": False}

        try:
            stat = self.CACHE_FILE.stat()
            modified = datetime.fromtimestamp(stat.st_mtime)

            # Try to read version
            version = "unknown"
            try:
                with open(self.CACHE_FILE) as f:
                    data = json.load(f)
                    version = data.get("version", "unknown")
            except Exception:
                pass

            return {
                "exists": True,
                "modified_at": modified.isoformat(),
                "version": version,
            }
        except Exception:
            return {"exists": False}

    def is_valid(self) -> bool:
        """Check if current cache is valid.

        Returns:
            True if cache exists and is valid
        """
        return self.load() is not None


class VersionDetector:
    """Detect project version for cache invalidation."""

    @staticmethod
    def detect_version(root_dir: Path) -> Optional[str]:
        """Detect project version from config files.

        Args:
            root_dir: Project root directory

        Returns:
            Version string if detected, None otherwise
        """
        # Check package.json (Node.js)
        pkg_json = root_dir / "package.json"
        if pkg_json.exists():
            try:
                import json

                with open(pkg_json) as f:
                    data = json.load(f)
                    return data.get("version")
            except Exception:
                pass

        # Check pyproject.toml (Python)
        pyproject = root_dir / "pyproject.toml"
        if pyproject.exists():
            try:
                import tomli

                with open(pyproject, "rb") as f:
                    data = tomli.load(f)
                    return data.get("project", {}).get("version")
            except ImportError:
                # tomli not installed, try manual parsing
                pass
            except Exception:
                pass

        # Check setup.py, __init__.py version, etc.
        return None

    @staticmethod
    def has_config_changed(root_dir: Path, cached_version: str) -> bool:
        """Check if project config has changed since cached version.

        Args:
            root_dir: Project root directory
            cached_version: Version from cache

        Returns:
            True if config has changed
        """
        current_version = VersionDetector.detect_version(root_dir)
        return current_version != cached_version
