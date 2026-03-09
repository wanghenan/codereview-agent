"""History tracker for code review analysis and trends."""

from __future__ import annotations

import csv
import json
import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Default database path
DEFAULT_DB_PATH = Path.home() / ".codereview-agent" / "reviews.db"


@dataclass
class ReviewRecord:
    """A single review record."""

    id: Optional[int] = None
    timestamp: str = ""
    repo_name: str = ""
    pr_number: Optional[int] = None
    files_reviewed: int = 0
    total_issues: int = 0
    high_risk_issues: int = 0
    medium_risk_issues: int = 0
    low_risk_issues: int = 0
    confidence: float = 0.0
    conclusion: str = ""
    review_summary: str = ""


@dataclass
class TrendData:
    """Trend analysis data."""

    period: str
    review_count: int = 0
    total_issues: int = 0
    avg_confidence: float = 0.0
    high_risk_count: int = 0
    issue_trend_change: float = 0.0  # percentage change from previous period


class HistoryTracker:
    """Track and analyze code review history."""

    def __init__(self, db_path: Optional[Path] = None):
        """Initialize history tracker.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path or DEFAULT_DB_PATH
        self._ensure_db_dir()
        self._init_db()

    def _ensure_db_dir(self) -> None:
        """Ensure database directory exists."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def _init_db(self) -> None:
        """Initialize database schema."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                repo_name TEXT NOT NULL,
                pr_number INTEGER,
                files_reviewed INTEGER DEFAULT 0,
                total_issues INTEGER DEFAULT 0,
                high_risk_issues INTEGER DEFAULT 0,
                medium_risk_issues INTEGER DEFAULT 0,
                low_risk_issues INTEGER DEFAULT 0,
                confidence REAL DEFAULT 0.0,
                conclusion TEXT,
                review_summary TEXT
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_timestamp ON reviews(timestamp)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_repo ON reviews(repo_name)
        """)

        conn.commit()
        conn.close()

    def _get_connection(self) -> sqlite3.Connection:
        """Get database connection."""
        return sqlite3.connect(str(self.db_path))

    def save_review(
        self,
        repo_name: str,
        files_reviewed: int,
        total_issues: int,
        high_risk_issues: int = 0,
        medium_risk_issues: int = 0,
        low_risk_issues: int = 0,
        confidence: float = 0.0,
        conclusion: str = "",
        review_summary: str = "",
        pr_number: Optional[int] = None,
        timestamp: Optional[str] = None,
    ) -> int:
        """Save a review record.

        Args:
            repo_name: Repository name
            files_reviewed: Number of files reviewed
            total_issues: Total number of issues found
            high_risk_issues: Number of high risk issues
            medium_risk_issues: Number of medium risk issues
            low_risk_issues: Number of low risk issues
            confidence: Confidence percentage (0-100)
            conclusion: Review conclusion
            review_summary: Summary of the review
            pr_number: Pull request number
            timestamp: Review timestamp (ISO format), defaults to now

        Returns:
            Record ID
        """
        timestamp = timestamp or datetime.now().isoformat()

        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO reviews (
                timestamp, repo_name, pr_number, files_reviewed,
                total_issues, high_risk_issues, medium_risk_issues,
                low_risk_issues, confidence, conclusion, review_summary
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                timestamp,
                repo_name,
                pr_number,
                files_reviewed,
                total_issues,
                high_risk_issues,
                medium_risk_issues,
                low_risk_issues,
                confidence,
                conclusion,
                review_summary,
            ),
        )

        record_id = cursor.lastrowid
        conn.commit()
        conn.close()

        logger.info(f"Saved review record {record_id} for {repo_name}")
        return record_id

    def get_history(
        self,
        limit: int = 10,
        repo_name: Optional[str] = None,
        file_path: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
    ) -> list[ReviewRecord]:
        """Get review history.

        Args:
            limit: Maximum number of records to return
            repo_name: Filter by repository name
            file_path: Filter by file path (not stored, kept for API compatibility)
            from_date: Start date (ISO format)
            to_date: End date (ISO format)

        Returns:
            List of review records
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        query = "SELECT * FROM reviews WHERE 1=1"
        params = []

        if repo_name:
            query += " AND repo_name = ?"
            params.append(repo_name)

        if from_date:
            query += " AND timestamp >= ?"
            params.append(from_date)

        if to_date:
            query += " AND timestamp <= ?"
            params.append(to_date)

        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        records = []
        for row in rows:
            records.append(
                ReviewRecord(
                    id=row[0],
                    timestamp=row[1],
                    repo_name=row[2],
                    pr_number=row[3],
                    files_reviewed=row[4],
                    total_issues=row[5],
                    high_risk_issues=row[6],
                    medium_risk_issues=row[7],
                    low_risk_issues=row[8],
                    confidence=row[9],
                    conclusion=row[10] or "",
                    review_summary=row[11] or "",
                )
            )

        return records

    def get_last_review(self, repo_name: Optional[str] = None) -> Optional[ReviewRecord]:
        """Get the most recent review.

        Args:
            repo_name: Optional repository filter

        Returns:
            Most recent review record or None
        """
        records = self.get_history(limit=1, repo_name=repo_name)
        return records[0] if records else None

    def analyze_trends(
        self,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        period: str = "month",
        repo_name: Optional[str] = None,
    ) -> list[TrendData]:
        """Analyze review trends.

        Args:
            from_date: Start date (ISO format). If None, uses all data.
            to_date: End date (ISO format). If None, uses all data.
            period: Trend period ('week' or 'month')
            repo_name: Optional repository filter

        Returns:
            List of trend data by period
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        query = """
            SELECT 
                timestamp, repo_name,
                COUNT(*) as review_count,
                SUM(total_issues) as total_issues,
                AVG(confidence) as avg_confidence,
                SUM(high_risk_issues) as high_risk_count
            FROM reviews
            WHERE 1=1
        """
        params = []

        if from_date:
            query += " AND timestamp >= ?"
            params.append(from_date)

        if to_date:
            query += " AND timestamp <= ?"
            params.append(to_date)

        if repo_name:
            query += " AND repo_name = ?"
            params.append(repo_name)

        query += " GROUP BY "

        if period == "week":
            query += "strftime('%Y-W%W', timestamp)"
        else:  # month
            query += "strftime('%Y-%m', timestamp)"

        query += " ORDER BY timestamp"

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        trends = []
        previous_issues = 0

        for i, row in enumerate(rows):
            period_str = row[1] if period == "repo" else (row[0][:7] if period == "month" else row[0][:10])
            review_count = row[2]
            total_issues = row[3] or 0
            avg_confidence = row[4] or 0.0
            high_risk_count = row[5] or 0

            # Calculate trend change
            if previous_issues > 0:
                change = ((total_issues - previous_issues) / previous_issues) * 100
            else:
                change = 0.0

            trends.append(
                TrendData(
                    period=period_str,
                    review_count=review_count,
                    total_issues=total_issues,
                    avg_confidence=round(avg_confidence, 1),
                    high_risk_count=high_risk_count,
                    issue_trend_change=round(change, 1),
                )
            )

            previous_issues = total_issues

        return trends

    def compare_with_previous(self, repo_name: Optional[str] = None) -> dict[str, Any]:
        """Compare current review with previous.

        Args:
            repo_name: Optional repository filter

        Returns:
            Comparison data
        """
        records = self.get_history(limit=2, repo_name=repo_name)

        if len(records) < 2:
            return {
                "has_previous": False,
                "message": "Not enough history for comparison",
            }

        current = records[0]
        previous = records[1]

        return {
            "has_previous": True,
            "current": {
                "timestamp": current.timestamp,
                "total_issues": current.total_issues,
                "confidence": current.confidence,
            },
            "previous": {
                "timestamp": previous.timestamp,
                "total_issues": previous.total_issues,
                "confidence": previous.confidence,
            },
            "issue_change": current.total_issues - previous.total_issues,
            "confidence_change": current.confidence - previous.confidence,
        }

    def export_json(self, filepath: Path, from_date: Optional[str] = None, to_date: Optional[str] = None) -> int:
        """Export review history to JSON.

        Args:
            filepath: Output file path
            from_date: Start date filter
            to_date: End date filter

        Returns:
            Number of records exported
        """
        records = self.get_history(limit=10000, from_date=from_date, to_date=to_date)

        # Reverse to get chronological order (oldest first)
        records = list(reversed(records))

        data = [
            {
                "id": r.id,
                "timestamp": r.timestamp,
                "repo_name": r.repo_name,
                "pr_number": r.pr_number,
                "files_reviewed": r.files_reviewed,
                "total_issues": r.total_issues,
                "high_risk_issues": r.high_risk_issues,
                "medium_risk_issues": r.medium_risk_issues,
                "low_risk_issues": r.low_risk_issues,
                "confidence": r.confidence,
                "conclusion": r.conclusion,
                "review_summary": r.review_summary,
            }
            for r in records
        ]

        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        logger.info(f"Exported {len(data)} records to {filepath}")
        return len(data)

    def export_csv(self, filepath: Path, from_date: Optional[str] = None, to_date: Optional[str] = None) -> int:
        """Export review history to CSV.

        Args:
            filepath: Output file path
            from_date: Start date filter
            to_date: End date filter

        Returns:
            Number of records exported
        """
        records = self.get_history(limit=10000, from_date=from_date, to_date=to_date)

        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    "id",
                    "timestamp",
                    "repo_name",
                    "pr_number",
                    "files_reviewed",
                    "total_issues",
                    "high_risk_issues",
                    "medium_risk_issues",
                    "low_risk_issues",
                    "confidence",
                    "conclusion",
                    "review_summary",
                ]
            )

            for r in records:
                writer.writerow(
                    [
                        r.id,
                        r.timestamp,
                        r.repo_name,
                        r.pr_number,
                        r.files_reviewed,
                        r.total_issues,
                        r.high_risk_issues,
                        r.medium_risk_issues,
                        r.low_risk_issues,
                        r.confidence,
                        r.conclusion,
                        r.review_summary,
                    ]
                )

        logger.info(f"Exported {len(records)} records to {filepath}")
        return len(records)

    def get_statistics(self, repo_name: Optional[str] = None) -> dict[str, Any]:
        """Get overall statistics.

        Args:
            repo_name: Optional repository filter

        Returns:
            Statistics dictionary
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        query = """
            SELECT 
                COUNT(*) as total_reviews,
                SUM(total_issues) as total_issues,
                AVG(confidence) as avg_confidence,
                SUM(high_risk_issues) as total_high_risk,
                SUM(medium_risk_issues) as total_medium_risk,
                SUM(low_risk_issues) as total_low_risk
            FROM reviews
        """
        params = []

        if repo_name:
            query += " WHERE repo_name = ?"
            params.append(repo_name)

        cursor.execute(query, params)
        row = cursor.fetchone()
        conn.close()

        return {
            "total_reviews": row[0] or 0,
            "total_issues": row[1] or 0,
            "avg_confidence": round(row[2] or 0, 1),
            "total_high_risk": row[3] or 0,
            "total_medium_risk": row[4] or 0,
            "total_low_risk": row[5] or 0,
        }

    def format_trend_report(
        self,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        period: str = "month",
    ) -> str:
        """Format trend analysis as a readable report.

        Args:
            from_date: Start date
            to_date: End date
            period: Trend period ('week' or 'month')

        Returns:
            Formatted report string
        """
        trends = self.analyze_trends(from_date=from_date, to_date=to_date, period=period)
        stats = self.get_statistics()

        if not trends:
            return "No review history found for the specified period."

        # Build header
        from_str = from_date[:10] if from_date else "3 months ago"
        to_str = to_date[:10] if to_date else "now"
        report = f"📈 趋势分析 ({from_str} - {to_str})\n\n"

        # Summary statistics
        report += f"审查总数: {stats['total_reviews']} 次\n"
        report += f"问题总数: {stats['total_issues']} 个\n"
        report += f"平均置信度: {stats['avg_confidence']}%\n\n"

        # Issue trend
        report += "问题趋势:\n"
        for trend in reversed(trends):
            bar_len = min(int(trend.total_issues / 5), 20)  # Scale bar
            bar = "█" * bar_len
            change_str = ""
            if trend.issue_trend_change != 0:
                direction = "↓" if trend.issue_trend_change < 0 else "↑"
                change_str = f" {direction}{abs(trend.issue_trend_change):.0f}%"

            report += f"{trend.period}: {bar} {trend.total_issues}{change_str}\n"

        report += "\n置信度趋势:\n"
        for trend in reversed(trends):
            trend_indicator = ""
            if trends.index(trend) > 0:
                prev = trends[trends.index(trend) - 1]
                if trend.avg_confidence > prev.avg_confidence:
                    trend_indicator = " ↑"
                elif trend.avg_confidence < prev.avg_confidence:
                    trend_indicator = " ↓"

            report += f"{trend.period}: {trend.avg_confidence}%{trend_indicator}\n"

        return report


# CLI helper function
def create_tracker(db_path: Optional[Path] = None) -> HistoryTracker:
    """Create a HistoryTracker instance.

    Args:
        db_path: Optional database path

    Returns:
        HistoryTracker instance
    """
    return HistoryTracker(db_path)
