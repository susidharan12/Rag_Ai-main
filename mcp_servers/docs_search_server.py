"""MCP Server for docs-search — exposes documentation search tools."""

import json
import sys
from typing import Any, Dict, List

from mcp.server import Server
from mcp.types import Tool, TextContent, ListToolsResult, CallToolResult, PaginatedRequestParams, CallToolRequestParams
from mcp.server.lowlevel.server import ServerRequestContext

sys.path.insert(0, "C:\\Users\\Akash.t\\Rag_Ai-main")

from rag_core.store import DocStore

_store = DocStore()


# For this corpus, we define known versions based on document names/content
# In a real scenario, these would be extracted from the indexed documents
KNOWN_VERSIONS = ["v2", "v3", "2022-11-28", "2025-06-01", "2.x", "3.x"]


def _get_available_versions() -> List[str]:
    """Get all unique SDK versions present in the index."""
    return KNOWN_VERSIONS


def search_docs(query: str) -> List[Dict[str, Any]]:
    """Search the indexed documentation for chunks relevant to a query."""
    results = _store.search(query, top_k=5)
    return results


def get_version_info(version: str, query: str = "") -> List[Dict[str, Any]]:
    """Get documentation chunks specific to a named version."""
    q = query or version
    results = _store.search(q, top_k=8)
    versioned = [r for r in results if r.get("sdk_version") == version]
    return versioned[:5]


def get_version_info_recoverable(version: str, query: str = "") -> Dict[str, Any]:
    """
    Get documentation chunks for a version with recoverable error path.
    
    Returns a dict with either 'results' (success) or 'error' + 'recovery_hint' (failure).
    The recovery hint tells the model exactly what to try next.
    """
    available_versions = _get_available_versions()
    
    if version not in available_versions:
        # Find closest match (e.g., v4.x -> v3.x, 2025-06-01 -> 2022-11-28)
        latest = available_versions[-1] if available_versions else "unknown"
        return {
            "error": f"No documentation found for version '{version}'",
            "recovery_hint": f"Available versions in this corpus: {', '.join(available_versions)}. Latest is '{latest}'. Try get_version_info(version='{latest}') instead.",
            "available_versions": available_versions,
        }
    
    q = query or version
    results = _store.search(q, top_k=8)
    versioned = [r for r in results if r.get("sdk_version") == version]
    
    if not versioned:
        # Fallback: search without version filter but note the version in hint
        fallback = _store.search(q, top_k=5)
        return {
            "error": f"No chunks found specifically for version {version}.",
            "recovery_hint": f"Version '{version}' exists in corpus but no version-tagged chunks matched. Try search_docs(query='{q}') for unversioned results, or get_version_info(version='{available_versions[-1]}') for latest.",
            "available_versions": available_versions,
            "fallback_results": fallback[:3],
        }
    
    return {"results": versioned[:5]}


def compare_versions(query: str = "differences between versions") -> Dict[str, Any]:
    """Retrieve documentation for two versions side by side."""
    import re
    _VERSION_RE = re.compile(r"2022-11-28|2025-06-01|\b2\.x\b|\b3\.x\b")
    detected = list(dict.fromkeys(_VERSION_RE.findall(query)))
    if len(detected) >= 2:
        v_a, v_b = detected[0], detected[-1]
    else:
        v_a, v_b = "v2", "v3"
    results_v2 = _store.search(f"{query} {v_a}", top_k=4)
    results_v3 = _store.search(f"{query} {v_b}", top_k=4)
    return {
        "v_a": v_a,
        "v_b": v_b,
        "results_v2": results_v2[:3],
        "results_v3": results_v3[:3],
    }


def get_error_info(code: str = "", query: str = "") -> List[Dict[str, Any]]:
    """Look up error code information."""
    q = query or f"error {code} HTTP"
    results = _store.search(q, top_k=5)
    return results[:3]


def get_parameter_default(param: str = "", query: str = "") -> List[Dict[str, Any]]:
    """Look up a specific parameter's default value, type, and description."""
    q = query or f"parameter {param} default"
    results = _store.search(q, top_k=6)
    return results[:4]


def check_deprecation(subject: str, api_version: str) -> List[Dict[str, Any]]:
    """Check whether a named endpoint/parameter was removed/changed/replaced."""
    query = f"{subject} {api_version}"
    results = _store.search(query, top_k=8)
    change_markers = (
        "no longer", "removed", "replaced", "deprecated", "instead of",
        "did not exist", "requires a follow-up", "undocumented",
        "new in", "added in", "introduced in", "no way to", "heuristic",
        "override", "now be specified", "can be pre-armed",
    )
    hits = []
    for r in results:
        text = r["text"]
        if subject.lower() in text.lower() and any(m in text.lower() for m in change_markers):
            hits.append(r)
    return hits[:5] if hits else results[:3]


async def list_tools_handler(ctx: ServerRequestContext, params: PaginatedRequestParams) -> ListToolsResult:
    return ListToolsResult(tools=[
        Tool(
            name="search_docs",
            description="Search the indexed documentation for chunks relevant to a query. Returns the top matching text chunks with source info.",
            inputSchema={
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        ),
        Tool(
            name="get_version_info",
            description="Get documentation chunks specific to a named version (e.g. 'v2', 'v3', or an API version string). Use when the question asks about one specific version. If the version doesn't exist in the corpus, the tool returns a recoverable error with the list of available versions and a suggested alternative.",
            inputSchema={
                "type": "object",
                "properties": {
                    "version": {"type": "string"},
                    "query": {"type": "string", "default": ""},
                },
                "required": ["version"],
            },
        ),
        Tool(
            name="compare_versions",
            description="Retrieve documentation for two versions side by side. Use when the question asks for differences or changes between versions.",
            inputSchema={
                "type": "object",
                "properties": {"query": {"type": "string", "default": "differences between versions"}},
                "required": [],
            },
        ),
        Tool(
            name="get_error_info",
            description="Look up error code information (HTTP status codes, error names, retryability). Use for questions about specific error codes. Not for version-to-version comparison or migration questions.",
            inputSchema={
                "type": "object",
                "properties": {
                    "code": {"type": "string", "default": ""},
                    "query": {"type": "string", "default": ""},
                },
                "required": [],
            },
        ),
        Tool(
            name="get_parameter_default",
            description="Look up a specific parameter's default value, type, and description from the parameter tables. Use ONLY when the question asks what a parameter's default/type/description is today - never for a question about how a parameter changed, was added, or was replaced between two api_versions (use compare_versions or check_deprecation for those instead).",
            inputSchema={
                "type": "object",
                "properties": {
                    "param": {"type": "string", "default": ""},
                    "query": {"type": "string", "default": ""},
                },
                "required": [],
            },
        ),
        Tool(
            name="check_deprecation",
            description="Check whether one specific named endpoint, parameter, or CLI flag was removed, changed, or replaced in a given target api_version, and return its replacement if one exists. Use ONLY as a follow-up once you already know the subject and the target version from an earlier step — not for open-ended searching or side-by-side version comparison.",
            inputSchema={
                "type": "object",
                "properties": {
                    "subject": {"type": "string"},
                    "api_version": {"type": "string", "enum": ["2022-11-28", "2025-06-01", "2.x", "3.x"]},
                },
                "required": ["subject", "api_version"],
            },
        ),
    ])


async def call_tool_handler(ctx: ServerRequestContext, params: CallToolRequestParams) -> CallToolResult:
    name = params.name
    arguments = params.arguments or {}
    
    try:
        if name == "search_docs":
            results = search_docs(arguments.get("query", ""))
            return CallToolResult(content=[TextContent(type="text", text=json.dumps(results, indent=2))])
        
        elif name == "get_version_info":
            # Use the new recoverable version
            result = get_version_info_recoverable(arguments.get("version", "v3"), arguments.get("query", ""))
            return CallToolResult(content=[TextContent(type="text", text=json.dumps(result, indent=2))])
        
        elif name == "compare_versions":
            results = compare_versions(arguments.get("query", "differences between versions"))
            return CallToolResult(content=[TextContent(type="text", text=json.dumps(results, indent=2))])
        
        elif name == "get_error_info":
            results = get_error_info(arguments.get("code", ""), arguments.get("query", ""))
            return CallToolResult(content=[TextContent(type="text", text=json.dumps(results, indent=2))])
        
        elif name == "get_parameter_default":
            results = get_parameter_default(arguments.get("param", ""), arguments.get("query", ""))
            return CallToolResult(content=[TextContent(type="text", text=json.dumps(results, indent=2))])
        
        elif name == "check_deprecation":
            results = check_deprecation(arguments.get("subject", ""), arguments.get("api_version", ""))
            return CallToolResult(content=[TextContent(type="text", text=json.dumps(results, indent=2))])
        
        else:
            return CallToolResult(content=[TextContent(type="text", text=f"Unknown tool: {name}")])
    except Exception as e:
        return CallToolResult(content=[TextContent(type="text", text=f"Error: {str(e)}")])


server = Server(
    "docs-search",
    on_list_tools=list_tools_handler,
    on_call_tool=call_tool_handler,
)


if __name__ == "__main__":
    from mcp.server.stdio import stdio_server
    import asyncio

    async def main():
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())

    asyncio.run(main())