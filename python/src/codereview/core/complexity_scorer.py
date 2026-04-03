"""Code Complexity Scorer - Provides code quality scoring similar to GPA."""

import ast
import re
from dataclasses import dataclass


@dataclass
class ComplexityMetrics:
    """Container for complexity metrics."""

    cyclomatic_complexity: int
    cognitive_complexity: int
    duplication_ratio: float  # 0.0 to 1.0
    avg_function_length: float
    max_nesting_depth: int


@dataclass
class ScoreResult:
    """Container for scoring results."""

    total_score: int  # 0-100
    level: str  # A/B/C/D/F
    metrics: ComplexityMetrics
    component_scores: dict  # Individual dimension scores


class ComplexityScorer:
    """
    Code Complexity Scorer - Calculates code quality scores.

    Similar to GPA, provides a score from 0-100 with letter grades.
    """

    # Weight配置
    WEIGHTS = {
        "cyclomatic": 0.30,
        "cognitive": 0.25,
        "duplication": 0.20,
        "length": 0.15,
        "nesting": 0.10,
    }

    def __init__(self):
        """Initialize the ComplexityScorer."""
        self._reset()

    def _reset(self):
        """Reset internal state."""
        self._function_bodies: list[str] = []
        self._total_lines: int = 0

    def analyze(self, code: str, language: str = "python") -> ComplexityMetrics:
        """
        Analyze code and return complexity metrics.

        Args:
            code: Source code to analyze
            language: Programming language (for future extensibility)

        Returns:
            ComplexityMetrics object with all measured values
        """
        self._reset()

        # Calculate each metric
        cyclomatic = self._calculate_cyclomatic_complexity(code)
        cognitive = self._calculate_cognitive_complexity(code)
        duplication = self._calculate_duplication_ratio(code)
        avg_length, max_nesting = self._calculate_length_and_nesting(code)

        return ComplexityMetrics(
            cyclomatic_complexity=cyclomatic,
            cognitive_complexity=cognitive,
            duplication_ratio=duplication,
            avg_function_length=avg_length,
            max_nesting_depth=max_nesting,
        )

    def calculate_score(self, code: str, language: str = "python") -> ScoreResult:
        """
        Calculate the overall complexity score (0-100).

        Args:
            code: Source code to analyze
            language: Programming language

        Returns:
            ScoreResult with total score and letter grade
        """
        metrics = self.analyze(code, language)

        # Calculate individual dimension scores (normalized to 0-100)
        cyclomatic_score = self._score_cyclomatic(metrics.cyclomatic_complexity)
        cognitive_score = self._score_cognitive(metrics.cognitive_complexity)
        duplication_score = self._score_duplication(metrics.duplication_ratio)
        length_score = self._score_length(metrics.avg_function_length)
        nesting_score = self._score_nesting(metrics.max_nesting_depth)

        # Calculate weighted total
        total_score = (
            cyclomatic_score * self.WEIGHTS["cyclomatic"]
            + cognitive_score * self.WEIGHTS["cognitive"]
            + duplication_score * self.WEIGHTS["duplication"]
            + length_score * self.WEIGHTS["length"]
            + nesting_score * self.WEIGHTS["nesting"]
        )

        total_score = round(total_score)

        component_scores = {
            "cyclomatic": cyclomatic_score,
            "cognitive": cognitive_score,
            "duplication": duplication_score,
            "length": length_score,
            "nesting": nesting_score,
        }

        return ScoreResult(
            total_score=total_score,
            level=self.rate_level(total_score),
            metrics=metrics,
            component_scores=component_scores,
        )

    def rate_level(self, score: int) -> str:
        """
        Convert numeric score to letter grade.

        Args:
            score: Score from 0-100

        Returns:
            Letter grade (A/B/C/D/F)
        """
        if score >= 90:
            return "A"
        elif score >= 80:
            return "B"
        elif score >= 70:
            return "C"
        elif score >= 60:
            return "D"
        else:
            return "F"

    def _calculate_cyclomatic_complexity(self, code: str) -> int:
        """
        Calculate cyclomatic complexity.

        Counts: if, elif, else, for, while, except, and, or, case, switch
        """
        if not code.strip():
            return 0

        try:
            tree = ast.parse(code)
        except SyntaxError:
            # Fall back to regex for non-Python or broken code
            return self._cyclomatic_regex(code)

        complexity = 1  # Base complexity

        class ComplexityVisitor(ast.NodeVisitor):
            def visit_If(self, node):
                nonlocal complexity
                complexity += 1
                self.generic_visit(node)

            def visit_For(self, node):
                nonlocal complexity
                complexity += 1
                self.generic_visit(node)

            def visit_While(self, node):
                nonlocal complexity
                complexity += 1
                self.generic_visit(node)

            def visit_ExceptHandler(self, node):
                nonlocal complexity
                complexity += 1
                self.generic_visit(node)

            def visit_BoolOp(self, node):
                nonlocal complexity
                # and/or operations add complexity
                if isinstance(node.op, (ast.And, ast.Or)):
                    complexity += len(node.values) - 1
                self.generic_visit(node)

        visitor = ComplexityVisitor()
        visitor.visit(tree)

        return complexity

    def _cyclomatic_regex(self, code: str) -> int:
        """Fallback regex-based cyclomatic complexity calculation."""
        complexity = 1
        patterns = [
            r"\bif\b",
            r"\belif\b",
            r"\bfor\b",
            r"\bwhile\b",
            r"\bexcept\b",
            r"\band\b",
            r"\bor\b",
            r"\?\s*",
        ]
        for pattern in patterns:
            complexity += len(re.findall(pattern, code))
        return complexity

    def _calculate_cognitive_complexity(self, code: str) -> int:
        """
        Calculate cognitive complexity.

        Measures how hard the code is to understand.
        """
        if not code.strip():
            return 0

        try:
            tree = ast.parse(code)
        except SyntaxError:
            return self._cognitive_regex(code)

        cognitive = 0
        nesting_level = 0

        class CognitiveVisitor(ast.NodeVisitor):
            def visit_If(self, node):
                nonlocal cognitive, nesting_level
                cognitive += 1 + nesting_level
                nesting_level += 1
                self.generic_visit(node)
                nesting_level -= 1

            def visit_For(self, node):
                nonlocal cognitive, nesting_level
                cognitive += 1 + nesting_level
                nesting_level += 1
                self.generic_visit(node)
                nesting_level -= 1

            def visit_While(self, node):
                nonlocal cognitive, nesting_level
                cognitive += 1 + nesting_level
                nesting_level += 1
                self.generic_visit(node)
                nesting_level -= 1

            def visit_With(self, node):
                nonlocal cognitive, nesting_level
                cognitive += 1 + nesting_level
                self.generic_visit(node)

            def visit_Try(self, node):
                nonlocal cognitive, nesting_level
                cognitive += 1 + nesting_level
                nesting_level += 1
                self.generic_visit(node)
                nesting_level -= 1

            def visit_TryExcept(self, node):
                nonlocal cognitive, nesting_level
                cognitive += 1 + nesting_level
                nesting_level += 1
                self.generic_visit(node)
                nesting_level -= 1

            def visit_ExceptHandler(self, node):
                nonlocal cognitive, nesting_level
                cognitive += 1 + nesting_level
                self.generic_visit(node)

            def visit_Match(self, node):
                nonlocal cognitive, nesting_level
                cognitive += 1 + nesting_level
                nesting_level += 1
                for case in node.cases:
                    cognitive += nesting_level
                    if case.pattern and hasattr(case.pattern, "patterns"):
                        for _ in case.pattern.patterns:
                            cognitive += 1
                nesting_level -= 1

        visitor = CognitiveVisitor()
        visitor.visit(tree)

        return cognitive

    def _cognitive_regex(self, code: str) -> int:
        """Fallback regex-based cognitive complexity."""
        cognitive = 0
        lines = code.split("\n")

        indent_stack = []
        for line in lines:
            if not line.strip():
                continue
            indent = len(line) - len(line.lstrip())

            # Track nesting via indent
            while indent_stack and indent <= indent_stack[-1]:
                indent_stack.pop()

            if re.search(r"\b(if|elif|for|while|except|try|with)\b", line):
                cognitive += 1 + len(indent_stack)
                indent_stack.append(indent)

            # Handle nested blocks
            if ":" in line and not line.strip().startswith("#"):
                if line.strip().endswith(":"):
                    indent_stack.append(indent)

        return cognitive

    def _calculate_duplication_ratio(self, code: str) -> float:
        """
        Calculate code duplication ratio.

        Returns ratio of duplicated lines (0.0 to 1.0).
        """
        if not code.strip():
            return 0.0

        lines = [line.strip() for line in code.split("\n") if line.strip()]
        if len(lines) < 4:
            return 0.0

        # Find duplicate lines (simple approach)
        seen = {}
        duplicates = 0

        for line in lines:
            # Normalize: remove whitespace variations
            normalized = re.sub(r"\s+", " ", line)
            if len(normalized) < 8:  # Skip short lines
                continue
            if normalized in seen:
                duplicates += 1
            else:
                seen[normalized] = True

        return min(duplicates / len(lines), 1.0)

    def _calculate_length_and_nesting(self, code: str) -> tuple[float, int]:
        """
        Calculate average function length and max nesting depth.

        Returns:
            Tuple of (avg_function_length, max_nesting_depth)
        """
        if not code.strip():
            return 0.0, 0

        try:
            tree = ast.parse(code)
        except SyntaxError:
            return self._length_nesting_regex(code)

        function_lengths = []
        max_nesting = 0

        class LengthNestingVisitor(ast.NodeVisitor):
            def __init__(self):
                super().__init__()
                self.current_nesting = 0
                self.current_length = 0
                self.in_function = False

            def visit_FunctionDef(self, node):
                nonlocal max_nesting
                old_in_function = self.in_function
                old_length = self.current_length
                old_nesting = self.current_nesting

                self.in_function = True
                self.current_length = 0

                self.generic_visit(node)

                if self.current_length > 0:
                    function_lengths.append(self.current_length)

                self.in_function = old_in_function
                self.current_length = old_length
                self.current_nesting = old_nesting

            def visit_For(self, node):
                nonlocal max_nesting
                self.current_nesting += 1
                max_nesting = max(max_nesting, self.current_nesting)
                self.current_length += 1
                self.generic_visit(node)
                self.current_nesting -= 1

            def visit_While(self, node):
                nonlocal max_nesting
                self.current_nesting += 1
                max_nesting = max(max_nesting, self.current_nesting)
                self.current_length += 1
                self.generic_visit(node)
                self.current_nesting -= 1

            def visit_If(self, node):
                nonlocal max_nesting
                self.current_nesting += 1
                max_nesting = max(max_nesting, self.current_nesting)
                self.current_length += 1
                self.generic_visit(node)
                self.current_nesting -= 1

            def visit_With(self, node):
                self.current_length += 1
                self.generic_visit(node)

            def visit_Try(self, node):
                self.current_length += 1
                self.generic_visit(node)

            def visit_ExceptHandler(self, node):
                self.current_length += 1
                self.generic_visit(node)

            def generic_visit(self, node):
                if self.in_function:
                    self.current_length += 1
                super().generic_visit(node)

        visitor = LengthNestingVisitor()
        visitor.visit(tree)

        avg_length = sum(function_lengths) / len(function_lengths) if function_lengths else 0.0

        return avg_length, max_nesting

    def _length_nesting_regex(self, code: str) -> tuple[float, int]:
        """Fallback regex-based length and nesting calculation."""
        lines = code.split("\n")
        max_nesting = 0
        current_nesting = 0
        indent_stack = []

        for line in lines:
            if not line.strip() or line.strip().startswith("#"):
                continue

            indent = len(line) - len(line.lstrip())

            while indent_stack and indent <= indent_stack[-1]:
                indent_stack.pop()
                current_nesting -= 1

            if line.strip().endswith(":"):
                indent_stack.append(indent)
                current_nesting += 1
                max_nesting = max(max_nesting, current_nesting)

        # Estimate function count
        functions = len(re.findall(r"\bdef\s+\w+\s*\(", code))
        avg_length = len(lines) / max(functions, 1)

        return avg_length, max_nesting

    # Scoring functions (normalize to 0-100, higher is better)
    def _score_cyclomatic(self, complexity: int) -> int:
        """Score cyclomatic complexity (lower is better)."""
        if complexity <= 5:
            return 100
        elif complexity <= 10:
            return 90
        elif complexity <= 15:
            return 75
        elif complexity <= 20:
            return 60
        elif complexity <= 30:
            return 40
        else:
            return 20

    def _score_cognitive(self, complexity: int) -> int:
        """Score cognitive complexity (lower is better)."""
        if complexity <= 10:
            return 100
        elif complexity <= 20:
            return 85
        elif complexity <= 40:
            return 70
        elif complexity <= 60:
            return 55
        else:
            return 35

    def _score_duplication(self, ratio: float) -> int:
        """Score code duplication (lower is better)."""
        # ratio is 0.0 to 1.0
        if ratio <= 0.03:
            return 100
        elif ratio <= 0.05:
            return 90
        elif ratio <= 0.10:
            return 75
        elif ratio <= 0.15:
            return 60
        elif ratio <= 0.25:
            return 45
        else:
            return 25

    def _score_length(self, avg_length: float) -> int:
        """Score average function length (shorter is better)."""
        if avg_length <= 10:
            return 100
        elif avg_length <= 20:
            return 90
        elif avg_length <= 30:
            return 75
        elif avg_length <= 50:
            return 60
        elif avg_length <= 80:
            return 45
        else:
            return 30

    def _score_nesting(self, max_depth: int) -> int:
        """Score maximum nesting depth (lower is better)."""
        if max_depth <= 2:
            return 100
        elif max_depth <= 3:
            return 85
        elif max_depth <= 4:
            return 70
        elif max_depth <= 5:
            return 55
        elif max_depth <= 7:
            return 40
        else:
            return 25


def create_complexity_scorer() -> ComplexityScorer:
    """Factory function to create a ComplexityScorer instance."""
    return ComplexityScorer()
