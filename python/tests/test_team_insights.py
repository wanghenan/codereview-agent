"""Tests for Team Insights module."""

import json
import tempfile
from pathlib import Path

import pytest

from codereview.core.team_insights import (
    IssueType,
    TeamInsights,
    create_team_insights,
)

# Test constants for issue types
SECURITY_TYPE = "security"
PERFORMANCE_TYPE = "performance"
STYLE_TYPE = "style"
BUG_TYPE = "bug"
OTHER_TYPE = "other"


class TestTeamInsights:
    """Test cases for TeamInsights class."""

    def test_create_instance(self):
        """Test creating a TeamInsights instance."""
        insights = TeamInsights()
        assert insights is not None
        assert insights.review_count == 0

    def test_factory_function(self):
        """Test factory function creates correct instance."""
        insights = create_team_insights()
        assert isinstance(insights, TeamInsights)

    def test_add_review(self):
        """Test adding a single review."""
        insights = TeamInsights()
        
        insights.add_review(
            pr_number=1,
            author="zhangsan",
            files=[
                {
                    "file_path": "src/auth.py",
                    "issues": [
                        {
                            "description": "SQL注入风险 - 使用参数化查询",
                            "risk_level": "high",
                        }
                    ],
                }
            ],
            issues=[
                {
                    "description": "SQL注入风险 - 使用参数化查询",
                    "risk_level": "high",
                }
            ],
            confidence=85.0,
            timestamp="2024-01-15T10:00:00",
        )
        
        assert insights.review_count == 1

    def test_collect_insights_empty(self):
        """Test collecting insights from empty data."""
        insights = TeamInsights()
        result = insights.collect_insights()
        
        assert result["total_prs"] == 0
        assert result["total_issues"] == 0
        assert result["avg_confidence"] == 0.0

    def test_collect_insights_with_data(self):
        """Test collecting insights with sample data."""
        insights = TeamInsights()
        
        # Add multiple reviews
        insights.add_review(
            pr_number=1,
            author="zhangsan",
            files=[
                {
                    "file_path": "src/auth.py",
                    "issues": [
                        {"description": "SQL注入风险", "risk_level": "high"},
                    ],
                }
            ],
            issues=[{"description": "SQL注入风险", "risk_level": "high"}],
            confidence=90.0,
            timestamp="2024-01-15T10:00:00",
        )
        
        insights.add_review(
            pr_number=2,
            author="lisi",
            files=[
                {
                    "file_path": "src/utils.py",
                    "issues": [
                        {"description": "命名不规范", "risk_level": "low"},
                    ],
                }
            ],
            issues=[{"description": "命名不规范", "risk_level": "low"}],
            confidence=95.0,
            timestamp="2024-01-16T10:00:00",
        )
        
        result = insights.collect_insights()
        
        assert result["total_prs"] == 2
        assert result["total_issues"] == 2
        assert result["avg_confidence"] == 92.5

    def test_classify_issue_security(self):
        """Test issue classification for security issues."""
        insights = TeamInsights()
        
        assert insights._classify_issue("SQL注入风险") == SECURITY_TYPE
        assert insights._classify_issue("XSS vulnerability") == SECURITY_TYPE
        assert insights._classify_issue("硬编码密码") == SECURITY_TYPE
        assert insights._classify_issue("API key exposed") == SECURITY_TYPE

    def test_classify_issue_performance(self):
        """Test issue classification for performance issues."""
        insights = TeamInsights()
        
        assert insights._classify_issue("性能问题 - 循环内查询数据库") == PERFORMANCE_TYPE
        assert insights._classify_issue("N+1 query problem") == PERFORMANCE_TYPE
        assert insights._classify_issue("缺少缓存") == PERFORMANCE_TYPE

    def test_classify_issue_style(self):
        """Test issue classification for style issues."""
        insights = TeamInsights()
        
        assert insights._classify_issue("命名不规范") == STYLE_TYPE
        assert insights._classify_issue("代码格式不一致") == STYLE_TYPE
        assert insights._classify_issue("indent error") == STYLE_TYPE

    def test_classify_issue_bug(self):
        """Test issue classification for bug issues."""
        insights = TeamInsights()
        
        assert insights._classify_issue("空指针异常") == BUG_TYPE
        assert insights._classify_issue("可能为 null") == BUG_TYPE

    def test_classify_issue_other(self):
        """Test issue classification for uncategorized issues."""
        insights = TeamInsights()
        
        assert insights._classify_issue("一些其他问题") == OTHER_TYPE

    def test_get_top_issues(self):
        """Test getting top issues."""
        insights = TeamInsights()
        
        insights.add_review(
            pr_number=1,
            author="zhangsan",
            files=[],
            issues=[
                {"description": "SQL注入风险"},
                {"description": "XSS漏洞"},
            ],
            confidence=85.0,
        )
        
        insights.add_review(
            pr_number=2,
            author="lisi",
            files=[],
            issues=[
                {"description": "SQL注入风险"},
                {"description": "命名不规范"},
            ],
            confidence=90.0,
        )
        
        top_issues = insights.get_top_issues(limit=5)
        
        assert len(top_issues) > 0
        # Security issues: SQL注入(2次) + XSS(1次) = 3次
        assert top_issues[0]["type"] == SECURITY_TYPE
        assert top_issues[0]["count"] == 3

    def test_get_developer_stats(self):
        """Test getting developer statistics."""
        insights = TeamInsights()
        
        insights.add_review(
            pr_number=1,
            author="zhangsan",
            files=[],
            issues=[
                {"description": "SQL注入风险"},
                {"description": "空指针异常"},
                {"description": "命名不规范"},
            ],
            confidence=85.0,
        )
        
        insights.add_review(
            pr_number=2,
            author="zhangsan",
            files=[],
            issues=[{"description": "XSS漏洞"}],
            confidence=90.0,
        )
        
        insights.add_review(
            pr_number=3,
            author="lisi",
            files=[],
            issues=[{"description": "命名不规范"}],
            confidence=95.0,
        )
        
        dev_stats = insights.get_developer_stats()
        
        assert len(dev_stats) == 2
        # zhangsan should have more issues
        assert dev_stats[0]["name"] == "zhangsan"
        assert dev_stats[0]["issues"] == 4

    def test_get_file_stats(self):
        """Test getting file statistics."""
        insights = TeamInsights()
        
        insights.add_review(
            pr_number=1,
            author="zhangsan",
            files=[
                {"file_path": "src/auth.py", "issues": [{"description": "SQL注入"}]},
                {"file_path": "src/utils.py", "issues": []},
            ],
            issues=[{"description": "SQL注入"}],
            confidence=85.0,
        )
        
        insights.add_review(
            pr_number=2,
            author="lisi",
            files=[
                {"file_path": "src/auth.py", "issues": [{"description": "XSS"}]},
            ],
            issues=[{"description": "XSS"}],
            confidence=90.0,
        )
        
        file_stats = insights.get_file_stats(by_directory=False)
        
        assert len(file_stats) == 2
        # auth.py should have more issues
        assert file_stats[0]["path"] == "src/auth.py"
        assert file_stats[0]["issues"] == 2

    def test_get_file_stats_by_directory(self):
        """Test getting directory statistics."""
        insights = TeamInsights()
        
        insights.add_review(
            pr_number=1,
            author="zhangsan",
            files=[
                {"file_path": "src/auth/login.py", "issues": [{"description": "SQL注入"}]},
                {"file_path": "src/auth/user.py", "issues": []},
                {"file_path": "tests/test_auth.py", "issues": []},
            ],
            issues=[{"description": "SQL注入"}],
            confidence=85.0,
        )
        
        dir_stats = insights.get_file_stats(by_directory=True)
        
        assert any(d["path"] == "src/auth" for d in dir_stats)

    def test_generate_report(self):
        """Test generating a comprehensive report."""
        insights = TeamInsights()
        
        # Add sample data
        insights.add_review(
            pr_number=1,
            author="zhangsan",
            files=[
                {"file_path": "src/auth.py", "issues": [{"description": "SQL注入风险"}]},
            ],
            issues=[{"description": "SQL注入风险"}],
            confidence=85.0,
        )
        
        insights.add_review(
            pr_number=2,
            author="lisi",
            files=[
                {"file_path": "src/utils.py", "issues": [{"description": "命名不规范"}]},
            ],
            issues=[{"description": "命名不规范"}],
            confidence=90.0,
        )
        
        report = insights.generate_report()
        
        assert "team_summary" in report
        assert "top_issues" in report
        assert "developer_stats" in report
        assert "recommendations" in report
        
        assert report["team_summary"]["total_prs"] == 2
        assert report["team_summary"]["total_issues"] == 2
        assert report["team_summary"]["avg_confidence"] == 87.5

    def test_generate_report_recommendations(self):
        """Test that recommendations are generated correctly."""
        insights = TeamInsights()
        
        # Add multiple security issues
        for i in range(12):
            insights.add_review(
                pr_number=i,
                author="zhangsan",
                files=[],
                issues=[
                    {"description": "SQL注入风险"},
                    {"description": "硬编码密码"},
                ],
                confidence=85.0,
            )
        
        report = insights.generate_report()
        
        assert len(report["recommendations"]) > 0
        # Should have security-related recommendations
        assert any("安全" in r or "SQL" in r for r in report["recommendations"])

    def test_save_and_load_json(self):
        """Test saving and loading data from JSON."""
        insights = TeamInsights()
        
        insights.add_review(
            pr_number=1,
            author="zhangsan",
            files=[],
            issues=[{"description": "SQL注入风险"}],
            confidence=85.0,
            timestamp="2024-01-15T10:00:00",
        )
        
        with tempfile.TemporaryDirectory() as tmpdir:
            json_path = Path(tmpdir) / "test_reviews.json"
            
            # Save
            saved_path = insights.save_to_json(str(json_path))
            assert Path(saved_path).exists()
            
            # Load into new instance
            insights2 = TeamInsights()
            insights2.load_from_json(str(json_path))
            
            assert insights2.review_count == 1
            assert insights2._reviews[0]["author"] == "zhangsan"

    def test_load_from_nonexistent_file(self):
        """Test loading from nonexistent file doesn't crash."""
        insights = TeamInsights()
        insights.load_from_json("/nonexistent/path.json")
        
        assert insights.review_count == 0

    def test_empty_report(self):
        """Test generating report with no data."""
        insights = TeamInsights()
        report = insights.generate_report()
        
        assert report["team_summary"]["total_prs"] == 0
        assert report["team_summary"]["total_issues"] == 0
        assert report["team_summary"]["avg_confidence"] == 0
        assert len(report["recommendations"]) > 0  # Should have default recommendations

    def test_trends_analysis(self):
        """Test time-based trends analysis."""
        insights = TeamInsights()
        
        insights.add_review(
            pr_number=1,
            author="zhangsan",
            files=[],
            issues=[{"description": "SQL注入风险"}],
            confidence=85.0,
            timestamp="2024-01-15T10:00:00",
        )
        
        insights.add_review(
            pr_number=2,
            author="lisi",
            files=[],
            issues=[
                {"description": "SQL注入风险"},
                {"description": "命名不规范"},
            ],
            confidence=90.0,
            timestamp="2024-02-15T10:00:00",
        )
        
        insights = insights.collect_insights()
        trends = insights.get("trends", {})
        
        assert "2024-01" in trends
        assert "2024-02" in trends
        assert trends["2024-01"]["prs"] == 1
        assert trends["2024-02"]["prs"] == 1
        assert trends["2024-02"]["issues"] == 2
