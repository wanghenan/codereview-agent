"""Team Insights - Analyze team code review patterns and provide recommendations."""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


class IssueType:
    """Issue type categories."""
    SECURITY = "security"
    PERFORMANCE = "performance"
    STYLE = "style"
    BUG = "bug"
    BEST_PRACTICE = "best_practice"
    DOCUMENTATION = "documentation"
    OTHER = "other"


class TeamInsights:
    """Analyze team code review patterns and generate insights."""

    # Issue type keywords for classification
    ISSUE_KEYWORDS = {
        IssueType.SECURITY: [
            "安全", "security", "sql注入", "sql injection", "xss", "csrf", "认证",
            "authentication", "授权", "authorization", "密码", "password", "密钥",
            "api key", "token", "secret", "硬编码", "hardcode", "漏洞", "vulnerability"
        ],
        IssueType.PERFORMANCE: [
            "性能", "performance", "慢", "slow", "内存", "memory", "优化", "optimize",
            "缓存", "cache", "索引", "index", "查询", "query", "数据库", "database",
            "循环", "loop", "n+1", "异步", "async"
        ],
        IssueType.STYLE: [
            "风格", "style", "格式", "format", "规范", "convention", "命名", "naming",
            "代码风格", "code style", "lint", "格式化", "formatting", "缩进", "indent"
        ],
        IssueType.BUG: [
            "bug", "错误", "error", "异常", "exception", "空指针", "null", "nil",
            "undefined", "崩溃", "crash", "故障", "defect", "缺陷", "修复", "fix"
        ],
        IssueType.BEST_PRACTICE: [
            "最佳实践", "best practice", "建议", "suggestion", "改进", "improve",
            "重构", "refactor", "清理", "cleanup", "简化", "simplify"
        ],
        IssueType.DOCUMENTATION: [
            "文档", "document", "注释", "comment", "readme", "说明", "description"
        ],
    }

    def __init__(self, data_dir: Optional[str] = None):
        """Initialize TeamInsights.

        Args:
            data_dir: Directory to store/load historical PR data
        """
        self.data_dir = Path(data_dir) if data_dir else Path(".codereview-agent/insights")
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._reviews: list[dict[str, Any]] = []

    def add_review(
        self,
        pr_number: int,
        author: str,
        files: list[dict[str, Any]],
        issues: list[dict[str, Any]],
        confidence: float,
        timestamp: Optional[str] = None,
    ) -> None:
        """Add a review result to the insights data.

        Args:
            pr_number: PR number
            author: PR author username
            files: List of reviewed files with their issues
            issues: List of all issues found
            confidence: Review confidence percentage
            timestamp: ISO format timestamp (defaults to now)
        """
        review = {
            "pr_number": pr_number,
            "author": author,
            "files": files,
            "issues": issues,
            "confidence": confidence,
            "timestamp": timestamp or datetime.now().isoformat(),
        }
        self._reviews.append(review)

    def load_from_json(self, json_path: str) -> None:
        """Load reviews from a JSON file.

        Args:
            json_path: Path to JSON file containing review data
        """
        path = Path(json_path)
        if not path.exists():
            logger.warning(f"JSON file not found: {json_path}")
            return

        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            
            if isinstance(data, list):
                self._reviews.extend(data)
            elif isinstance(data, dict) and "reviews" in data:
                self._reviews.extend(data["reviews"])
            
            logger.info(f"Loaded {len(self._reviews)} reviews from {json_path}")
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON: {e}")

    def save_to_json(self, json_path: Optional[str] = None) -> str:
        """Save reviews to a JSON file.

        Args:
            json_path: Path to save JSON file (defaults to data_dir/reviews.json)

        Returns:
            Path to saved file
        """
        path = Path(json_path) if json_path else self.data_dir / "reviews.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"reviews": self._reviews}, f, ensure_ascii=False, indent=2)
        return str(path)

    def collect_insights(self) -> dict[str, Any]:
        """Collect insights from all loaded reviews.

        Returns:
            Dictionary containing collected insights
        """
        if not self._reviews:
            return {
                "total_prs": 0,
                "total_issues": 0,
                "avg_confidence": 0.0,
                "issue_types": {},
                "authors": {},
                "files": {},
                "trends": {},
            }

        # Aggregate statistics
        total_prs = len(self._reviews)
        total_issues = sum(len(r.get("issues", [])) for r in self._reviews)
        avg_confidence = sum(r.get("confidence", 0) for r in self._reviews) / total_prs if total_prs > 0 else 0

        # Count issue types
        issue_type_counts: dict[str, int] = defaultdict(int)
        issue_descriptions: dict[str, list[str]] = defaultdict(list)

        for review in self._reviews:
            for issue in review.get("issues", []):
                issue_type = self._classify_issue(issue.get("description", ""))
                issue_type_counts[issue_type] += 1
                issue_descriptions[issue_type].append(issue.get("description", ""))

        # Count by author
        author_stats: dict[str, dict[str, Any]] = defaultdict(lambda: {
            "count": 0,
            "issues": 0,
            "issue_types": defaultdict(int),
        })

        for review in self._reviews:
            author = review.get("author", "unknown")
            author_stats[author]["count"] += 1
            author_stats[author]["issues"] += len(review.get("issues", []))
            for issue in review.get("issues", []):
                issue_type = self._classify_issue(issue.get("description", ""))
                author_stats[author]["issue_types"][issue_type] += 1

        # Count by file
        file_stats: dict[str, dict[str, Any]] = defaultdict(lambda: {
            "count": 0,
            "issues": 0,
        })

        for review in self._reviews:
            for file_info in review.get("files", []):
                file_path = file_info.get("file_path", "unknown")
                file_stats[file_path]["count"] += 1
                file_stats[file_path]["issues"] += len(file_info.get("issues", []))

        # Group file paths by directory
        dir_stats: dict[str, dict[str, Any]] = defaultdict(lambda: {
            "count": 0,
            "issues": 0,
        })

        for file_path in file_stats:
            dir_path = str(Path(file_path).parent)
            dir_stats[dir_path]["count"] += file_stats[file_path]["count"]
            dir_stats[dir_path]["issues"] += file_stats[file_path]["issues"]

        # Time-based trends (monthly)
        trends: dict[str, dict[str, int]] = defaultdict(lambda: {
            "prs": 0,
            "issues": 0,
        })

        for review in self._reviews:
            timestamp = review.get("timestamp", "")
            try:
                month = timestamp[:7]  # YYYY-MM
                trends[month]["prs"] += 1
                trends[month]["issues"] += len(review.get("issues", []))
            except (ValueError, IndexError):
                continue

        return {
            "total_prs": total_prs,
            "total_issues": total_issues,
            "avg_confidence": round(avg_confidence, 1),
            "issue_types": dict(issue_type_counts),
            "issue_descriptions": {k: list(set(v)) for k, v in issue_descriptions.items()},
            "authors": dict(author_stats),
            "files": dict(file_stats),
            "directories": dict(dir_stats),
            "trends": dict(trends),
        }

    def _classify_issue(self, description: str) -> str:
        """Classify an issue based on its description.

        Args:
            description: Issue description text

        Returns:
            Issue type string
        """
        description_lower = description.lower()
        
        for issue_type, keywords in self.ISSUE_KEYWORDS.items():
            for keyword in keywords:
                if keyword in description_lower:
                    return issue_type
        
        return IssueType.OTHER

    def get_top_issues(self, limit: int = 10) -> list[dict[str, Any]]:
        """Get the most common issues.

        Args:
            limit: Maximum number of issues to return

        Returns:
            List of top issues with counts and descriptions
        """
        insights = self.collect_insights()
        issue_type_counts = insights.get("issue_types", {})
        issue_descriptions = insights.get("issue_descriptions", {})

        # Get issue type labels
        issue_labels = {
            IssueType.SECURITY: "安全问题",
            IssueType.PERFORMANCE: "性能问题",
            IssueType.STYLE: "代码风格",
            IssueType.BUG: "Bug/缺陷",
            IssueType.BEST_PRACTICE: "最佳实践",
            IssueType.DOCUMENTATION: "文档问题",
            IssueType.OTHER: "其他问题",
        }

        top_issues = []
        for issue_type, count in sorted(issue_type_counts.items(), key=lambda x: x[1], reverse=True)[:limit]:
            descriptions = issue_descriptions.get(issue_type, [])
            # Get the most common description for this type
            common_description = descriptions[0] if descriptions else issue_labels.get(issue_type, issue_type)
            
            top_issues.append({
                "type": issue_type,
                "count": count,
                "description": common_description,
                "label": issue_labels.get(issue_type, issue_type),
            })

        return top_issues

    def get_developer_stats(self) -> list[dict[str, Any]]:
        """Get statistics grouped by developer.

        Returns:
            List of developer statistics
        """
        insights = self.collect_insights()
        authors = insights.get("authors", {})

        issue_labels = {
            IssueType.SECURITY: "安全问题",
            IssueType.PERFORMANCE: "性能问题",
            IssueType.STYLE: "代码风格",
            IssueType.BUG: "Bug/缺陷",
            IssueType.BEST_PRACTICE: "最佳实践",
            IssueType.DOCUMENTATION: "文档问题",
            IssueType.OTHER: "其他问题",
        }

        developer_stats = []
        for author, stats in sorted(authors.items(), key=lambda x: x[1].get("issues", 0), reverse=True):
            # Find the most common issue type for this developer
            issue_types = stats.get("issue_types", {})
            common_type = max(issue_types.items(), key=lambda x: x[1]) if issue_types else (IssueType.OTHER, 0)
            
            developer_stats.append({
                "name": author,
                "prs": stats.get("count", 0),
                "issues": stats.get("issues", 0),
                "common": issue_labels.get(common_type[0], common_type[0]),
                "common_count": common_type[1],
                "issue_breakdown": issue_types,
            })

        return developer_stats

    def get_file_stats(self, by_directory: bool = False) -> list[dict[str, Any]]:
        """Get statistics grouped by file or directory.

        Args:
            by_directory: If True, group by directory; otherwise by file

        Returns:
            List of file/directory statistics
        """
        insights = self.collect_insights()
        
        if by_directory:
            stats = insights.get("directories", {})
        else:
            stats = insights.get("files", {})

        file_stats = []
        for path, data in sorted(stats.items(), key=lambda x: x[1].get("issues", 0), reverse=True):
            file_stats.append({
                "path": path,
                "review_count": data.get("count", 0),
                "issues": data.get("issues", 0),
            })

        return file_stats

    def generate_report(self) -> dict[str, Any]:
        """Generate a comprehensive team insights report.

        Returns:
            Dictionary containing the full report
        """
        insights = self.collect_insights()
        top_issues = self.get_top_issues(limit=5)
        developer_stats = self.get_developer_stats()
        file_stats = self.get_file_stats(by_directory=True)[:5]
        
        # Generate recommendations based on insights
        recommendations = self._generate_recommendations(insights, top_issues, developer_stats)

        return {
            "team_summary": {
                "total_prs": insights.get("total_prs", 0),
                "total_issues": insights.get("total_issues", 0),
                "avg_confidence": insights.get("avg_confidence", 0),
            },
            "top_issues": top_issues,
            "developer_stats": [
                {
                    "name": d["name"],
                    "issues": d["issues"],
                    "common": d["common"],
                }
                for d in developer_stats[:10]
            ],
            "file_stats": file_stats,
            "recommendations": recommendations,
            "trends": insights.get("trends", {}),
        }

    def _generate_recommendations(
        self,
        insights: dict[str, Any],
        top_issues: list[dict[str, Any]],
        developer_stats: list[dict[str, Any]],
    ) -> list[str]:
        """Generate recommendations based on analysis.

        Args:
            insights: Collected insights data
            top_issues: Top issues list
            developer_stats: Developer statistics

        Returns:
            List of recommendation strings
        """
        recommendations = []

        # Based on issue types
        issue_type_counts = insights.get("issue_types", {})
        
        if issue_type_counts.get(IssueType.SECURITY, 0) > 5:
            recommendations.append("建议团队培训：安全编码实践和常见漏洞防护")
        
        if issue_type_counts.get(IssueType.SECURITY, 0) > 10:
            recommendations.append("建议添加：密钥管理和环境变量最佳实践")
        
        if issue_type_counts.get(IssueType.PERFORMANCE, 0) > 5:
            recommendations.append("建议团队培训：数据库查询优化和缓存策略")
        
        if issue_type_counts.get(IssueType.PERFORMANCE, 0) > 10:
            recommendations.append("建议添加：N+1 查询检测和预加载最佳实践")
        
        if issue_type_counts.get(IssueType.STYLE, 0) > 10:
            recommendations.append("建议配置：自动代码格式化工具 (prettier, black, rustfmt)")
        
        if issue_type_counts.get(IssueType.BUG, 0) > 5:
            recommendations.append("建议添加：单元测试和集成测试覆盖")

        # Based on top issues
        for issue in top_issues:
            if issue["type"] == IssueType.SECURITY:
                if not any("安全" in r for r in recommendations):
                    recommendations.append("建议团队培训：SQL 注入防护和输入验证")
            elif issue["type"] == IssueType.PERFORMANCE:
                if not any("性能" in r or "缓存" in r for r in recommendations):
                    recommendations.append("建议审查：循环内数据库查询优化")

        # Based on developer patterns
        for dev in developer_stats[:3]:
            if dev.get("issues", 0) > 10:
                recommendations.append(f"建议关注：{dev['name']} 的代码质量，可能需要额外审查")

        # Default recommendations if none generated
        if not recommendations:
            recommendations = [
                "继续保持代码审查习惯",
                "建议定期回顾常见问题模式",
            ]

        return recommendations[:10]  # Limit to 10 recommendations

    @property
    def review_count(self) -> int:
        """Get the number of loaded reviews."""
        return len(self._reviews)


def create_team_insights(data_dir: Optional[str] = None) -> TeamInsights:
    """Factory function to create a TeamInsights instance.

    Args:
        data_dir: Directory to store/load historical PR data

    Returns:
        TeamInsights instance
    """
    return TeamInsights(data_dir=data_dir)
