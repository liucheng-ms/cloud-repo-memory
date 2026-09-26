"""Copied outside the checkout by check_wheel.py; uses installed packages only."""

import hashlib
from importlib.resources import files
import json
from pathlib import Path
import sys

import anyio
from jsonschema import Draft202012Validator
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

import cloud_repo_memory
from cloud_repo_memory.schemas import tool_schema


async def main():
    configuration, expected_hash = sys.argv[1:]
    prefix = Path(sys.prefix).resolve()
    assert Path(cloud_repo_memory.__file__).resolve().is_relative_to(prefix)
    resource = files("cloud_repo_memory.contracts").joinpath("local-mvp-v1.schema.json").read_bytes()
    assert hashlib.sha256(resource).hexdigest() == expected_hash
    for launcher in (
        StdioServerParameters(command=sys.executable, args=[
            "-I", "-B", "-m", "cloud_repo_memory", "--config", configuration], cwd=Path.cwd()),
        StdioServerParameters(command=str(prefix / "Scripts" / "cloud-repo-memory.exe"),
                              args=["--config", configuration], cwd=Path.cwd()),
    ):
        async with stdio_client(launcher) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = (await session.list_tools()).tools
                assert [tool.name for tool in tools] == ["list_memory_index", "get_memory"]
                for tool, stem in zip(tools, ("listMemoryIndex", "getMemory")):
                    assert tool.inputSchema == tool_schema(stem + "Input")
                    assert tool.outputSchema == tool_schema(stem + "Output")
                for name, arguments, schema in (
                    ("list_memory_index", {"project": "p"}, "listMemoryIndexOutput"),
                    ("get_memory", {"project": "p", "memory_id": "note-001"}, "getMemoryOutput"),
                ):
                    result = await session.call_tool(name, arguments)
                    assert not result.isError
                    assert len(result.content) == 1
                    assert result.structuredContent == json.loads(result.content[0].text)
                    Draft202012Validator(tool_schema(schema)).validate(result.structuredContent)
                result = await session.call_tool("get_memory", {
                    "project": "p", "memory_id": "note-001", "expected_version": None})
                assert result.isError and result.structuredContent["error"]["code"] == "INVALID_ARGUMENT"
    print("Installed resource parity and both real stdio launchers: PASS")


anyio.run(main)
