"""Project Analyzer Agent using LangGraph.

This agent analyzes the project structure and generates context
for the code review process.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import END, StateGraph

from codereview.models import Config, ProjectContext

logger = logging.getLogger(__name__)


# State for the analyzer agent
class AnalyzerState(dict):
    """State for project analyzer agent."""

    config: Config
    root_dir: Path
    files_info: str = ""
    project_context: ProjectContext | None = None
    analysis_complete: bool = False


# System prompt for project analysis
ANALYZER_SYSTEM_PROMPT = """You are a project analysis expert. Your task is to analyze the project structure
and provide a comprehensive summary that will help with code review.

Analyze the following aspects:
1. Tech stack (languages, frameworks)
2. Dependencies and package managers
3. Code style conventions (linters, formatters)
4. Directory structure and key modules
5. Critical paths (auth, payment, admin, etc.)

Provide your analysis in JSON format with the following structure:
{
    "tech_stack": ["language1", "framework1"],
    "language": "primary language",
    "frameworks": ["framework1", "framework2"],
    "dependencies": {"package1": "version1"},
    "critical_paths": ["src/auth", "src/payment"],
    "code_style": "description of code style",
    "directory_structure": "tree structure description",
    "linter_config": {"linter": "config"}
}

Be thorough but concise. Focus on what's relevant for code review."""


class ProjectAnalyzer:
    """LangGraph-based project analyzer agent."""

    def __init__(self, config: Config, llm: Any):
        """Initialize analyzer.

        Args:
            config: Agent configuration
            llm: LangChain LLM instance
        """
        self.config = config
        self.llm = llm

    async def analyze(self, root_dir: Path) -> ProjectContext:
        """Analyze the project using LangGraph workflow.

        Args:
            root_dir: Project root directory

        Returns:
            Project context with analysis results
        """
        # Build and run the graph
        graph = self.create_graph()

        initial_state = AnalyzerState(
            config=self.config,
            root_dir=root_dir,
            project_context=None,
            analysis_complete=False,
        )

        result_state = await graph.ainvoke(initial_state)
        context = result_state.get("project_context")

        if context is None:
            # Fallback: run without graph
            files_info = self._collect_files_info(root_dir)
            context = await self._llm_analyze(files_info, root_dir)

        # Add user-configured critical paths
        context.critical_paths.extend(self.config.critical_paths)
        context.critical_paths = list(set(context.critical_paths))

        return context

    def _collect_files_info(self, root_dir: Path) -> str:
        """Collect basic file information from the project.

        Reads actual config file contents (not just existence) so the LLM
        can produce meaningful analysis.

        Args:
            root_dir: Project root

        Returns:
            Formatted string with file info
        """
        info_parts = []

        # Read actual config file contents for meaningful analysis
        config_readers = {
            "package.json": self._read_json_keys,
            "pyproject.toml": self._read_toml_content,
            "tsconfig.json": self._read_json_keys,
            "go.mod": self._read_first_lines,
            "Cargo.toml": self._read_first_lines,
            "pom.xml": self._read_first_lines,
            "requirements.txt": self._read_first_lines,
            "next.config.js": self._read_first_lines,
            "vite.config.ts": self._read_first_lines,
        }

        for cf, reader in config_readers.items():
            path = root_dir / cf
            if path.exists():
                content = reader(path)
                if content:
                    info_parts.append(f"=== {cf} ===\n{content}")

        # Also check for linter/formatter configs (existence only)
        for cf in [".eslintrc", ".eslintrc.js", ".eslintrc.json", ".prettierrc", ".prettierrc.js"]:
            path = root_dir / cf
            if path.exists():
                info_parts.append(f"Found linter/formatter: {cf}")

        # List top-level directories
        if root_dir.exists():
            dirs = [d.name for d in root_dir.iterdir() if d.is_dir() and not d.name.startswith(".")]
            if dirs:
                info_parts.append(f"Top-level directories: {', '.join(dirs[:10])}")

        return "\n\n".join(info_parts) if info_parts else "No config files found"

    @staticmethod
    def _read_json_keys(path: Path) -> str:
        """Read key fields from a JSON config file."""
        try:
            import json as json_mod

            with open(path) as f:
                data = json_mod.load(f)
            # Extract only relevant keys
            keys_to_extract = ["name", "version", "dependencies", "devDependencies", "scripts"]
            parts = []
            for key in keys_to_extract:
                if key in data:
                    val = data[key]
                    if isinstance(val, dict):
                        items = list(val.items())[:15]
                        parts.append(f"{key}: {json_mod.dumps(dict(items), indent=2)}")
                    else:
                        parts.append(f"{key}: {val}")
            return "\n".join(parts)
        except Exception:
            return ""

    @staticmethod
    def _read_toml_content(path: Path) -> str:
        """Read key sections from a TOML config file."""
        try:
            with open(path) as f:
                content = f.read()
            # Only include first 40 lines to keep it manageable
            lines = content.splitlines()[:40]
            return "\n".join(lines)
        except Exception:
            return ""

    @staticmethod
    def _read_first_lines(path: Path, limit: int = 20) -> str:
        """Read first N lines from a file."""
        try:
            with open(path) as f:
                lines = [line.rstrip() for line in f.readlines()[:limit]]
            return "\n".join(lines)
        except Exception:
            return ""

    async def _llm_analyze(self, files_info: str, root_dir: Path) -> ProjectContext:
        """Use LLM to analyze the project.

        Args:
            files_info: Collected file information
            root_dir: Project root

        Returns:
            Project context
        """
        from datetime import datetime

        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", ANALYZER_SYSTEM_PROMPT),
                ("user", "Project files:\n{files_info}\n\nRoot directory: {root_dir}"),
            ]
        )

        # Create chain
        chain = prompt | self.llm | JsonOutputParser()

        try:
            result = await chain.ainvoke({"files_info": files_info, "root_dir": str(root_dir)})

            return ProjectContext(
                tech_stack=result.get("tech_stack", []),
                language=result.get("language"),
                frameworks=result.get("frameworks", []),
                dependencies=result.get("dependencies", {}),
                critical_paths=result.get("critical_paths", []),
                code_style=result.get("code_style"),
                directory_structure=result.get("directory_structure"),
                linter_config=result.get("linter_config"),
                version="1.0.0",  # Will be updated by cache manager
                analyzed_at=datetime.now().isoformat(),
            )
        except Exception:
            logger.warning("Failed to analyze project context, using defaults")
            return ProjectContext(
                tech_stack=["unknown"],
                language="unknown",
                frameworks=[],
                dependencies={},
                critical_paths=self.config.critical_paths,
                analyzed_at=datetime.now().isoformat(),
            )

    def create_graph(self) -> StateGraph:
        """Create LangGraph for project analysis workflow.

        Returns:
            Compiled LangGraph
        """
        workflow = StateGraph(AnalyzerState)

        # Add nodes
        workflow.add_node("collect_files", self._node_collect_files)
        workflow.add_node("analyze_with_llm", self._node_analyze_with_llm)

        # Set entry point
        workflow.set_entry_point("collect_files")

        # Add edges
        workflow.add_edge("collect_files", "analyze_with_llm")
        workflow.add_edge("analyze_with_llm", END)

        return workflow.compile()

    async def _node_collect_files(self, state: AnalyzerState) -> dict:
        """Node: Collect file information."""
        return {"files_info": self._collect_files_info(state["root_dir"])}

    async def _node_analyze_with_llm(self, state: AnalyzerState) -> dict:
        """Node: Analyze with LLM."""
        context = await self._llm_analyze(state.get("files_info", ""), state["root_dir"])
        return {"project_context": context, "analysis_complete": True}
