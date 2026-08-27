"""Default AXIO Code tool registry."""

from __future__ import annotations

from .registry import CodeTool, CodeToolRegistry, ToolResult, summarize_arguments


def build_default_registry() -> CodeToolRegistry:
    from .artifact_tools import TOOLS as ARTIFACT_TOOLS
    from .document_tools import TOOLS as DOCUMENT_TOOLS
    from .browser_tools import TOOLS as BROWSER_TOOLS
    from .filesystem import TOOLS as FILESYSTEM_TOOLS
    from .git_tools import TOOLS as GIT_TOOLS
    from .github_tools import TOOLS as GITHUB_TOOLS
    from .node_tools import TOOLS as NODE_TOOLS
    from .python_tools import TOOLS as PYTHON_TOOLS
    from .retrieval_tools import TOOLS as RETRIEVAL_TOOLS
    from .scaffold_tools import TOOLS as SCAFFOLD_TOOLS
    from .shell_tools import TOOLS as SHELL_TOOLS
    from .web_tools import TOOLS as WEB_TOOLS
    from .verification import make_verification_gate_tool

    registry = CodeToolRegistry()
    registry.register_many(FILESYSTEM_TOOLS, category="filesystem")
    registry.register_many(PYTHON_TOOLS, category="python")
    registry.register_many(NODE_TOOLS, category="node")
    registry.register_many(GIT_TOOLS, category="git")
    registry.register_many(GITHUB_TOOLS, category="github")
    registry.register_many(DOCUMENT_TOOLS, category="document")
    registry.register_many(ARTIFACT_TOOLS, category="artifact")
    registry.register_many(SHELL_TOOLS, category="shell")
    registry.register(make_verification_gate_tool(registry))
    registry.register_many(WEB_TOOLS, category="web")
    registry.register_many(BROWSER_TOOLS, category="browser")
    registry.register_many(RETRIEVAL_TOOLS, category="retrieval")
    registry.register_many(SCAFFOLD_TOOLS, category="scaffold")
    return registry


CODE_TOOL_REGISTRY = build_default_registry()

__all__ = [
    "CODE_TOOL_REGISTRY",
    "CodeTool",
    "CodeToolRegistry",
    "ToolResult",
    "build_default_registry",
    "summarize_arguments",
]
