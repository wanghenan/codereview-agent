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
    elif name == "AutoMerger":
        from codereview.core.auto_merger import AutoMerger
        return AutoMerger
    elif name == "create_auto_merger":
        from codereview.core.auto_merger import create_auto_merger
        return create_auto_merger
    elif name == "GitHubClient":
        from codereview.core.github_client import GitHubClient
        return GitHubClient
    elif name == "create_github_client":
        from codereview.core.github_client import create_github_client
        return create_github_client
    elif name == "MergeMethod":
        from codereview.core.github_client import MergeMethod
        return MergeMethod
    elif name == "HistoryTracker":
        from codereview.core.history_tracker import HistoryTracker
        return HistoryTracker
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "AutoMerger",
    "CacheManager",
    "CodeFixer",
    "ConfigLoader",
    "create_auto_merger",
    "create_github_client",
    "create_team_insights",
    "FixOrchestrator",
    "FixResult",
    "FixSuggestion",
    "FixType",
    "GitHubClient",
    "HistoryTracker",
    "LLMFactory",
    "MergeMethod",
    "TeamInsights",
    "VersionDetector",
]
