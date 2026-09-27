"""Checkout-side synthetic Copilot configuration and SDK-only verification."""

import argparse
import json
import logging
import os
from pathlib import Path
import re
import stat
import sys
from typing import Any

import anyio
from jsonschema import Draft202012Validator
from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client

from cloud_repo_memory.metadata import identifier, version
from cloud_repo_memory.results import MESSAGES
from cloud_repo_memory.schemas import tool_schema
from cloud_repo_memory.server import SafeDiagnostic
from validation.real_clients.prepare import TOOLS, checked_directory, json_bytes

PROTOCOL_TIMEOUT_SECONDS = 20
ANNOTATIONS = {
    "readOnlyHint": True, "destructiveHint": False,
    "idempotentHint": True, "openWorldHint": False,
}


class SetupError(ValueError):
    """Actionable operator error without note contents or raw exception data."""


def checked_file(path: Path) -> None:
    checked_directory(path.parent)
    info = path.lstat()
    if (not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode)
            or getattr(info, "st_file_attributes", 0) & 0x400 or info.st_nlink != 1):
        raise SetupError("Use an ordinary local file, not a link or redirected file.")


def settings(owned_parent: Path, output: Path, python: Path,
             project: str, root: Path) -> dict[str, Any]:
    if os.name != "nt":
        raise SetupError("This setup requires Windows and an owned fixed-NTFS synthetic root.")
    if not identifier(project):
        raise SetupError("Use a lowercase project slug of 1-64 characters with single hyphens.")
    parent = checked_directory(owned_parent)
    checked_directory(root)
    if (not re.match(r"^[A-Za-z]:\\", str(root))
            or any(char in str(root) for char in "%$")
            or any(part.endswith((" ", ".")) for part in root.parts)):
        raise SetupError("Use a literal drive-qualified root without expansions or trailing dots/spaces.")
    if not output.is_absolute() or output.parent != parent or output.name in ("", ".", ".."):
        raise SetupError("Output must be a direct child of the explicit owned parent.")
    location, knowledge = parent.resolve(strict=True) / output.name, root.resolve(strict=True)
    if location == knowledge or knowledge in location.parents or location in knowledge.parents:
        raise SetupError("Keep the configuration directory separate from the knowledge root.")
    if not python.is_absolute():
        raise SetupError("Supply the absolute python.exe from the installed runtime venv.")
    checked_file(python)
    if python.name.lower() != "python.exe":
        raise SetupError("Supply the installed runtime venv's python.exe, not a client or shell.")
    local = {"schema_version": 1, "projects": [{"project": project, "root": str(root)}]}
    if not Draft202012Validator(tool_schema("configuration")).is_valid(local):
        raise SetupError("Mapping does not satisfy local-v1; check the project and root.")
    return {
        "local.json": local,
        "copilot-mcp.json": {"mcpServers": {"synthetic-memory": {
            "type": "local", "command": str(python),
            "args": ["-I", "-B", "-m", "cloud_repo_memory", "--config", str(output / "local.json")],
            "tools": TOOLS,
        }}},
    }


def configure(owned_parent: Path, output: Path, python: Path, project: str, root: Path) -> None:
    payloads = settings(owned_parent, output, python, project, root)
    if os.path.lexists(output):
        raise SetupError("Output already exists; choose a new config directory. Nothing was overwritten.")
    output.mkdir()
    for name, value in payloads.items():
        with (output / name).open("xb") as stream:
            stream.write(json_bytes(value))


def checked_result(result: types.CallToolResult, prefix: str) -> dict[str, Any]:
    value = result.structuredContent
    if (not Draft202012Validator(tool_schema(prefix + "Output")).is_valid(value)
            or not isinstance(value, dict)
            or len(result.content) != 1 or not isinstance(result.content[0], types.TextContent)
            or result.isError is not (not value["ok"])):
        raise SetupError("SDK result does not match the local-v1 contract; check the installed runtime.")
    try:
        matching = json.loads(result.content[0].text) == value
    except ValueError:
        matching = False
    if not matching:
        raise SetupError("SDK text and structured results disagree; check the installed runtime.")
    if not value["ok"]:
        code = value["error"]["code"]
        raise SetupError(f"{code}: {MESSAGES[code]}")
    return value


async def roundtrip(session: ClientSession, project: str, memory_id: str) -> dict[str, object]:
    initialized = await session.initialize()
    if (initialized.serverInfo.name != "cloud-repo-memory"
            or initialized.capabilities.tools is None
            or initialized.capabilities.resources is not None
            or initialized.capabilities.prompts is not None):
        raise SetupError("Unexpected SDK server identity/capabilities; check the runtime installation.")
    discovery = await session.list_tools()
    if [tool.name for tool in discovery.tools] != TOOLS or discovery.nextCursor is not None:
        raise SetupError("Discovery must expose exactly the two local-v1 tools without pagination.")
    for tool, prefix in zip(discovery.tools, ("listMemoryIndex", "getMemory")):
        if (tool.inputSchema != tool_schema(prefix + "Input")
                or tool.outputSchema != tool_schema(prefix + "Output")
                or tool.annotations is None
                or tool.annotations.model_dump(exclude_none=True) != ANNOTATIONS):
            raise SetupError("Discovered schemas/annotations differ from local-v1; reinstall the runtime.")
    index = checked_result(
        await session.call_tool("list_memory_index", {"project": project}), "listMemoryIndex")
    markdown = index["index_markdown"]
    if (index["project"] != project or index["index_utf8_bytes"] != len(markdown.encode("utf-8"))
            or index["index_version"] != version(markdown.encode("utf-8"))):
        raise SetupError("Index identity, byte count or version mismatch; check the installed runtime.")
    entries = re.findall(
        r"^- \*\*([a-z0-9]+(?:-[a-z0-9]+)*)\*\* .*\n"
        r"  Summary: .*\n  Read when: .*\n  Version: (sha256:[0-9a-f]{64})$",
        markdown, re.M,
    )
    if len(entries) != index["entry_count"] or len(dict(entries)) != len(entries):
        raise SetupError("Index entries do not match the contract; check the installed runtime.")
    expected = dict(entries).get(memory_id)
    if expected is None:
        raise SetupError("Requested memory ID is absent from the index; check its project and active/approved metadata.")
    body = checked_result(await session.call_tool("get_memory", {
        "project": project, "memory_id": memory_id, "expected_version": expected,
    }), "getMemory")
    if (body["project"] != project or body["memory_id"] != memory_id
            or body["metadata"]["project"] != project or body["metadata"]["id"] != memory_id
            or body["source_version"] != expected):
        raise SetupError("Versioned get does not match the selected index entry; rerun after checking the runtime.")
    return {"status": "SDK_VERIFIED", "project": project, "tools": TOOLS,
            "entry_count": index["entry_count"], "memory_id": memory_id,
            "source_version": expected, "coding_client": "NOT_RUN"}


async def verify(owned_parent: Path, output: Path, python: Path,
                 project: str, root: Path, memory_id: str) -> dict[str, object]:
    payloads = settings(owned_parent, output, python, project, root)
    if not identifier(memory_id):
        raise SetupError("Use a valid explicit memory ID from your synthetic note.")
    checked_directory(output)
    for name, expected in payloads.items():
        path = output / name
        checked_file(path)
        with path.open("rb") as stream:
            raw = stream.read(262145)
        # Exact generated bytes reject duplicate keys, edits and substituted commands.
        if raw != json_bytes(expected):
            raise SetupError("Config differs from these explicit arguments; configure a new directory, then verify it.")
    copilot = payloads["copilot-mcp.json"]
    server = copilot["mcpServers"]["synthetic-memory"]
    failure = None
    async with stdio_client(StdioServerParameters(
            command=server["command"], args=server["args"], cwd=str(output))) as (read, write):
        async with ClientSession(read, write) as session:
            try:
                # End the deadline before transport teardown, so SDK cleanup is not cancelled.
                with anyio.fail_after(PROTOCOL_TIMEOUT_SECONDS):
                    result = await roundtrip(session, project, memory_id)
            except SetupError as exc:
                failure = exc
            except TimeoutError:
                failure = SetupError(
                    "SDK verification timed out; check local file availability and server stderr. "
                    "No coding client was launched.")
    if failure is not None:
        raise failure
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("configure", "verify"):
        command = commands.add_parser(name)
        command.add_argument("--owned-parent", required=True, type=Path)
        command.add_argument("--output", required=True, type=Path)
        command.add_argument("--python", required=True, type=Path)
        command.add_argument("--project", required=True)
        command.add_argument("--root", required=True, type=Path)
        command.add_argument("--synthetic-only", required=True, action="store_true",
                             help="Confirm the explicit root contains only owned synthetic notes.")
        if name == "verify":
            command.add_argument("--memory-id", required=True)
    args = parser.parse_args()
    logging.basicConfig(handlers=[SafeDiagnostic()], level=logging.WARNING, force=True)
    arguments = (args.owned_parent, args.output, args.python, args.project, args.root)
    try:
        if args.command == "configure":
            configure(*arguments)
            print("CONFIGURED: two new files; SDK verification is still required. No client was launched.")
        else:
            print(json.dumps(anyio.run(verify, *arguments, args.memory_id), ensure_ascii=True))
    except ValueError as exc:
        print(f"Setup refused: {exc}", file=sys.stderr)
        return 1
    except OSError:
        print("Setup I/O failed: check explicit paths, existence, permissions and free space. "
              "Partial output is retained; use a new directory after inspection.", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Setup interrupted; no verification success is claimed.", file=sys.stderr)
        return 130
    except Exception:
        print("SDK startup/protocol/cleanup failed. Check server stderr, the installed venv "
              "(-I -m cloud_repo_memory --help), and the explicit config. "
              "No coding client was launched or verified.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
