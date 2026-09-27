"""Explicit, one-shot synthetic pilot; no discovery, reuse, hydration or cleanup."""

import argparse
from contextlib import ExitStack
import ctypes as C
from ctypes import wintypes as W
from datetime import timedelta
import importlib.util
from importlib.metadata import version as package_version
import json
import ntpath
import os
from pathlib import Path
import sys
import time
import traceback
from unittest.mock import patch
import uuid

import anyio
from jsonschema import Draft202012Validator
from mcp import ClientSession, StdioServerParameters, types
import mcp.client.stdio as sdk_stdio

from cloud_repo_memory.metadata import parse, render, version
from cloud_repo_memory.results import utc_now
from cloud_repo_memory.schemas import tool_schema
from cloud_repo_memory import winfs

REPO = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "pilot_fixture_helpers", REPO / "validation" / "real_clients" / "prepare.py")
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Fixture helper unavailable.")
kit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(kit)
PROJECT = kit.PROJECT

WriteFile = winfs.api("WriteFile", W.BOOL, W.HANDLE, C.c_void_p, W.DWORD,
                     C.POINTER(W.DWORD), C.c_void_p)
Seek = winfs.api("SetFilePointerEx", W.BOOL, W.HANDLE, C.c_longlong,
                C.POINTER(C.c_longlong), W.DWORD)
Truncate = winfs.api("SetEndOfFile", W.BOOL, W.HANDLE)
Flush = winfs.api("FlushFileBuffers", W.BOOL, W.HANDLE)
SetInfo = winfs.api("SetFileInformationByHandle", W.BOOL, W.HANDLE, C.c_int,
                   C.c_void_p, W.DWORD)


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def absent(path):
    # lexists alone can hide access errors. A non-following lstat must confirm
    # absence too; any error other than FileNotFoundError stops the experiment.
    if os.path.lexists(path):
        raise FileExistsError("Target exists; confirmation required, no inspection.")
    try:
        os.lstat(path)
    except FileNotFoundError:
        return
    raise FileExistsError("Target exists; confirmation required, no inspection.")


def payloads():
    adaptation = json.loads((REPO / "validation" / "local-mvp-acceptance.json")
                            .read_bytes())["fixture_adaptation"]
    overlays = adaptation["overlays"]
    require(adaptation["project"] == PROJECT
            and tuple(row["file"] for row in overlays) == kit.FILES
            and [row["id"] for row in overlays] == [f"kst-{n:03}" for n in range(1, 6)],
            "Unexpected fixture layout.")
    result = {}
    for row in overlays:
        raw = (REPO / "validation" / "samples" / "kusto-memory" / "agent-input"
               / row["file"]).read_bytes()
        body = kit.historical_body(raw)
        metadata = {
            "schema_version": 1, "id": row["id"], "project": PROJECT,
            **{key: row[key] for key in ("title", "summary", "read_when")},
            "status": "active", "approval": "approved",
        }
        data = source(metadata, body)
        note = parse(data, PROJECT)
        require(note.eligible and note.body.encode("utf-8") == body,
                "Fixture fidelity failed.")
        result[row["file"]] = data
    return result


def source(metadata, body):
    return ("---\n" + "".join(
        f"{key}: {json.dumps(value, ensure_ascii=True)}\n"
        for key, value in metadata.items()) + "---\n").encode("utf-8") + body


class Evidence:
    def __init__(self, parent):
        kit.checked_directory(parent)
        self.path = parent / ("onedrive-pilot-" + uuid.uuid4().hex)
        self.path.mkdir()
        self.ledger = self.path / "events.jsonl"
        with self.ledger.open("xb"):
            pass

    def record(self, event, **fields):
        with self.ledger.open("ab") as stream:
            stream.write(kit.json_bytes({"at": utc_now(), "event": event, **fields})
                         .replace(b"\n", b"") + b"\n")
            stream.flush()
            os.fsync(stream.fileno())

    def file(self, name, data):
        with (self.path / name).open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())


def flags(attributes, tag):
    return {
        "attributes": f"0x{attributes:08x}", "tag": f"0x{tag:08x}",
        "offline": bool(attributes & winfs.OFFLINE),
        "recall_on_data": bool(attributes & winfs.RECALL_DATA),
        "pinned": bool(attributes & 0x80000),
        "unpinned": bool(attributes & 0x100000),
    }


def preflight_parent(path, evidence):
    # Outermost first: never stat a child through an unchecked redirect.
    winfs.root_parts(str(path))
    for number, ancestor in enumerate(reversed((path, *path.parents))):
        state = ancestor.lstat()
        evidence.record("ancestor-metadata", ancestor_number=number,
                        **flags(state.st_file_attributes, state.st_reparse_tag))
        winfs.classify(state.st_file_attributes, state.st_reparse_tag, enumeration=True)
        require(bool(state.st_file_attributes & winfs.DIRECTORY),
                "Non-directory ancestor.")


class OwnedFile(winfs.Handle):
    """No-follow exclusive create/mutation, with validation on the same handle."""

    def __init__(self, parent, name, *, create=False):
        winfs.component(name)
        self.value = winfs.CreateFile(
            ntpath.join(parent, name), 0xC0000000 | 0x10000, 1, None,
            1 if create else 3, winfs.OPEN_FLAGS, None)
        if self.value == C.c_void_p(-1).value:
            raise C.WinError(C.get_last_error())
        try:
            state, final = self.snapshot(), self.final_path()
            require(not state.attributes & winfs.DIRECTORY and state.links == 1,
                    "Non-regular or hard-linked source.")
            require(ntpath.dirname(final).rstrip("\\") == parent.rstrip("\\")
                    and ntpath.basename(final).casefold() == name.casefold(),
                    "Source containment changed.")
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def bytes(self):
        before = self.snapshot()
        require(before.size <= winfs.MAX_FILE, "Unexpected file size.")
        winfs.check(Seek(self.value, 0, None, 0))
        buffer = C.create_string_buffer(before.size + 1)
        count = W.DWORD()
        winfs.check(winfs.ReadFile(self.value, buffer, len(buffer), C.byref(count), None))
        require(count.value == before.size and self.snapshot() == before,
                "File changed during ownership check.")
        return buffer.raw[:count.value]

    def write(self, data):
        winfs.check(Seek(self.value, 0, None, 0))
        count = W.DWORD()
        winfs.check(WriteFile(self.value, data, len(data), C.byref(count), None))
        require(count.value == len(data), "Incomplete synthetic write.")
        winfs.check(Truncate(self.value))
        winfs.check(Flush(self.value))
        require(self.bytes() == data, "Synthetic write verification failed.")

    def delete(self):
        disposition = W.BOOL(True)
        winfs.check(SetInfo(self.value, 4, C.byref(disposition), C.sizeof(disposition)))


class Corpus:
    def __init__(self, path, evidence):
        self.path, self.evidence = path, evidence
        self.identity = None
        self.files = {}

    def create(self):
        winfs.component(self.path.name)
        preflight_parent(self.path.parent, self.evidence)
        self.evidence.record("parent-handle-validation-started")
        with winfs.Root(str(self.path.parent)) as parent:
            self.evidence.record("parent-handle-validated",
                                 **flags(parent.state.attributes, parent.state.tag))
            target = ntpath.join(parent.final, self.path.name)
            absent(target)
            self.evidence.record("directory-create-intent", root=str(self.path))
            os.mkdir(target)
            created = os.lstat(target)
            with winfs.Root(str(self.path)) as root:
                require((root.state.identity[1] << 32 | root.state.identity[2])
                        == created.st_ino, "New directory identity changed.")
                self.identity = root.state.identity
                self.evidence.record("directory-owned", identity=self.identity,
                                     **flags(root.state.attributes, root.state.tag))
                self.inventory(root)
        print("New synthetic directory created; ownership ledger persisted.", flush=True)

    def inventory(self, root):
        with os.scandir(root.final) as entries:
            found = {}
            for entry in entries:
                require(entry.name in self.files, "Unexpected entry; stop without cleanup.")
                info = entry.stat(follow_symlinks=False)
                self.evidence.record("source-enumeration", name=entry.name,
                                     **flags(info.st_file_attributes, info.st_reparse_tag))
                winfs.classify(info.st_file_attributes, info.st_reparse_tag, enumeration=True)
                require(not info.st_file_attributes & winfs.DIRECTORY,
                        "Unexpected subdirectory; stop without cleanup.")
                found[entry.name] = info
        require(set(found) == set(self.files), "Generated source missing unexpectedly.")
        return found

    def observe(self, phase):
        require(self.identity is not None, "Directory ownership not established.")
        with winfs.Root(str(self.path), self.identity) as root:
            self.evidence.record("directory-metadata", phase=phase,
                                 **flags(root.state.attributes, root.state.tag))
            self.inventory(root)
            for name, (identity, data) in self.files.items():
                with ExitStack() as stack:
                    _, state, _ = winfs.child(stack, root.final, name)
                    self.evidence.record("source-metadata", phase=phase, name=name,
                                         **flags(state.attributes, state.tag))
                    require(state.identity == identity and state.links == 1,
                            "Generated source identity changed.")
                    require(root.read(name, state) == data,
                            "Generated source hash/content changed.")
        self.evidence.record("phase-verified", phase=phase, files=len(self.files))

    def add(self, name, data):
        require(self.identity is not None and name in kit.FILES and name not in self.files,
                "Unapproved create.")
        note = parse(data, PROJECT)
        with winfs.Root(str(self.path), self.identity) as root:
            self.inventory(root)
            absent(ntpath.join(root.final, name))
            self.evidence.record("file-create-intent", name=name, memory_id=note.metadata["id"],
                                 version=version(data))
            with OwnedFile(root.final, name, create=True) as handle:
                identity = handle.snapshot().identity
                self.evidence.record("file-owned-empty", name=name, identity=identity,
                                     version=version(b""))
                handle.write(data)
                self.files[name] = identity, data
                self.evidence.record("file-created", name=name, identity=identity,
                                     version=version(data))

    def mutate(self, name, replacement):
        self.observe("before-delete" if replacement is None else "before-edit")
        identity, expected = self.files[name]
        with winfs.Root(str(self.path), self.identity) as root:
            self.inventory(root)
            with OwnedFile(root.final, name) as handle:
                require(handle.snapshot().identity == identity, "Mutation identity mismatch.")
                data = handle.bytes()
                require(version(data) == version(expected) and data == expected
                        and parse(data, PROJECT).metadata["id"]
                        == parse(expected, PROJECT).metadata["id"], "Mutation content mismatch.")
                self.evidence.record("delete-intent" if replacement is None else "edit-intent",
                                     name=name, identity=identity, previous_version=version(data),
                                     next_version=None if replacement is None else version(replacement))
                if replacement is None:
                    handle.delete()
                else:
                    require(parse(replacement, PROJECT).metadata["id"]
                            == parse(data, PROJECT).metadata["id"], "Edit changed note ID.")
                    handle.write(replacement)
            if replacement is None:
                del self.files[name]
                absent(ntpath.join(root.final, name))
            else:
                self.files[name] = identity, replacement
            self.evidence.record("deleted" if replacement is None else "edited", name=name)


def check_result(result, tool, code=None):
    require(isinstance(result, types.CallToolResult), "Invalid SDK result type.")
    value = result.structuredContent
    require(len(result.content) == 1 and isinstance(result.content[0], types.TextContent)
            and value == json.loads(result.content[0].text), "Result representations disagree.")
    Draft202012Validator(tool_schema(
        "getMemoryOutput" if tool == "get_memory" else "listMemoryIndexOutput")).validate(value)
    require(result.isError is (not value["ok"]), "Incorrect error marker.")
    require((not value["ok"] and value["error"]["code"] == code) if code else value["ok"],
            "Unexpected tool outcome.")
    return value


async def exercise(corpus, originals):
    evidence = corpus.evidence
    evidence.file("config.json", kit.json_bytes({
        "schema_version": 1, "projects": [{"project": PROJECT, "root": str(corpus.path)}]}))
    processes = []
    launch = sdk_stdio._create_platform_compatible_process

    async def capture(**kwargs):
        process = await launch(**kwargs)
        processes.append(process)
        evidence.record("server-launched", pid=process.pid)
        return process

    async def call(session, label, tool="list_memory_index", *, code=None, **arguments):
        corpus.observe(label)
        arguments = {"project": PROJECT, **arguments}
        started = time.monotonic()
        result = await session.call_tool(tool, arguments)
        evidence.record("tool-response", label=label, tool=tool, arguments=arguments,
                        wall_ms=round((time.monotonic() - started) * 1000, 3),
                        response=result.model_dump(mode="json", exclude_none=True),
                        server_pid=processes[0].pid)
        return check_result(result, tool, code)

    def check_index(result):
        expected = render(PROJECT, [parse(data, PROJECT) for _, data in corpus.files.values()])
        require(result["index_markdown"] == expected
                and result["index_version"] == version(expected.encode("utf-8"))
                and result["index_utf8_bytes"] == len(expected.encode("utf-8"))
                and result["entry_count"] == len(corpus.files)
                and result["excluded_count"] == 0, "Index does not match owned corpus.")

    def check_body(result, data):
        note = parse(data, PROJECT)
        require(result["body_markdown"] == note.body and result["metadata"] == note.metadata
                and result["source_version"] == note.version
                and result["source_utf8_bytes"] == len(data), "Body/version mismatch.")

    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-B", str(Path(__file__).with_name("observe_server.py")),
              str(evidence.path / "config.json"), str(evidence.path / "workers.jsonl")],
        cwd=str(REPO))
    try:
        with (evidence.path / "stderr.txt").open("x", encoding="utf-8") as stderr, patch.object(
                sdk_stdio, "_create_platform_compatible_process", side_effect=capture):
            with anyio.fail_after(90):
                async with sdk_stdio.stdio_client(parameters, errlog=stderr) as (read, write):
                    async with ClientSession(
                            read, write, read_timeout_seconds=timedelta(seconds=10)) as session:
                        initialized = await session.initialize()
                        evidence.record("initialized", result=initialized.model_dump(mode="json"))
                        require(initialized.serverInfo.name == "cloud-repo-memory",
                                "Unexpected server identity.")
                        tools = await session.list_tools()
                        require([tool.name for tool in tools.tools] == kit.TOOLS,
                                "Unexpected tools.")
                        baseline = await call(session, "baseline-index")
                        check_index(baseline)
                        for name, data in originals.items():
                            note = parse(data, PROJECT)
                            result = await call(
                                session, "baseline-" + note.metadata["id"], "get_memory",
                                memory_id=note.metadata["id"], expected_version=note.version)
                            check_body(result, data)
                        name = kit.FILES[0]
                        original = originals[name]
                        note = parse(original, PROJECT)
                        changed = source(
                            {**note.metadata, "title": "Environment routing pilot revision",
                             "summary": "Fictional local pilot metadata revision."},
                            note.body.encode("utf-8") + b"\nFictional local pilot revision two.\n")
                        corpus.mutate(name, changed)
                        updated = await call(session, "updated-index")
                        check_index(updated)
                        require(updated["index_version"] != baseline["index_version"],
                                "Index failed to refresh.")
                        await call(session, "stale-version", "get_memory", code="MEMORY_CHANGED",
                                   memory_id=note.metadata["id"], expected_version=note.version)
                        result = await call(session, "updated-body", "get_memory",
                                            memory_id=note.metadata["id"],
                                            expected_version=version(changed))
                        check_body(result, changed)
                        corpus.mutate(name, None)
                        deleted = await call(session, "deleted-index")
                        check_index(deleted)
                        await call(session, "deleted-body", "get_memory", code="MEMORY_NOT_FOUND",
                                   memory_id=note.metadata["id"], expected_version=version(changed))
                        corpus.add(name, original)
                        restored = await call(session, "restored-index")
                        check_index(restored)
                        require(restored["index_version"] == baseline["index_version"],
                                "Baseline index not restored.")
                        result = await call(session, "restored-body", "get_memory",
                                            memory_id=note.metadata["id"],
                                            expected_version=note.version)
                        check_body(result, original)
                        require(len(processes) == 1 and processes[0].returncode is None,
                                "Server did not remain alive throughout.")
    finally:
        evidence.record("server-exit-observation",
                        processes=[{"pid": p.pid, "returncode": p.returncode} for p in processes])
    require(len(processes) == 1 and processes[0].returncode == 0, "Server exit not clean.")
    events = [json.loads(line) for line in (evidence.path / "workers.jsonl")
              .read_text("utf-8").splitlines()]
    jobs = [event for event in events if event["event"] == "job-finished"]
    require(len(jobs) == 14 and all(event["cleanup_confirmed"] is True
                                  and event["pending"] is False
                                  and all(p["returncode"] is not None
                                          for p in event["workers"]) for event in jobs),
            "Worker ownership/cleanup observation incomplete.")
    require(events[-1]["event"] == "shutdown" and not events[-1]["pending"]
            and events[-1]["code"] == 0, "Server shutdown ownership incomplete.")
    corpus.observe("final-baseline")
    evidence.record("pilot-passed", names=list(originals), tool_calls=13,
                    worker_jobs=len(jobs), server_exit=0)


def arguments(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True,
                        help="Exact approved NEW direct child of the personal OneDrive directory")
    parser.add_argument("--evidence-parent", type=Path, required=True,
                        help="Existing owned non-synchronized local directory")
    for flag in ("approve-new-synthetic-files", "approve-edit-delete-recreate",
                 "confirm-evidence-outside-sync", "run-live-sdk"):
        parser.add_argument("--" + flag, required=True, action="store_true")
    return parser.parse_args(argv)


def main(argv=None):
    args = arguments(argv)
    # Neither environment/profile discovery nor automatic root selection is permitted.
    winfs.root_parts(str(args.root))
    require(args.root.parent != args.root and args.root.parent.parent != args.root.parent,
            "A dedicated child directory is required.")
    kit.checked_directory(args.evidence_parent)
    left, right = str(args.root.parent).casefold(), str(args.evidence_parent).casefold()
    require(right != left and not right.startswith(left + "\\"),
            "Evidence cannot be inside the synchronized parent.")
    originals = payloads()
    evidence = Evidence(args.evidence_parent)
    print(f"Private evidence: {evidence.path}", flush=True)
    started = time.monotonic()
    try:
        evidence.record("pilot-start", root=str(args.root), retries=0,
                        python=sys.version, sdk_call_timeout_seconds=10,
                        sdk_observation_budget_seconds=90,
                        packages={name: package_version(name) for name in (
                            "cloud-repo-memory", "mcp", "anyio", "jsonschema", "ruamel.yaml")})
        corpus = Corpus(args.root, evidence)
        corpus.create()
        for name, data in originals.items():
            corpus.add(name, data)
        anyio.run(exercise, corpus, originals)
    except BaseException as error:
        evidence.file("failure-traceback.txt", "".join(
            traceback.format_exception(type(error), error, error.__traceback__)).encode("utf-8"))
        evidence.record("pilot-stopped", error_type=type(error).__name__,
                        code=getattr(error, "code", None), winerror=getattr(error, "winerror", None),
                        elapsed_ms=round((time.monotonic() - started) * 1000, 3))
        print("Pilot stopped; preserve partial files and private evidence. No retry or cleanup.",
              file=sys.stderr)
        return 1
    evidence.record("pilot-finished", elapsed_ms=round((time.monotonic() - started) * 1000, 3))
    print("PASS: five synthetic baseline notes retained; local observations only.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
