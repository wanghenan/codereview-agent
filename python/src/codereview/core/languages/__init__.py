"""Multi-language health check module.

This module provides language-specific code analysis and health checks
for multiple programming languages.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# Language detection mapping
EXTENSION_TO_LANGUAGE = {
    # Python
    ".py": "python",
    ".pyw": "python",
    # JavaScript/TypeScript
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    # Go
    ".go": "go",
    # Java
    ".java": "java",
    # Rust
    ".rs": "rust",
    # C++
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".c++": "cpp",
    ".h": "cpp",
    ".hpp": "cpp",
    ".hh": "cpp",
    # PHP
    ".php": "php",
    # Ruby
    ".rb": "ruby",
    ".rake": "ruby",
    ".gemspec": "ruby",
    # C#
    ".cs": "csharp",
    # Other
    ".swift": "swift",
    ".kt": "kotlin",
    ".scala": "scala",
}


# Language display names
LANGUAGE_NAMES = {
    "python": "Python",
    "javascript": "JavaScript",
    "typescript": "TypeScript",
    "go": "Go",
    "java": "Java",
    "rust": "Rust",
    "cpp": "C++",
    "php": "PHP",
    "ruby": "Ruby",
    "csharp": "C#",
    "swift": "Swift",
    "kotlin": "Kotlin",
    "scala": "Scala",
}


@dataclass
class LanguageIssue:
    """A code issue found by language analyzer."""

    rule_id: str
    rule_name: str
    line_number: int
    severity: str  # high, medium, low
    description: str
    suggestion: str
    language: str


@dataclass
class LanguageAnalysisResult:
    """Result of language-specific code analysis."""

    language: str
    file_path: str
    issues: list[LanguageIssue] = field(default_factory=list)
    health_score: float = 100.0  # 0-100, higher is better
    summary: str = ""


class BaseLanguageAnalyzer(ABC):
    """Base class for language analyzers."""

    def __init__(self, language: str):
        """Initialize analyzer.

        Args:
            language: Language identifier
        """
        self.language = language

    @abstractmethod
    def analyze(self, content: str, file_path: str) -> LanguageAnalysisResult:
        """Analyze code content.

        Args:
            content: Source code content
            file_path: Path to the source file

        Returns:
            Analysis result with issues and health score
        """
        pass

    @abstractmethod
    def get_rules(self) -> list[dict]:
        """Get language-specific detection rules.

        Returns:
            List of rule dictionaries
        """
        pass

    def _calculate_health_score(self, issues: list[LanguageIssue]) -> float:
        """Calculate health score based on issues.

        Args:
            issues: List of issues found

        Returns:
            Health score (0-100)
        """
        if not issues:
            return 100.0

        # Deduct points based on severity
        deductions = 0
        for issue in issues:
            if issue.severity == "high":
                deductions += 10
            elif issue.severity == "medium":
                deductions += 5
            elif issue.severity == "low":
                deductions += 2

        return max(0.0, 100.0 - deductions)


# Registry of language analyzers
_LANGUAGE_ANALYZERS: dict[str, type[BaseLanguageAnalyzer]] = {}


def register_analyzer(language: str) -> callable:
    """Decorator to register a language analyzer.

    Args:
        language: Language identifier

    Returns:
        Decorator function
    """

    def decorator(cls: type[BaseLanguageAnalyzer]) -> type[BaseLanguageAnalyzer]:
        _LANGUAGE_ANALYZERS[language] = cls
        return cls

    return decorator


def get_analyzer(language: str) -> Optional[BaseLanguageAnalyzer]:
    """Get an analyzer for the specified language.

    Args:
        language: Language identifier

    Returns:
        Language analyzer instance or None if not supported
    """
    if language not in _LANGUAGE_ANALYZERS:
        # Try to import the language module
        try:
            import importlib

            importlib.import_module(f"codereview.core.languages.{language}")
        except ImportError:
            pass

    if language in _LANGUAGE_ANALYZERS:
        return _LANGUAGE_ANALYZERS[language](language)

    return None


def detect_language(file_path: str) -> Optional[str]:
    """Detect language from file path.

    Args:
        file_path: Path to the file

    Returns:
        Language identifier or None if not detected
    """
    path = Path(file_path)
    extension = path.suffix.lower()

    # Check extension
    if extension in EXTENSION_TO_LANGUAGE:
        return EXTENSION_TO_LANGUAGE[extension]

    # Check filename patterns
    filename = path.name.lower()
    if filename == "dockerfile":
        return "dockerfile"
    if filename == "makefile" or filename == "makefile.mk":
        return "makefile"
    if filename.endswith("makefile"):
        return "makefile"

    return None


def get_supported_languages() -> list[str]:
    """Get list of supported languages.

    Returns:
        List of supported language identifiers
    """
    return list(EXTENSION_TO_LANGUAGE.values())


def analyze_file(
    content: str,
    file_path: str,
    language: Optional[str] = None,
) -> Optional[LanguageAnalysisResult]:
    """Analyze a file with language-specific rules.

    Args:
        content: Source code content
        file_path: Path to the source file
        language: Optional language override

    Returns:
        Analysis result or None if language not supported
    """
    # Auto-detect language if not provided
    if language is None:
        language = detect_language(file_path)

    if language is None:
        return None

    # Get analyzer
    analyzer = get_analyzer(language)
    if analyzer is None:
        return None

    return analyzer.analyze(content, file_path)


# Import all language analyzers to register them
from codereview.core.languages import (  # noqa: F401,E402,I001
    cpp as cpp,
    csharp as csharp,
    go as go,
    java as java,
    php as php,
    ruby as ruby,
    rust as rust,
)


def analyze_multiple_files(
    files: list[tuple[str, str]],  # List of (file_path, content)
    max_workers: int = 4,
) -> list[LanguageAnalysisResult]:
    """Analyze multiple files in parallel.

    Args:
        files: List of tuples (file_path, content)
        max_workers: Maximum number of parallel workers

    Returns:
        List of analysis results
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    results = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_file = {
            executor.submit(analyze_file, content, file_path): (file_path, content)
            for file_path, content in files
        }

        for future in as_completed(future_to_file):
            try:
                result = future.result()
                if result:
                    results.append(result)
            except Exception as e:
                logger.error(f"Error analyzing file: {e}")

    return results


def analyze_directory(
    directory: Path,
    extensions: Optional[list[str]] = None,
    exclude_patterns: Optional[list[str]] = None,
    max_workers: int = 4,
) -> list[LanguageAnalysisResult]:
    """Analyze all supported files in a directory.

    Args:
        directory: Directory to analyze
        extensions: Optional list of extensions to include
        exclude_patterns: Optional list of patterns to exclude
        max_workers: Maximum number of parallel workers

    Returns:
        List of analysis results
    """
    import fnmatch

    exclude_patterns = exclude_patterns or []
    files = []

    for file_path in directory.rglob("*"):
        if not file_path.is_file():
            continue

        # Check if file matches exclude patterns
        file_str = str(file_path)
        if any(fnmatch.fnmatch(file_str, pattern) for pattern in exclude_patterns):
            continue

        # Check extension filter
        if extensions and file_path.suffix.lower() not in extensions:
            continue

        # Try to detect language
        if detect_language(file_str):
            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
                files.append((file_str, content))
            except Exception as e:
                logger.warning(f"Could not read file {file_str}: {e}")

    return analyze_multiple_files(files, max_workers)
