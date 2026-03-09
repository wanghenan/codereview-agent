"""Core module init with lazy loading."""

def __getattr__(name):
    """Lazy load core module members."""
    if name == "CacheManager":
        from codereview.core.cache import CacheManager
        return CacheManager
    elif name == "VersionDetector":
        from codereview.core.cache import VersionDetector
        return VersionDetector
    elif name == "ConfigLoader":
        from codereview.core.config import ConfigLoader
        return ConfigLoader
    elif name == "CodeFixer":
        from codereview.core.fixer import CodeFixer
        return CodeFixer
    elif name == "FixOrchestrator":
        from codereview.core.fixer import FixOrchestrator
        return FixOrchestrator
    elif name == "FixResult":
        from codereview.core.fixer import FixResult
        return FixResult
    elif name == "FixSuggestion":
        from codereview.core.fixer import FixSuggestion
        return FixSuggestion
    elif name == "FixType":
        from codereview.core.fixer import FixType
        return FixType
    elif name == "LLMFactory":
        from codereview.core.llm import LLMFactory
        return LLMFactory
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "CacheManager",
    "CodeFixer",
    "ConfigLoader",
    "FixOrchestrator",
    "FixResult",
    "FixSuggestion",
    "FixType",
    "LLMFactory",
    "VersionDetector",
]
