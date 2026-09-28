"""MCP Server for package-registry — exposes version metadata, release dates, and deprecation notices."""

import json
from datetime import datetime
from typing import Any, Dict, List

from mcp.server import Server
from mcp.types import Tool, TextContent, ListToolsResult, CallToolResult, PaginatedRequestParams, CallToolRequestParams
from mcp.server.lowlevel.server import ServerRequestContext


PACKAGE_REGISTRY = {
    "requests": {
        "versions": [
            {"version": "2.32.3", "release_date": "2024-11-15", "deprecated": False, "yanked": False},
            {"version": "2.32.2", "release_date": "2024-08-20", "deprecated": False, "yanked": False},
            {"version": "2.32.1", "release_date": "2024-06-10", "deprecated": False, "yanked": False},
            {"version": "2.31.0", "release_date": "2023-05-15", "deprecated": True, "yanked": False,
             "deprecation_notice": "Use 2.32.x for security fixes. Migration guide: https://requests.readthedocs.io/en/latest/migration/"},
            {"version": "2.30.0", "release_date": "2023-01-10", "deprecated": True, "yanked": False,
             "deprecation_notice": "End of life. Upgrade to 2.32.x."},
        ],
        "latest": "2.32.3",
        "description": "Python HTTP library for humans",
    },
    "numpy": {
        "versions": [
            {"version": "2.0.1", "release_date": "2024-11-20", "deprecated": False, "yanked": False},
            {"version": "2.0.0", "release_date": "2024-06-15", "deprecated": False, "yanked": False},
            {"version": "1.26.4", "release_date": "2024-03-20", "deprecated": True, "yanked": False,
             "deprecation_notice": "Last 1.x release. NumPy 2.0 introduces breaking changes. Migration guide: https://numpy.org/devdocs/release/2.0.0-notes.html"},
            {"version": "1.26.3", "release_date": "2024-01-15", "deprecated": True, "yanked": False,
             "deprecation_notice": "Security fixes only. Upgrade to 2.x."},
        ],
        "latest": "2.0.1",
        "description": "Fundamental package for scientific computing with Python",
    },
    "pandas": {
        "versions": [
            {"version": "2.2.2", "release_date": "2024-11-10", "deprecated": False, "yanked": False},
            {"version": "2.2.1", "release_date": "2024-09-05", "deprecated": False, "yanked": False},
            {"version": "2.1.4", "release_date": "2024-05-20", "deprecated": True, "yanked": False,
             "deprecation_notice": "Use 2.2.x for performance improvements and bug fixes."},
            {"version": "2.0.3", "release_date": "2023-10-10", "deprecated": True, "yanked": False,
             "deprecation_notice": "Major version with breaking changes. See migration guide at pandas.pydata.org/docs/whatsnew/v2.0.0.html"},
        ],
        "latest": "2.2.2",
        "description": "Powerful data structures for data analysis",
    },
    "fastapi": {
        "versions": [
            {"version": "0.115.0", "release_date": "2024-11-05", "deprecated": False, "yanked": False},
            {"version": "0.114.0", "release_date": "2024-09-20", "deprecated": False, "yanked": False},
            {"version": "0.113.0", "release_date": "2024-08-10", "deprecated": False, "yanked": False},
            {"version": "0.110.0", "release_date": "2024-05-15", "deprecated": True, "yanked": False,
             "deprecation_notice": "Pre-1.0 versions have breaking changes. Migration to 0.115+: https://fastapi.tiangulo.com/migration/"},
        ],
        "latest": "0.115.0",
        "description": "Modern, fast web framework for building APIs with Python",
    },
}


def get_package_versions(package_name: str) -> Dict[str, Any]:
    """Get all version metadata for a package."""
    pkg = PACKAGE_REGISTRY.get(package_name.lower())
    if not pkg:
        return {"error": f"Package '{package_name}' not found in registry", "available_packages": list(PACKAGE_REGISTRY.keys())}
    return {
        "package": package_name,
        "description": pkg["description"],
        "latest_version": pkg["latest"],
        "versions": pkg["versions"],
    }


def get_latest_version(package_name: str) -> Dict[str, Any]:
    """Get the latest version info for a package."""
    pkg = PACKAGE_REGISTRY.get(package_name.lower())
    if not pkg:
        return {"error": f"Package '{package_name}' not found in registry"}
    latest_ver = next(v for v in pkg["versions"] if v["version"] == pkg["latest"])
    return {
        "package": package_name,
        "latest_version": pkg["latest"],
        "release_date": latest_ver["release_date"],
        "deprecated": latest_ver["deprecated"],
    }


def get_deprecation_notice(package_name: str, version: str) -> Dict[str, Any]:
    """Get deprecation notice for a specific package version."""
    pkg = PACKAGE_REGISTRY.get(package_name.lower())
    if not pkg:
        return {"error": f"Package '{package_name}' not found in registry"}
    ver_info = next((v for v in pkg["versions"] if v["version"] == version), None)
    if not ver_info:
        return {"error": f"Version '{version}' not found for package '{package_name}'"}
    return {
        "package": package_name,
        "version": version,
        "deprecated": ver_info.get("deprecated", False),
        "yanked": ver_info.get("yanked", False),
        "release_date": ver_info.get("release_date"),
        "deprecation_notice": ver_info.get("deprecation_notice", "No deprecation notice for this version."),
        "migration_guide": f"https://{package_name}.readthedocs.io/en/latest/migration/" if ver_info.get("deprecated") else None,
    }


def check_version_exists(package_name: str, version: str) -> Dict[str, Any]:
    """Check if a specific version exists for a package."""
    pkg = PACKAGE_REGISTRY.get(package_name.lower())
    if not pkg:
        return {"error": f"Package '{package_name}' not found in registry", "exists": False}
    exists = any(v["version"] == version for v in pkg["versions"])
    ver_info = next((v for v in pkg["versions"] if v["version"] == version), None)
    return {
        "package": package_name,
        "version": version,
        "exists": exists,
        "version_info": ver_info,
        "latest_available": pkg["latest"] if not exists else None,
    }


async def list_tools_handler(ctx: ServerRequestContext, params: PaginatedRequestParams) -> ListToolsResult:
    return ListToolsResult(tools=[
        Tool(
            name="get_package_versions",
            description="Get all version metadata for a package including release dates and deprecation status.",
            inputSchema={
                "type": "object",
                "properties": {"package_name": {"type": "string", "description": "Name of the package (e.g., 'requests', 'numpy')", }},
                "required": ["package_name"],
            },
        ),
        Tool(
            name="get_latest_version",
            description="Get the latest version information for a package.",
            inputSchema={
                "type": "object",
                "properties": {"package_name": {"type": "string", "description": "Name of the package", }},
                "required": ["package_name"],
            },
        ),
        Tool(
            name="get_deprecation_notice",
            description="Get deprecation notice and migration guide for a specific package version.",
            inputSchema={
                "type": "object",
                "properties": {
                    "package_name": {"type": "string", "description": "Name of the package", },
                    "version": {"type": "string", "description": "Specific version to check", },
                },
                "required": ["package_name", "version"],
            },
        ),
        Tool(
            name="check_version_exists",
            description="Check if a specific version exists for a package and get the latest available if not.",
            inputSchema={
                "type": "object",
                "properties": {
                    "package_name": {"type": "string", "description": "Name of the package", },
                    "version": {"type": "string", "description": "Version to check", },
                },
                "required": ["package_name", "version"],
            },
        ),
    ])


async def call_tool_handler(ctx: ServerRequestContext, params: CallToolRequestParams) -> CallToolResult:
    name = params.name
    arguments = params.arguments or {}
    
    try:
        if name == "get_package_versions":
            result = get_package_versions(arguments.get("package_name", ""))
        elif name == "get_latest_version":
            result = get_latest_version(arguments.get("package_name", ""))
        elif name == "get_deprecation_notice":
            result = get_deprecation_notice(arguments.get("package_name", ""), arguments.get("version", ""))
        elif name == "check_version_exists":
            result = check_version_exists(arguments.get("package_name", ""), arguments.get("version", ""))
        else:
            return CallToolResult(content=[TextContent(type="text", text=f"Unknown tool: {name}")])

        return CallToolResult(content=[TextContent(type="text", text=json.dumps(result, indent=2))])
    except Exception as e:
        return CallToolResult(content=[TextContent(type="text", text=f"Error: {str(e)}")])


server = Server(
    "package-registry",
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