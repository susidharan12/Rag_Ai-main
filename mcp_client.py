"""MCP Client for tool discovery and capturing JSON-RPC exchanges."""

import asyncio
import json
import subprocess
import sys
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, asdict


@dataclass
class JSONRPCMessage:
    jsonrpc: str = "2.0"
    id: Optional[int] = None
    method: Optional[str] = None
    params: Optional[Dict[str, Any]] = None
    result: Optional[Any] = None
    error: Optional[Dict[str, Any]] = None


class MCPClient:
    def __init__(self, command: List[str]):
        self.command = command
        self.process: Optional[subprocess.Popen] = None
        self.request_id = 0
        self.messages: List[Dict[str, Any]] = []

    def _next_id(self) -> int:
        self.request_id += 1
        return self.request_id

    async def start(self):
        self.process = subprocess.Popen(
            self.command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

    async def stop(self):
        if self.process:
            self.process.terminate()
            await asyncio.sleep(0.1)
            if self.process.poll() is None:
                self.process.kill()

    async def send(self, method: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if not self.process:
            raise RuntimeError("Client not started")

        msg = JSONRPCMessage(id=self._next_id(), method=method, params=params or {})
        line = json.dumps(asdict(msg)) + "\n"
        self.messages.append({"direction": "sent", "message": asdict(msg)})

        self.process.stdin.write(line)
        self.process.stdin.flush()

        # Read response
        response_line = await asyncio.get_event_loop().run_in_executor(
            None, self.process.stdout.readline
        )
        if not response_line:
            # Check stderr for errors
            stderr_line = await asyncio.get_event_loop().run_in_executor(
                None, self.process.stderr.readline
            )
            if stderr_line:
                print(f"Server stderr: {stderr_line}")
            raise RuntimeError("No response from server")

        response = json.loads(response_line.strip())
        self.messages.append({"direction": "received", "message": response})
        return response

    async def initialize(self) -> Dict[str, Any]:
        return await self.send("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "mcp-client", "version": "1.0.0"},
        })

    async def list_tools(self) -> Dict[str, Any]:
        return await self.send("tools/list", {})

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        return await self.send("tools/call", {"name": name, "arguments": arguments})

    def get_messages(self) -> List[Dict[str, Any]]:
        return self.messages


async def discover_tools(server_name: str, command: List[str]) -> Dict[str, Any]:
    """Discover tools from an MCP server and capture the full exchange."""
    client = MCPClient(command)
    await client.start()

    try:
        init_result = await client.initialize()
        tools_result = await client.list_tools()
        return {
            "server": server_name,
            "initialize": init_result,
            "tools_list": tools_result,
            "messages": client.get_messages(),
        }
    finally:
        await client.stop()


async def call_tool_and_capture(server_name: str, command: List[str], tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Call a tool and capture the full JSON-RPC exchange."""
    client = MCPClient(command)
    await client.start()

    try:
        init_result = await client.initialize()
        tools_result = await client.list_tools()
        call_result = await client.call_tool(tool_name, arguments)
        return {
            "server": server_name,
            "tool_called": tool_name,
            "arguments": arguments,
            "initialize": init_result,
            "tools_list": tools_result,
            "tools_call": call_result,
            "messages": client.get_messages(),
        }
    finally:
        await client.stop()


async def main():
    # Test docs-search server (server 1)
    print("=== Discovering tools from docs-search server ===")
    docs_result = await discover_tools(
        "docs-search",
        [sys.executable, "-m", "mcp_servers.docs_search_server"]
    )
    tools_before = docs_result['tools_list'].get('result', {}).get('tools', [])
    print(f"Tools found: {len(tools_before)}")
    for tool in tools_before:
        print(f"  - {tool['name']}")

    # Test package-registry server (server 2)
    print("\n=== Discovering tools from package-registry server ===")
    pkg_result = await discover_tools(
        "package-registry",
        [sys.executable, "-m", "mcp_servers.package_registry_server"]
    )
    tools_pkg = pkg_result['tools_list'].get('result', {}).get('tools', [])
    print(f"Tools found: {len(tools_pkg)}")
    for tool in tools_pkg:
        print(f"  - {tool['name']}")

    # Call a tool from package-registry to prove it works
    print("\n=== Calling get_package_versions for 'requests' ===")
    call_result = await call_tool_and_capture(
        "package-registry",
        [sys.executable, "-m", "mcp_servers.package_registry_server"],
        "get_package_versions",
        {"package_name": "requests"}
    )
    call_resp = call_result['tools_call']
    if 'result' in call_resp:
        print(f"Call succeeded: {call_resp['result']['content'][0]['text'][:200]}...")
    else:
        print(f"Call failed: {call_resp}")

    # Save wire.json with annotations
    wire_data = {
        "server_1_docs_search": docs_result,
        "server_2_package_registry": pkg_result,
        "tool_call_example": call_result,
    }

    with open("wire.json", "w") as f:
        json.dump(wire_data, f, indent=2)
    print("\nSaved wire.json with full JSON-RPC exchange")

    # Print tool counts
    tools_after = tools_before + tools_pkg
    print(f"\nTool count before: {len(tools_before)}")
    print(f"Tool count after: {len(tools_after)}")
    print(f"Before tools: {[t['name'] for t in tools_before]}")
    print(f"After tools: {[t['name'] for t in tools_after]}")


if __name__ == "__main__":
    asyncio.run(main())