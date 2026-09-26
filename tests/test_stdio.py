"""Real subprocess protocol-client evidence; no coding agent or OneDrive access."""

from contextlib import asynccontextmanager
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

import anyio
from jsonschema import Draft202012Validator
from mcp import ClientSession, StdioServerParameters, types
import mcp.client.stdio as sdk_stdio
from mcp.shared.exceptions import McpError

import pytest

from cloud_repo_memory.schemas import CONTRACT, tool_schema
from support import REPO, config, source


@pytest.fixture
def anyio_backend():
    return "asyncio"


class RecordingReceive:
    def __init__(self, wrapped, messages):
        self.wrapped, self.messages = wrapped, messages

    async def receive(self):
        message = await self.wrapped.receive()
        self.messages.append(message)
        return message

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return await self.receive()
        except anyio.EndOfStream:
            raise StopAsyncIteration

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.wrapped.aclose()


@asynccontextmanager
async def connect(fixture, config_path, *, harness=None, ledger=None):
    messages, processes = [], []
    launch = sdk_stdio._create_platform_compatible_process

    async def capture(**kwargs):
        process = await launch(**kwargs)
        processes.append(process)
        return process

    args = ["-B", "-m", "cloud_repo_memory", "--config", str(config_path)]
    if harness:
        args = ["-B", str(Path(__file__).with_name("stdio_harness.py")),
                str(config_path), str(ledger), harness]
    stderr = fixture.file("server-stderr.txt", b"")
    with stderr.open("w", encoding="utf-8") as errlog, patch.object(
            sdk_stdio, "_create_platform_compatible_process", side_effect=capture):
        async with sdk_stdio.stdio_client(StdioServerParameters(
                command=sys.executable, args=args, cwd=str(fixture.base)), errlog=errlog) as (read, write):
            async with ClientSession(RecordingReceive(read, messages), write) as session:
                initialized = await session.initialize()
                assert initialized.serverInfo.name == "cloud-repo-memory"
                assert initialized.capabilities.tools is not None
                assert initialized.capabilities.resources is None
                assert initialized.capabilities.prompts is None
                yield session, processes[0], messages
    assert all(not isinstance(message, Exception) for message in messages)
    assert "Traceback" not in stderr.read_text("utf-8")


def setup(fixture):
    root = fixture.directory("notes")
    note = fixture.file(root / "one.md", source(project="p", body="Untrusted reference.\n"))
    settings = fixture.file("config.json", json.dumps(config(("p", root))).encode())
    return root, note, settings


def check(result, tool="get_memory", code=None):
    assert isinstance(result, types.CallToolResult)
    assert len(result.content) == 1 and isinstance(result.content[0], types.TextContent)
    value = result.structuredContent
    assert value == json.loads(result.content[0].text)
    assert result.isError is (not value["ok"])
    Draft202012Validator(tool_schema(
        "getMemoryOutput" if tool == "get_memory" else "listMemoryIndexOutput")).validate(value)
    if code:
        assert not value["ok"] and value["error"]["code"] == code
    else:
        assert value["ok"]
    return value


def test_normative_schema_resource_parity():
    assert CONTRACT == json.loads((REPO / "contracts" / "local-mvp-v1.schema.json").read_text("utf-8"))
    for name in ("listMemoryIndexInput", "getMemoryInput",
                 "listMemoryIndexOutput", "getMemoryOutput"):
        schema = tool_schema(name)
        Draft202012Validator.check_schema(schema)
        assert schema == {"$schema": CONTRACT["$schema"], **CONTRACT["$defs"][name],
                          "$defs": CONTRACT["$defs"]}


@pytest.mark.anyio
async def test_real_stdio_discovery_and_storage(fixture):
    root, note, settings = setup(fixture)
    async with connect(fixture, settings) as (session, process, messages):
        tools = (await session.list_tools()).tools
        assert [tool.name for tool in tools] == ["list_memory_index", "get_memory"]
        for tool, prefix in zip(tools, ("listMemoryIndex", "getMemory")):
            assert tool.inputSchema == tool_schema(prefix + "Input")
            assert tool.outputSchema == tool_schema(prefix + "Output")
            assert tool.annotations.model_dump(exclude_none=True) == {
                "readOnlyHint": True, "destructiveHint": False,
                "idempotentHint": True, "openWorldHint": False,
            }
        first = check(await session.call_tool("list_memory_index", {"project": "p"}),
                      "list_memory_index")
        body = check(await session.call_tool("get_memory", {"project": "p", "memory_id": "note-001"}))
        assert body["body_markdown"] == "Untrusted reference.\n"
        assert body["source_version"] in first["index_markdown"]
        args = {"project": "p", "memory_id": "note-001", "expected_version": body["source_version"]}
        check(await session.call_tool("get_memory", args))
        note.write_bytes(source(project="p", body="Changed.\n"))
        check(await session.call_tool("get_memory", args), code="MEMORY_CHANGED")
        changed = check(await session.call_tool("get_memory", {"project": "p", "memory_id": "note-001"}))
        assert changed["source_version"] != body["source_version"]
        assert changed["body_markdown"] == "Changed.\n"
        note.write_bytes(source(project="p", status="draft"))
        check(await session.call_tool("get_memory", args), code="MEMORY_INELIGIBLE")
        excluded = check(await session.call_tool("list_memory_index", {"project": "p"}),
                         "list_memory_index")
        assert excluded["entry_count"] == 0 and excluded["excluded_count"] == 1
        note.unlink()
        check(await session.call_tool("get_memory", args), code="MEMORY_NOT_FOUND")
        assert process.returncode is None
    assert fixture.base.joinpath("server-stderr.txt").read_text("utf-8") == ""


@pytest.mark.anyio
async def test_real_stdio_errors_and_invalid_arguments(fixture):
    root, note, settings = setup(fixture)
    settings.write_text(json.dumps(config(("p", root), ("missing", fixture.base / "missing-root"))),
                        encoding="utf-8")
    async with connect(fixture, settings) as (session, process, messages):
        for name, args in (
            ("list_memory_index", None), ("list_memory_index", {}),
            ("list_memory_index", {"project": None}),
            ("list_memory_index", {"project": "P"}),
            ("list_memory_index", {"project": 12}),
            ("list_memory_index", {"project": "p", "path": "PRIVATE_SENTINEL"}),
            ("get_memory", {"project": "p"}),
            ("get_memory", {"project": "p", "memory_id": 1}),
            ("get_memory", {"project": "p", "memory_id": "../PRIVATE_SENTINEL"}),
            ("get_memory", {"project": "p", "memory_id": "note-001", "expected_version": None}),
            ("get_memory", {"project": "p", "memory_id": "note-001", "expected_version": False}),
            ("get_memory", {"project": "p", "memory_id": "note-001", "expected_version": "bad"}),
            ("get_memory", {"project": "p", "memory_id": "note-001", "extra": True}),
        ):
            value = check(await session.call_tool(name, args), name, code="INVALID_ARGUMENT")
            assert not value["error"]["scan_complete"]
            assert "PRIVATE_SENTINEL" not in json.dumps(value)
        check(await session.call_tool("get_memory", {"project": "unknown", "memory_id": "note-001"}),
              code="UNKNOWN_PROJECT")
        check(await session.call_tool("get_memory", {"project": "missing", "memory_id": "note-001"}),
              code="PROJECT_UNAVAILABLE")
        with pytest.raises(McpError) as unknown:
            await session.call_tool("PRIVATE_SENTINEL", {})
        assert unknown.value.error.code == types.INVALID_PARAMS
        assert unknown.value.error.message == "Unknown tool."
        # Bypass client model validation only, not the SDK protocol transport.
        malformed = types.ClientRequest.model_construct(root=types.CallToolRequest.model_construct(
            method="tools/call", params={"name": "get_memory", "arguments": ["PRIVATE_SENTINEL"]}))
        with pytest.warns(UserWarning, match="Pydantic serializer warnings"):
            with pytest.raises(McpError) as invalid:
                await session.send_request(malformed, types.CallToolResult)
        assert invalid.value.error.code == types.INVALID_PARAMS
        assert "PRIVATE_SENTINEL" not in invalid.value.error.message
        copy = fixture.file(root / "copy.md", source(project="p"))
        for name, args in (("list_memory_index", {"project": "p"}),
                           ("get_memory", {"project": "p", "memory_id": "note-001"})):
            check(await session.call_tool(name, args), name, code="DUPLICATE_ID")
        copy.write_bytes(b"invalid PRIVATE_SENTINEL")
        for name, args in (("list_memory_index", {"project": "p"}),
                           ("get_memory", {"project": "p", "memory_id": "note-001"})):
            check(await session.call_tool(name, args), name, code="INVALID_METADATA")
        copy.unlink()
        check(await session.call_tool("get_memory", {"project": "p", "memory_id": "note-001"}))
    stderr = fixture.base.joinpath("server-stderr.txt").read_text("utf-8")
    assert "PRIVATE_SENTINEL" not in stderr


@pytest.mark.anyio
async def test_malformed_transport_frames_do_not_end_session(fixture):
    root, note, settings = setup(fixture)
    async with connect(fixture, settings) as (session, process, messages):
        for frame in (
            b'{"jsonrpc":"2.0","id":200,"method":false}\n',
            b'{"jsonrpc":"2.0","id":201,"method":{"PRIVATE_SENTINEL":true}}\n',
            b'not JSON PRIVATE_SENTINEL\n',
        ):
            before = len(messages)
            await process.stdin.send(frame)
            with anyio.fail_after(5):
                while not any(isinstance(item.message.root, types.JSONRPCNotification)
                              for item in messages[before:]):
                    await anyio.sleep(0.01)
                await session.send_ping()
                check(await session.call_tool("get_memory", {
                    "project": "p", "memory_id": "note-001"}))
            assert process.returncode is None
        encoded = "\n".join(item.message.model_dump_json() for item in messages)
        assert "PRIVATE_SENTINEL" not in encoded
    assert process.returncode == 0
    stderr = fixture.base.joinpath("server-stderr.txt").read_text("utf-8")
    assert "PRIVATE_SENTINEL" not in stderr
    assert stderr.count("MCP protocol diagnostic;") == 3


@pytest.mark.anyio
@pytest.mark.parametrize("mode", [
    "tool-exception", "tool-mcp-exception", "discovery-exception", "ping-exception",
])
async def test_unexpected_handler_exceptions_are_generic_and_recoverable(fixture, mode):
    root, note, settings = setup(fixture)
    ledger = fixture.file("ownership.jsonl", b"")
    async with connect(fixture, settings, harness=mode, ledger=ledger) as (session, process, messages):
        if mode.startswith("tool-"):
            result = check(await session.call_tool("get_memory", {
                "project": "p", "memory_id": "note-001"}), code="INTERNAL_ERROR")
            assert not result["error"]["scan_complete"]
        else:
            with pytest.raises(McpError) as failure:
                if mode == "discovery-exception":
                    await session.list_tools()
                else:
                    await session.send_ping()
            assert failure.value.error.code == types.INTERNAL_ERROR
            assert failure.value.error.message == "Local memory request failed."
            assert failure.value.error.data is None
        await session.send_ping()
        assert len((await session.list_tools()).tools) == 2
        check(await session.call_tool("get_memory", {"project": "p", "memory_id": "note-001"}))
        assert process.returncode is None
        encoded = "\n".join(item.message.model_dump_json() for item in messages)
        assert "PRIVATE_SENTINEL" not in encoded
    assert process.returncode == 0
    stderr = fixture.base.joinpath("server-stderr.txt").read_text("utf-8")
    assert stderr == "Local memory request handler failed.\n"


@pytest.mark.parametrize("arguments", [[], ["--bad=PRIVATE_SENTINEL"],
                                       ["--config", "PRIVATE_SENTINEL.json"]])
def test_launcher_failure_is_stderr_only(arguments, fixture):
    result = subprocess.run([sys.executable, "-B", "-m", "cloud_repo_memory", *arguments],
                            cwd=fixture.base, capture_output=True, text=True, timeout=15)
    assert result.returncode != 0
    assert not result.stdout
    assert result.stderr and "PRIVATE_SENTINEL" not in result.stderr
    assert "Traceback" not in result.stderr


@pytest.mark.parametrize("raw", [b"{PRIVATE_SENTINEL", b"{}", b'{"schema_version":1,"projects":[]}'])
def test_bad_configuration_startup(raw, fixture):
    settings = fixture.file("config.json", raw)
    result = subprocess.run([sys.executable, "-B", "-m", "cloud_repo_memory",
                             "--config", str(settings)], cwd=fixture.base,
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 2 and not result.stdout
    assert result.stderr == "Invalid local storage configuration; startup refused.\n"


def events(ledger):
    return [json.loads(line) for line in ledger.read_text("utf-8").splitlines()]


async def wait_events(ledger, predicate):
    with anyio.fail_after(10):
        while True:
            observed = events(ledger)
            if predicate(observed):
                return observed
            await anyio.sleep(0.01)


async def captured_call(session, results):
    try:
        results.append(await session.call_tool("list_memory_index", {"project": "p"}))
    except McpError as error:
        results.append(error)


@pytest.mark.anyio
async def test_cancellation_cancels_queued_not_owned_jobs(fixture):
    root, note, settings = setup(fixture)
    ledger = fixture.file("ownership.jsonl", b"")
    async with connect(fixture, settings, harness="slow", ledger=ledger) as (session, process, messages):
        results = []
        async with anyio.create_task_group() as group:
            running_id = session._request_id
            group.start_soon(captured_call, session, results)
            await wait_events(ledger, lambda rows: any(
                row["event"] == "launch" and row["operation"] == "list" for row in rows))
            queued_id = session._request_id
            group.start_soon(captured_call, session, results)
            await wait_events(ledger, lambda rows: sum(row["event"] == "request" for row in rows) == 2)
            with anyio.fail_after(0.5):
                await session.send_ping()
                for request_id in (queued_id, running_id):
                    await session.send_notification(types.ClientNotification(
                        types.CancelledNotification(method="notifications/cancelled",
                                                    params=types.CancelledNotificationParams(
                                                        requestId=request_id))))
            await wait_events(ledger, lambda rows: any(
                row["event"] == "job-finished" and row["operation"] == "list" for row in rows))
        assert len(results) == 2 and all(isinstance(item, McpError) for item in results)
        observed = events(ledger)
        assert sum(row["event"] == "launch" and row["operation"] == "list" for row in observed) == 1
        assert [row for row in observed if row["event"] == "job-finished"][-1]["pending"] is False
        check(await session.call_tool("get_memory", {"project": "p", "memory_id": "note-001"}))
        for message in messages:
            assert not (isinstance(message.message.root, types.JSONRPCResponse)
                        and message.message.root.id in (running_id, queued_id))


@pytest.mark.anyio
@pytest.mark.parametrize("mode", ["slow", "cleanup"])
async def test_eof_cancels_queue_and_retains_worker_until_cleanup(fixture, mode):
    import _winapi

    root, note, settings = setup(fixture)
    ledger = fixture.file("ownership.jsonl", b"")
    async with connect(fixture, settings, harness=mode, ledger=ledger) as (session, process, messages):
        results = []
        async with anyio.create_task_group() as group:
            running_id = session._request_id
            group.start_soon(captured_call, session, results)
            observed = await wait_events(ledger, lambda rows: any(
                row["event"] == "launch" and row["operation"] == "list" for row in rows))
            pid = next(row["pid"] for row in observed if row["event"] == "launch"
                       and row["operation"] == "list")
            handle = _winapi.OpenProcess(0x100000, False, pid)
            try:
                queued_id = session._request_id
                group.start_soon(captured_call, session, results)
                await wait_events(ledger, lambda rows: sum(row["event"] == "request" for row in rows) == 2)
                with anyio.fail_after(0.5):
                    await session.send_ping()
                await process.stdin.aclose()
                with anyio.fail_after(10):
                    assert await process.wait() == 0
                assert _winapi.WaitForSingleObject(handle, 0) == _winapi.WAIT_OBJECT_0
            finally:
                _winapi.CloseHandle(handle)
        observed = events(ledger)
        assert sum(row["event"] == "launch" and row["operation"] == "list" for row in observed) == 1
        assert observed[-1] == {"event": "shutdown", "pending": False, "code": 0}
        assert len(results) == 2 and all(isinstance(item, McpError) for item in results)
        assert not any(isinstance(message.message.root, types.JSONRPCResponse)
                       and message.message.root.id in (running_id, queued_id) for message in messages)
    stderr = fixture.base.joinpath("server-stderr.txt").read_text("utf-8")
    if mode == "cleanup":
        assert any(row["event"] == "cleanup-withheld" for row in observed)
        assert stderr == "Worker cleanup is pending; shutdown retains ownership.\n"
    else:
        assert stderr == ""


@pytest.mark.anyio
async def test_cleanup_pending_rejects_replacements_and_recovers(fixture):
    root, note, settings = setup(fixture)
    ledger = fixture.file("ownership.jsonl", b"")
    async with connect(fixture, settings, harness="cleanup", ledger=ledger) as (session, process, messages):
        result = check(await session.call_tool("list_memory_index", {"project": "p"}),
                       "list_memory_index", code="INTERNAL_ERROR")
        assert result["error"]["diagnostics"][0]["message"].startswith("Worker cleanup is pending")
        for _ in range(3):
            check(await session.call_tool("get_memory", {"project": "p", "memory_id": "note-001"}),
                  code="INTERNAL_ERROR")
        assert sum(row["event"] == "launch" for row in events(ledger)) == 2  # probe + one scan
        await anyio.sleep(1.3)
        check(await session.call_tool("get_memory", {"project": "p", "memory_id": "note-001"}))
        assert sum(row["event"] == "launch" for row in events(ledger)) == 3


@pytest.mark.anyio
async def test_shutdown_reaping_is_shielded_and_logs_once(capsys):
    from cloud_repo_memory.server import drain_workers

    with patch("cloud_repo_memory.server.MemoryStore.reap_workers",
               side_effect=[False, False, True]) as reap:
        with anyio.CancelScope() as scope:
            scope.cancel()
            await drain_workers()
        assert reap.call_count == 3
    captured = capsys.readouterr()
    assert not captured.out
    assert captured.err == "Worker cleanup is pending; shutdown retains ownership.\n"


@pytest.mark.anyio
async def test_bad_internal_result_is_sanitized(capsys):
    from unittest.mock import Mock
    from cloud_repo_memory.server import create_server

    store = Mock()
    store.get_memory.return_value = {"ok": True, "body_markdown": "PRIVATE_SENTINEL"}
    server = create_server(store)
    result = await server.request_handlers[types.CallToolRequest](types.CallToolRequest(
        method="tools/call", params=types.CallToolRequestParams(
            name="get_memory", arguments={"project": "p", "memory_id": "note-001"})))
    value = check(result.root, code="INTERNAL_ERROR")
    assert "PRIVATE_SENTINEL" not in json.dumps(value)
    assert capsys.readouterr().err == "Local storage returned an invalid result.\n"
