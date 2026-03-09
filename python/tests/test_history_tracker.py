"""Tests for history_tracker module."""

import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from codereview.core.history_tracker import HistoryTracker, ReviewRecord, TrendData


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_reviews.db"
        yield db_path


@pytest.fixture
def tracker(temp_db):
    """Create a HistoryTracker with temporary database."""
    return HistoryTracker(db_path=temp_db)


class TestSaveReview:
    """Tests for save_review method."""

    def test_save_review_basic(self, tracker):
        """Test saving a basic review record."""
        record_id = tracker.save_review(
            repo_name="test-repo",
            files_reviewed=5,
            total_issues=10,
            high_risk_issues=2,
            medium_risk_issues=3,
            low_risk_issues=5,
            confidence=85.0,
            conclusion="can_submit",
            review_summary="Good code quality",
        )

        assert record_id is not None
        assert record_id > 0

    def test_save_review_with_pr(self, tracker):
        """Test saving a review with PR number."""
        record_id = tracker.save_review(
            repo_name="test-repo",
            pr_number=123,
            files_reviewed=3,
            total_issues=5,
            confidence=90.0,
            conclusion="needs_review",
        )

        assert record_id is not None

    def test_save_review_default_timestamp(self, tracker):
        """Test that timestamp defaults to current time."""
        before = datetime.now().isoformat()
        record_id = tracker.save_review(
            repo_name="test-repo",
            files_reviewed=1,
            total_issues=0,
            confidence=100.0,
        )
        after = datetime.now().isoformat()

        history = tracker.get_history(limit=1)
        assert len(history) == 1
        assert history[0].timestamp >= before
        assert history[0].timestamp <= after


class TestGetHistory:
    """Tests for get_history method."""

    def test_get_history_empty(self, tracker):
        """Test getting history from empty database."""
        history = tracker.get_history(limit=10)
        assert len(history) == 0

    def test_get_history_with_records(self, tracker):
        """Test getting history with records."""
        # Save some records
        for i in range(5):
            tracker.save_review(
                repo_name=f"repo-{i}",
                files_reviewed=i + 1,
                total_issues=i * 2,
                confidence=80.0 + i,
            )

        history = tracker.get_history(limit=10)
        assert len(history) == 5

    def test_get_history_limit(self, tracker):
        """Test history limit parameter."""
        for i in range(10):
            tracker.save_review(
                repo_name=f"repo-{i}",
                files_reviewed=1,
                total_issues=0,
                confidence=90.0,
            )

        history = tracker.get_history(limit=3)
        assert len(history) == 3

    def test_get_history_by_repo(self, tracker):
        """Test filtering history by repository."""
        tracker.save_review(repo_name="specific-repo", files_reviewed=1, total_issues=0, confidence=90.0)
        tracker.save_review(repo_name="other-repo", files_reviewed=1, total_issues=0, confidence=90.0)
        tracker.save_review(repo_name="specific-repo", files_reviewed=1, total_issues=0, confidence=90.0)

        history = tracker.get_history(limit=10, repo_name="specific-repo")
        assert len(history) == 2
        assert all(r.repo_name == "specific-repo" for r in history)

    def test_get_history_by_date_range(self, tracker):
        """Test filtering history by date range."""
        # Save records with different dates
        tracker.save_review(
            repo_name="old-repo",
            files_reviewed=1,
            total_issues=0,
            confidence=90.0,
            timestamp="2024-01-01T00:00:00",
        )
        tracker.save_review(
            repo_name="new-repo",
            files_reviewed=1,
            total_issues=0,
            confidence=90.0,
            timestamp="2024-06-01T00:00:00",
        )

        history = tracker.get_history(
            limit=10,
            from_date="2024-03-01T00:00:00",
            to_date="2024-12-31T23:59:59",
        )

        assert len(history) == 1
        assert history[0].repo_name == "new-repo"


class TestGetLastReview:
    """Tests for get_last_review method."""

    def test_get_last_review_exists(self, tracker):
        """Test getting the last review."""
        tracker.save_review(repo_name="repo-1", files_reviewed=1, total_issues=0, confidence=80.0)
        tracker.save_review(repo_name="repo-2", files_reviewed=1, total_issues=0, confidence=90.0)

        last = tracker.get_last_review()
        assert last is not None
        assert last.repo_name == "repo-2"

    def test_get_last_review_none(self, tracker):
        """Test getting last review when none exist."""
        last = tracker.get_last_review()
        assert last is None


class TestAnalyzeTrends:
    """Tests for analyze_trends method."""

    def test_analyze_trends_empty(self, tracker):
        """Test trends with empty database."""
        trends = tracker.analyze_trends()
        assert len(trends) == 0

    def test_analyze_trends_monthly(self, tracker):
        """Test monthly trend analysis."""
        # Save records across months
        for month in range(1, 4):
            tracker.save_review(
                repo_name="test-repo",
                files_reviewed=5,
                total_issues=10 * month,
                confidence=80.0 + month,
                timestamp=f"2024-0{month}-15T12:00:00",
            )

        trends = tracker.analyze_trends(period="month")
        assert len(trends) == 3

    def test_analyze_trends_with_change(self, tracker):
        """Test trend change calculation."""
        tracker.save_review(
            repo_name="test-repo",
            files_reviewed=5,
            total_issues=50,
            confidence=80.0,
            timestamp="2024-01-15T12:00:00",
        )
        tracker.save_review(
            repo_name="test-repo",
            files_reviewed=5,
            total_issues=40,
            confidence=85.0,
            timestamp="2024-02-15T12:00:00",
        )

        trends = tracker.analyze_trends(period="month")
        assert len(trends) == 2
        assert trends[1].issue_trend_change < 0  # Decreased


class TestCompareWithPrevious:
    """Tests for compare_with_previous method."""

    def test_compare_insufficient_history(self, tracker):
        """Test comparison with insufficient history."""
        tracker.save_review(repo_name="test-repo", files_reviewed=1, total_issues=5, confidence=80.0)

        comparison = tracker.compare_with_previous()
        assert comparison["has_previous"] is False

    def test_compare_with_history(self, tracker):
        """Test comparison with previous review."""
        tracker.save_review(repo_name="test-repo", files_reviewed=1, total_issues=10, confidence=80.0)
        tracker.save_review(repo_name="test-repo", files_reviewed=1, total_issues=5, confidence=85.0)

        comparison = tracker.compare_with_previous()
        assert comparison["has_previous"] is True
        assert comparison["issue_change"] == -5  # 5 - 10
        assert comparison["confidence_change"] == 5.0  # 85 - 80


class TestExport:
    """Tests for export methods."""

    def test_export_json(self, tracker, temp_db):
        """Test JSON export."""
        tracker.save_review(repo_name="repo-1", files_reviewed=1, total_issues=5, confidence=80.0)
        tracker.save_review(repo_name="repo-2", files_reviewed=2, total_issues=3, confidence=90.0)

        output_path = temp_db.parent / "exports" / "reviews.json"
        count = tracker.export_json(output_path)

        assert count == 2
        assert output_path.exists()

        with open(output_path) as f:
            data = json.load(f)
            assert len(data) == 2
            assert data[0]["repo_name"] == "repo-1"

    def test_export_csv(self, tracker, temp_db):
        """Test CSV export."""
        tracker.save_review(repo_name="repo-1", files_reviewed=1, total_issues=5, confidence=80.0)
        tracker.save_review(repo_name="repo-2", files_reviewed=2, total_issues=3, confidence=90.0)

        output_path = temp_db.parent / "exports" / "reviews.csv"
        count = tracker.export_csv(output_path)

        assert count == 2
        assert output_path.exists()

        with open(output_path) as f:
            lines = f.readlines()
            assert len(lines) == 3  # Header + 2 data rows


class TestGetStatistics:
    """Tests for get_statistics method."""

    def test_get_statistics_empty(self, tracker):
        """Test statistics with empty database."""
        stats = tracker.get_statistics()
        assert stats["total_reviews"] == 0
        assert stats["total_issues"] == 0
        assert stats["avg_confidence"] == 0.0

    def test_get_statistics_with_data(self, tracker):
        """Test statistics with data."""
        tracker.save_review(
            repo_name="repo-1",
            files_reviewed=5,
            total_issues=10,
            high_risk_issues=2,
            medium_risk_issues=3,
            low_risk_issues=5,
            confidence=85.0,
        )
        tracker.save_review(
            repo_name="repo-2",
            files_reviewed=3,
            total_issues=5,
            high_risk_issues=1,
            medium_risk_issues=2,
            low_risk_issues=2,
            confidence=90.0,
        )

        stats = tracker.get_statistics()
        assert stats["total_reviews"] == 2
        assert stats["total_issues"] == 15
        assert stats["avg_confidence"] == 87.5
        assert stats["total_high_risk"] == 3


class TestFormatTrendReport:
    """Tests for format_trend_report method."""

    def test_format_trend_report_empty(self, tracker):
        """Test formatting report with no data."""
        report = tracker.format_trend_report()
        assert "No review history found" in report

    def test_format_trend_report_with_data(self, tracker):
        """Test formatting report with data."""
        tracker.save_review(
            repo_name="test-repo",
            files_reviewed=5,
            total_issues=10,
            confidence=80.0,
            timestamp="2024-01-15T12:00:00",
        )
        tracker.save_review(
            repo_name="test-repo",
            files_reviewed=5,
            total_issues=8,
            confidence=85.0,
            timestamp="2024-02-15T12:00:00",
        )
        tracker.save_review(
            repo_name="test-repo",
            files_reviewed=5,
            total_issues=5,
            confidence=90.0,
            timestamp="2024-03-15T12:00:00",
        )

        report = tracker.format_trend_report(period="month")
        assert "趋势分析" in report
        assert "审查总数:" in report
        assert "问题总数:" in report
        assert "平均置信度:" in report
        assert "问题趋势:" in report
        assert "置信度趋势:" in report


class TestReviewRecord:
    """Tests for ReviewRecord dataclass."""

    def test_review_record_creation(self):
        """Test creating a ReviewRecord."""
        record = ReviewRecord(
            id=1,
            timestamp="2024-01-01T00:00:00",
            repo_name="test-repo",
            pr_number=123,
            files_reviewed=5,
            total_issues=10,
            high_risk_issues=2,
            medium_risk_issues=3,
            low_risk_issues=5,
            confidence=85.0,
            conclusion="can_submit",
            review_summary="Good code",
        )

        assert record.id == 1
        assert record.repo_name == "test-repo"
        assert record.total_issues == 10


class TestTrendData:
    """Tests for TrendData dataclass."""

    def test_trend_data_creation(self):
        """Test creating a TrendData."""
        trend = TrendData(
            period="2024-01",
            review_count=10,
            total_issues=50,
            avg_confidence=85.0,
            high_risk_count=5,
            issue_trend_change=-10.0,
        )

        assert trend.period == "2024-01"
        assert trend.review_count == 10
        assert trend.issue_trend_change == -10.0
