"""Tests for multi-language health check module."""

import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

# Import language analyzers directly to avoid core/__init__.py imports
from codereview.core.languages.go.analyzer import GoAnalyzer
from codereview.core.languages.java.analyzer import JavaAnalyzer
from codereview.core.languages.rust.analyzer import RustAnalyzer
from codereview.core.languages.cpp.analyzer import CppAnalyzer
from codereview.core.languages.php.analyzer import PhpAnalyzer
from codereview.core.languages.ruby.analyzer import RubyAnalyzer
from codereview.core.languages.csharp.analyzer import CSharpAnalyzer
from codereview.core.languages import (
    detect_language,
    get_supported_languages,
    LanguageIssue,
    LanguageAnalysisResult,
)


# Patch the get_analyzer to avoid circular imports
import codereview.core.languages as languages_module


def get_analyzer(lang):
    """Get analyzer for a language."""
    analyzers = {
        "go": GoAnalyzer,
        "java": JavaAnalyzer,
        "rust": RustAnalyzer,
        "cpp": CppAnalyzer,
        "php": PhpAnalyzer,
        "ruby": RubyAnalyzer,
        "csharp": CSharpAnalyzer,
    }
    if lang in analyzers:
        return analyzers[lang](lang)
    return None


def analyze_file(content, file_path, language=None):
    """Analyze a file."""
    if language is None:
        language = detect_language(file_path)
    if language:
        analyzer = get_analyzer(language)
        if analyzer:
            return analyzer.analyze(content, file_path)
    return None


import pytest


class TestLanguageDetection:
    """Test language detection from file extensions."""

    def test_detect_python(self):
        """Test Python file detection."""
        assert detect_language("test.py") == "python"
        assert detect_language("main.pyw") == "python"

    def test_detect_javascript(self):
        """Test JavaScript file detection."""
        assert detect_language("app.js") == "javascript"
        assert detect_language("component.jsx") == "javascript"
        assert detect_language("index.mjs") == "javascript"

    def test_detect_typescript(self):
        """Test TypeScript file detection."""
        assert detect_language("app.ts") == "typescript"
        assert detect_language("component.tsx") == "typescript"

    def test_detect_go(self):
        """Test Go file detection."""
        assert detect_language("main.go") == "go"

    def test_detect_java(self):
        """Test Java file detection."""
        assert detect_language("Main.java") == "java"

    def test_detect_rust(self):
        """Test Rust file detection."""
        assert detect_language("main.rs") == "rust"

    def test_detect_cpp(self):
        """Test C++ file detection."""
        assert detect_language("main.cpp") == "cpp"
        assert detect_language("header.hh") == "cpp"
        assert detect_language("source.cc") == "cpp"

    def test_detect_php(self):
        """Test PHP file detection."""
        assert detect_language("index.php") == "php"

    def test_detect_ruby(self):
        """Test Ruby file detection."""
        assert detect_language("script.rb") == "ruby"

    def test_detect_csharp(self):
        """Test C# file detection."""
        assert detect_language("Program.cs") == "csharp"

    def test_unknown_extension(self):
        """Test unknown file extension."""
        assert detect_language("unknown.xyz") is None


class TestSupportedLanguages:
    """Test supported languages listing."""

    def test_get_supported_languages(self):
        """Test getting supported languages."""
        languages = get_supported_languages()
        assert "python" in languages
        assert "javascript" in languages
        assert "go" in languages
        assert "java" in languages
        assert "rust" in languages
        assert "cpp" in languages
        assert "php" in languages
        assert "ruby" in languages
        assert "csharp" in languages


class TestGoAnalyzer:
    """Test Go language analyzer."""

    def test_get_go_analyzer(self):
        """Test getting Go analyzer."""
        analyzer = get_analyzer("go")
        assert analyzer is not None
        assert analyzer.language == "go"

    def test_go_rules_exist(self):
        """Test that Go rules are defined."""
        analyzer = get_analyzer("go")
        rules = analyzer.get_rules()
        assert len(rules) > 0

    def test_go_analyze_with_issues(self):
        """Test Go analyzer detects issues."""
        code = """
package main

import "fmt"

func main() {
    go func() {
        for {
            fmt.Println("loop")
        }
    }()
}
"""
        result = analyze_file(code, "main.go")
        assert result is not None
        assert result.language == "go"
        assert len(result.issues) > 0

    def test_go_health_score(self):
        """Test Go health score calculation."""
        code = "package main\n\nfunc main() {}"
        result = analyze_file(code, "main.go")
        assert result is not None
        assert result.health_score >= 0


class TestJavaAnalyzer:
    """Test Java language analyzer."""

    def test_get_java_analyzer(self):
        """Test getting Java analyzer."""
        analyzer = get_analyzer("java")
        assert analyzer is not None
        assert analyzer.language == "java"

    def test_java_rules_exist(self):
        """Test that Java rules are defined."""
        analyzer = get_analyzer("java")
        rules = analyzer.get_rules()
        assert len(rules) > 0

    def test_java_analyze_with_issues(self):
        """Test Java analyzer detects issues."""
        code = """
public class Main {
    public static void main(String[] args) {
        String password = "hardcoded";
    }
}
"""
        result = analyze_file(code, "Main.java")
        assert result is not None
        assert len(result.issues) > 0


class TestRustAnalyzer:
    """Test Rust language analyzer."""

    def test_get_rust_analyzer(self):
        """Test getting Rust analyzer."""
        analyzer = get_analyzer("rust")
        assert analyzer is not None
        assert analyzer.language == "rust"

    def test_rust_rules_exist(self):
        """Test that Rust rules are defined."""
        analyzer = get_analyzer("rust")
        rules = analyzer.get_rules()
        assert len(rules) > 0


class TestCppAnalyzer:
    """Test C++ language analyzer."""

    def test_get_cpp_analyzer(self):
        """Test getting C++ analyzer."""
        analyzer = get_analyzer("cpp")
        assert analyzer is not None
        assert analyzer.language == "cpp"

    def test_cpp_rules_exist(self):
        """Test that C++ rules are defined."""
        analyzer = get_analyzer("cpp")
        rules = analyzer.get_rules()
        assert len(rules) > 0


class TestPhpAnalyzer:
    """Test PHP language analyzer."""

    def test_get_php_analyzer(self):
        """Test getting PHP analyzer."""
        analyzer = get_analyzer("php")
        assert analyzer is not None
        assert analyzer.language == "php"

    def test_php_rules_exist(self):
        """Test that PHP rules are defined."""
        analyzer = get_analyzer("php")
        rules = analyzer.get_rules()
        assert len(rules) > 0

    def test_php_analyze_with_issues(self):
        """Test PHP analyzer detects issues."""
        code = """
<?php
$password = "secret123";
$sql = "SELECT * FROM users WHERE id=" . $_GET['id'];
echo $_GET['name'];
?>
"""
        result = analyze_file(code, "index.php")
        assert result is not None
        assert len(result.issues) > 0


class TestRubyAnalyzer:
    """Test Ruby language analyzer."""

    def test_get_ruby_analyzer(self):
        """Test getting Ruby analyzer."""
        analyzer = get_analyzer("ruby")
        assert analyzer is not None
        assert analyzer.language == "ruby"

    def test_ruby_rules_exist(self):
        """Test that Ruby rules are defined."""
        analyzer = get_analyzer("ruby")
        rules = analyzer.get_rules()
        assert len(rules) > 0


class TestCSharpAnalyzer:
    """Test C# language analyzer."""

    def test_get_csharp_analyzer(self):
        """Test getting C# analyzer."""
        analyzer = get_analyzer("csharp")
        assert analyzer is not None
        assert analyzer.language == "csharp"

    def test_csharp_rules_exist(self):
        """Test that C# rules are defined."""
        analyzer = get_analyzer("csharp")
        rules = analyzer.get_rules()
        assert len(rules) > 0


class TestLanguageIssue:
    """Test LanguageIssue dataclass."""

    def test_create_issue(self):
        """Test creating a language issue."""
        issue = LanguageIssue(
            rule_id="TEST-001",
            rule_name="Test Rule",
            line_number=10,
            severity="high",
            description="Test description",
            suggestion="Fix this",
            language="python",
        )
        assert issue.rule_id == "TEST-001"
        assert issue.severity == "high"
        assert issue.language == "python"


class TestLanguageAnalysisResult:
    """Test LanguageAnalysisResult dataclass."""

    def test_create_result(self):
        """Test creating a language analysis result."""
        result = LanguageAnalysisResult(
            language="python",
            file_path="test.py",
            issues=[],
            health_score=100.0,
            summary="No issues found",
        )
        assert result.language == "python"
        assert result.health_score == 100.0

    def test_result_with_issues(self):
        """Test result with issues."""
        issue = LanguageIssue(
            rule_id="TEST-001",
            rule_name="Test",
            line_number=1,
            severity="high",
            description="Issue",
            suggestion="Fix",
            language="python",
        )
        result = LanguageAnalysisResult(
            language="python",
            file_path="test.py",
            issues=[issue],
            health_score=90.0,
        )
        assert len(result.issues) == 1
        assert result.health_score == 90.0
