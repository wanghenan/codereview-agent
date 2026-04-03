"""Cache manager for project context and file-level review cache."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from codereview.models import ProjectContext

logger = logging.getLogger(__name__)

# Optional imports for version detection
try:
    import tomli
except ImportError:
    tomli = None


class FileReviewCache:
    """Cache for individual file review results to enable incremental review."""

    CACHE_DIR = Path(".codereview-agent/cache")
    FILE_CACHE_DIR = CACHE_DIR / "file_reviews"

    def __init__(self, cache_ttl_days: int = 7):
        """Initialize file review cache.

        Args:
            cache_ttl_days: Cache time-to-live in days
        """
        self.cache_ttl_days = cache_ttl_days
        self._ensure_cache_dir()

    def _ensure_cache_dir(self) -> None:
        """Ensure cache directories exist."""
        self.CACHE_DIR.mkdir(parents=True, exist_ok=True)
        self.FILE_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    def _normalize_patch(self, patch: str) -> str:
        """Normalize patch for consistent hashing.

        Extracts semantic content of a diff, ignoring:
        - Trailing whitespace
        - Duplicate content lines
        - Empty lines
        - Whitespace-only formatting changes

        This ensures that semantically identical patches (even with different
        whitespace) will produce the same cache key.

        Args:
            patch: Raw diff patch content

        Returns:
            Normalized patch string
        """
        if not patch:
            return ""

        lines = patch.splitlines()
        normalized = []
        seen = set()

        for line in lines:
            # Skip empty lines
            if not line.strip():
                continue

            # Get the meaningful content (strip +/- for diff lines)
            if line.startswith("+"):
                content = "+" + line.lstrip("+").strip()
            elif line.startswith("-"):
                content = "-" + line.lstrip("-").strip()
            else:
                content = line.strip()

            # Skip duplicate content
            if content in seen:
                continue
            seen.add(content)

            # Keep hunk headers as-is
            if line.startswith("@@"):
                normalized.append(line)
            else:
                normalized.append(content)

        return "\n".join(normalized)

    def _get_file_hash(self, filename: str, content: str) -> str:
        """Generate hash for file content.

        Args:
            filename: File name
            content: File content (diff patch)

        Returns:
            Hash string
        """
        # Normalize patch for consistent hashing
        normalized_content = self._normalize_patch(content)
        data = f"{filename}:{normalized_content}"
        return hashlib.sha256(data.encode()).hexdigest()[:16]

    def _get_cache_path(self, filename: str) -> Path:
        """Get cache file path for a file.

        Args:
            filename: File name

        Returns:
            Path to cache file
        """
        # Use safe filename
        safe_filename = filename.replace("/", "_").replace("\\", "_")
        return self.FILE_CACHE_DIR / f"{safe_filename}.json"

    def get(self, filename: str, patch: str) -> Optional[dict]:
        """Get cached review result for a file.

        Args:
            filename: File name
            patch: Diff patch content

        Returns:
            Cached review result or None if not found/expired
        """
        cache_path = self._get_cache_path(filename)
        
        if not cache_path.exists():
            return None

        try:
            with open(cache_path) as f:
                data = json.load(f)

            # Check if cache is expired
            cached_at = datetime.fromisoformat(data.get("cached_at", ""))
            ttl = timedelta(days=self.cache_ttl_days)
            if datetime.now() - cached_at > ttl:
                return None

            # Check if patch hash matches (file unchanged)
            current_hash = self._get_file_hash(filename, patch)
            if data.get("patch_hash") != current_hash:
                return None

            return data.get("result")
        except (json.JSONDecodeError, KeyError, ValueError, FileNotFoundError):
            return None

    def save(self, filename: str, patch: str, result: dict) -> None:
        """Save review result to cache.

        Args:
            filename: File name
            patch: Diff patch content
            result: Review result to cache
        """
        cache_path = self._get_cache_path(filename)
        patch_hash = self._get_file_hash(filename, patch)

        data = {
            "filename": filename,
            "patch_hash": patch_hash,
            "cached_at": datetime.now().isoformat(),
            "result": result,
        }

        try:
            with open(cache_path, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save file review cache: {e}")

    def invalidate(self, filename: str) -> None:
        """Invalidate cache for a specific file.

        Args:
            filename: File name
        """
        cache_path = self._get_cache_path(filename)
        if cache_path.exists():
            cache_path.unlink()

    def invalidate_all(self) -> None:
        """Invalidate all file review caches."""
        if self.FILE_CACHE_DIR.exists():
            for cache_file in self.FILE_CACHE_DIR.glob("*.json"):
                cache_file.unlink()

    def get_stats(self) -> dict:
        """Get cache statistics.

        Returns:
            Dictionary with cache stats
        """
        if not self.FILE_CACHE_DIR.exists():
            return {"total": 0, "valid": 0, "expired": 0}

        total = 0
        valid = 0
        expired = 0
        now = datetime.now()

        for cache_file in self.FILE_CACHE_DIR.glob("*.json"):
            total += 1
            try:
                with open(cache_file) as f:
                    data = json.load(f)
                cached_at = datetime.fromisoformat(data.get("cached_at", ""))
                ttl = timedelta(days=self.cache_ttl_days)
                if now - cached_at > ttl:
                    expired += 1
                else:
                    valid += 1
            except Exception:
                expired += 1

        return {"total": total, "valid": valid, "expired": expired}


class CacheManager:
    """Manage project context cache and file review cache."""

    CACHE_DIR = Path(".codereview-agent/cache")
    CACHE_FILE = CACHE_DIR / "project-context.json"

    def __init__(self, cache_ttl_days: int = 7, enable_file_cache: bool = True):
        """Initialize cache manager.

        Args:
            cache_ttl_days: Project context cache time-to-live in days
            enable_file_cache: Enable file-level review caching
        """
        self.cache_ttl_days = cache_ttl_days
        self._ensure_cache_dir()
        
        # Initialize file review cache
        self.file_cache = FileReviewCache(cache_ttl_days) if enable_file_cache else None

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
                with open(pkg_json) as f:
                    data = json.load(f)
                    return data.get("version")
            except Exception:
                pass

        # Check pyproject.toml (Python)
        pyproject = root_dir / "pyproject.toml"
        if pyproject.exists():
            try:
                if tomli is None:
                    raise ImportError("tomli not installed")
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
