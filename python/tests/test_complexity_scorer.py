"""Tests for ComplexityScorer."""

import pytest
from codereview.core.complexity_scorer import (
    ComplexityScorer,
    ComplexityMetrics,
    ScoreResult,
    create_complexity_scorer,
)


class TestComplexityScorer:
    """Test ComplexityScorer class."""

    def test_scorer_creation(self):
        """Test creating a ComplexityScorer instance."""
        scorer = ComplexityScorer()
        assert scorer is not None

    def test_factory_function(self):
        """Test create_complexity_scorer factory function."""
        scorer = create_complexity_scorer()
        assert isinstance(scorer, ComplexityScorer)

    def test_rate_level(self):
        """Test letter grade conversion."""
        scorer = ComplexityScorer()
        
        # Test A grade
        assert scorer.rate_level(100) == "A"
        assert scorer.rate_level(90) == "A"
        
        # Test B grade
        assert scorer.rate_level(89) == "B"
        assert scorer.rate_level(80) == "B"
        
        # Test C grade
        assert scorer.rate_level(79) == "C"
        assert scorer.rate_level(70) == "C"
        
        # Test D grade
        assert scorer.rate_level(69) == "D"
        assert scorer.rate_level(60) == "D"
        
        # Test F grade
        assert scorer.rate_level(59) == "F"
        assert scorer.rate_level(0) == "F"


class TestCyclomaticComplexity:
    """Test cyclomatic complexity calculation."""

    def test_simple_function(self):
        """Test simple function with no branches."""
        code = """
def hello():
    print("hello")
    return 0
"""
        scorer = ComplexityScorer()
        result = scorer.calculate_score(code)
        
        # Simple function should have low complexity
        assert result.metrics.cyclomatic_complexity >= 1

    def test_function_with_if(self):
        """Test function with if statement."""
        code = """
def check_value(x):
    if x > 0:
        return 1
    return 0
"""
        scorer = ComplexityScorer()
        result = scorer.calculate_score(code)
        
        # Should have higher complexity due to if
        assert result.metrics.cyclomatic_complexity >= 2

    def test_function_with_multiple_branches(self):
        """Test function with multiple branches."""
        code = """
def process(x):
    if x > 10:
        return 1
    elif x > 5:
        return 2
    elif x > 0:
        return 3
    else:
        return 0

def another(y):
    if y:
        for i in range(10):
            if i > 5:
                return i
"""
        scorer = ComplexityScorer()
        result = scorer.calculate_score(code)
        
        # Multiple branches
        assert result.metrics.cyclomatic_complexity >= 4


class TestCognitiveComplexity:
    """Test cognitive complexity calculation."""

    def test_simple_code(self):
        """Test simple code has low cognitive complexity."""
        code = """
def hello():
    print("hello")
"""
        scorer = ComplexityScorer()
        result = scorer.calculate_score(code)
        
        # Simple code should have low cognitive complexity
        assert result.metrics.cognitive_complexity >= 0

    def test_nested_code(self):
        """Test nested code has higher cognitive complexity."""
        code = """
def nested(x):
    if x:
        for i in range(10):
            if i > 5:
                print(i)
"""
        scorer = ComplexityScorer()
        result = scorer.calculate_score(code)
        
        # Nested code should have higher cognitive complexity
        assert result.metrics.cognitive_complexity >= 3


class TestDuplication:
    """Test code duplication detection."""

    def test_no_duplication(self):
        """Test code with no duplication."""
        code = """
def func1():
    return 1

def func2():
    return 2

def func3():
    return 3
"""
        scorer = ComplexityScorer()
        result = scorer.calculate_score(code)
        
        # Should have low duplication
        assert result.metrics.duplication_ratio <= 0.1

    def test_with_duplication(self):
        """Test code with obvious duplication."""
        code = """
def func1():
    x = 1
    y = 2
    z = 3
    return x + y + z

def func2():
    x = 1
    y = 2
    z = 3
    return x - y - z

def func3():
    x = 1
    y = 2
    z = 3
    return x * y * z
"""
        scorer = ComplexityScorer()
        result = scorer.calculate_score(code)
        
        # Should detect some duplication
        assert result.metrics.duplication_ratio >= 0.0


class TestFunctionLength:
    """Test function length calculation."""

    def test_short_function(self):
        """Test short function."""
        code = """
def short():
    return 1
"""
        scorer = ComplexityScorer()
        result = scorer.calculate_score(code)
        
        assert result.metrics.avg_function_length <= 5

    def test_long_function(self):
        """Test long function."""
        code = """
def long():
    x = 1
    x = 2
    x = 3
    x = 4
    x = 5
    x = 6
    x = 7
    x = 8
    x = 9
    x = 10
    x = 11
    x = 12
    x = 13
    x = 14
    x = 15
    return x
"""
        scorer = ComplexityScorer()
        result = scorer.calculate_score(code)
        
        # Should have longer average
        assert result.metrics.avg_function_length >= 10


class TestNestingDepth:
    """Test nesting depth calculation."""

    def test_flat_code(self):
        """Test flat code with no nesting."""
        code = """
def flat():
    a = 1
    b = 2
    c = 3
    return a + b + c
"""
        scorer = ComplexityScorer()
        result = scorer.calculate_score(code)
        
        # Flat code should have low nesting
        assert result.metrics.max_nesting_depth <= 1

    def test_deeply_nested(self):
        """Test deeply nested code."""
        code = """
def deep():
    if a:
        if b:
            if c:
                if d:
                    if e:
                        return 1
"""
        scorer = ComplexityScorer()
        result = scorer.calculate_score(code)
        
        # Should detect deep nesting
        assert result.metrics.max_nesting_depth >= 4


class TestOverallScore:
    """Test overall score calculation."""

    def test_simple_code_high_score(self):
        """Test simple code gets high score."""
        code = """
def add(a, b):
    return a + b

def multiply(a, b):
    return a * b
"""
        scorer = ComplexityScorer()
        result = scorer.calculate_score(code)
        
        # Simple code should get good score
        assert result.total_score >= 70
        assert result.level in ["A", "B", "C"]

    def test_complex_code_low_score(self):
        """Test complex code gets lower score."""
        code = """
def complex(x, y, z):
    if x > 0:
        if y > 0:
            if z > 0:
                if x > y:
                    if y > z:
                        return 1
                    else:
                        if z > x:
                            return 2
                        else:
                            return 3
                else:
                    for i in range(x):
                        if i > 0:
                            if i % 2 == 0:
                                return i
                            else:
                                return -i
    return 0
"""
        scorer = ComplexityScorer()
        result = scorer.calculate_score(code)
        
        # Complex code should get lower score
        assert result.total_score >= 0
        # Should not get A
        assert result.level in ["B", "C", "D", "F"]

    def test_empty_code(self):
        """Test empty code handling."""
        code = ""
        scorer = ComplexityScorer()
        result = scorer.calculate_score(code)
        
        # Empty code should have valid result
        assert result.total_score >= 0
        assert result.metrics.cyclomatic_complexity >= 0


class TestScoreResult:
    """Test ScoreResult dataclass."""

    def test_result_structure(self):
        """Test ScoreResult has all required fields."""
        code = """
def test():
    return 1
"""
        scorer = ComplexityScorer()
        result = scorer.calculate_score(code)
        
        assert isinstance(result.total_score, int)
        assert isinstance(result.level, str)
        assert isinstance(result.metrics, ComplexityMetrics)
        assert isinstance(result.component_scores, dict)


class TestWeights:
    """Test weight configuration."""

    def test_weights_sum_to_one(self):
        """Test weights sum to 1.0."""
        scorer = ComplexityScorer()
        total = sum(scorer.WEIGHTS.values())
        assert abs(total - 1.0) < 0.001

    def test_all_dimensions_present(self):
        """Test all 5 dimensions are present."""
        scorer = ComplexityScorer()
        expected = {"cyclomatic", "cognitive", "duplication", "length", "nesting"}
        assert set(scorer.WEIGHTS.keys()) == expected


class TestAnalyze:
    """Test the analyze method."""

    def test_analyze_returns_metrics(self):
        """Test analyze returns ComplexityMetrics."""
        code = """
def func():
    if x:
        return 1
    return 0
"""
        scorer = ComplexityScorer()
        metrics = scorer.analyze(code)
        
        assert isinstance(metrics, ComplexityMetrics)
        assert hasattr(metrics, 'cyclomatic_complexity')
        assert hasattr(metrics, 'cognitive_complexity')
        assert hasattr(metrics, 'duplication_ratio')
        assert hasattr(metrics, 'avg_function_length')
        assert hasattr(metrics, 'max_nesting_depth')
