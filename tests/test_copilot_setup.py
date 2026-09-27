"""Owned synthetic setup checks; never launch Copilot or another coding client."""

import json
from pathlib import Path
import stat
import subprocess
import sys
import time
from types import SimpleNamespace

import anyio
import mcp.client.stdio as sdk_stdio
import pytest

from cloud_repo_memory.metadata import version
from support import REPO, source
from validation import copilot_setup as setup


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def configured(fixture):
    root = fixture.directory("synthetic notes")
    note = fixture.file(root / "one.md", source(project="p", body="Only synthetic reference.\n"))
    output = fixture.base / "local config"
    args = (fixture.base, output, Path(sys.executable), "p", root)
    try:
        setup.configure(*args)
        yield args, note
    finally:
        if output.exists():
            fixture.dirs.append(output)
            fixture.files.extend(path for path in output.iterdir() if path.is_file())


def capture_processes(monkeypatch, *, stall=False):
    processes = []
    launch = sdk_stdio._create_platform_compatible_process

    async def capture(**kwargs):
        if stall:
            kwargs["args"] = ["-I", "-c", "import time; time.sleep(60)"]
        process = await launch(**kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(sdk_stdio, "_create_platform_compatible_process", capture)
    return processes


def test_explicit_config_is_nonlaunching_and_read_only(configured, fixture, monkeypatch):
    args, note = configured
    parent, output, python, project, root = args
    original = note.read_bytes()
    settings = json.loads((output / "local.json").read_text("utf-8"))
    server = json.loads((output / "copilot-mcp.json").read_text("utf-8"))[
        "mcpServers"]["synthetic-memory"]
    assert settings == {"schema_version": 1, "projects": [{"project": project, "root": str(root)}]}
    assert server == {
        "type": "local", "command": str(python),
        "args": ["-I", "-B", "-m", "cloud_repo_memory", "--config", str(output / "local.json")],
        "tools": ["list_memory_index", "get_memory"],
    }
    assert sorted(path.name for path in output.iterdir()) == ["copilot-mcp.json", "local.json"]

    def no_process(*args, **kwargs):
        pytest.fail("Configuration must not launch any subprocess")

    monkeypatch.setattr(subprocess, "Popen", no_process)
    monkeypatch.setenv("SETUP_PRIVATE_SENTINEL", "never-copy-this-value")
    assert setup.settings(*args)["local.json"] == settings
    new_output = parent / "new config"
    try:
        setup.configure(parent, new_output, python, project, root)
        for path in new_output.iterdir():
            assert b"never-copy-this-value" not in path.read_bytes()
    finally:
        if new_output.exists():
            fixture.dirs.append(new_output)
            fixture.files.extend(new_output.iterdir())
    with pytest.raises(setup.SetupError, match="already exists"):
        setup.configure(*args)
    assert note.read_bytes() == original and list(root.iterdir()) == [note]


@pytest.mark.parametrize("change,match", [
    ({0: Path("relative")}, "absolute"),
    ({2: Path("python.exe")}, "absolute"),
    ({3: "Invalid Project"}, "slug"),
    ({4: Path("relative")}, "absolute"),
])
def test_invalid_explicit_arguments(configured, change, match):
    args, _ = configured
    values = list(args)
    for index, value in change.items():
        values[index] = value
    with pytest.raises(ValueError, match=match):
        setup.settings(*values)


def test_config_must_be_separate_and_direct_child(configured):
    args, _ = configured
    parent, output, python, project, root = args
    for owner, target in ((root, root / "config"), (parent, root),
                          (parent, parent / "nested" / "config"),
                          (parent, parent.parent / "outside")):
        with pytest.raises(setup.SetupError):
            setup.configure(owner, target, python, project, root)
    with pytest.raises(setup.SetupError, match="separate"):
        setup.configure(parent.parent, parent, python, project, root)
    assert not (root / "config").exists()


def test_redirected_ancestor_refused(configured, monkeypatch):
    args, _ = configured
    original = Path.lstat

    def redirected(path, *other, **kwargs):
        if path == args[0]:
            return SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=0x400)
        return original(path, *other, **kwargs)

    monkeypatch.setattr(Path, "lstat", redirected)
    with pytest.raises(ValueError, match="redirected"):
        setup.settings(*args)


def test_canonical_root_alias_cannot_hide_config_overlap(configured, monkeypatch):
    args, _ = configured
    parent, _, python, project, root = args
    original = Path.resolve

    def alias(path, *other, **kwargs):
        if path == root:
            return parent
        return original(path, *other, **kwargs)

    monkeypatch.setattr(Path, "resolve", alias)
    with pytest.raises(setup.SetupError, match="separate"):
        setup.settings(parent, parent / "new config", python, project, root)


@pytest.mark.anyio
async def test_generated_config_sdk_roundtrip_and_clean_exit(configured, monkeypatch):
    args, note = configured
    original = note.read_bytes()
    processes = capture_processes(monkeypatch)
    result = await setup.verify(*args, "note-001")
    assert result == {
        "status": "SDK_VERIFIED", "project": "p", "tools": setup.TOOLS,
        "entry_count": 1, "memory_id": "note-001",
        "source_version": version(original), "coding_client": "NOT_RUN",
    }
    assert len(processes) == 1 and processes[0].returncode == 0
    assert note.read_bytes() == original and list(note.parent.iterdir()) == [note]


@pytest.mark.anyio
@pytest.mark.parametrize("mutation", ["command", "duplicate", "missing", "large"])
async def test_tampered_configuration_never_executes(configured, monkeypatch, mutation):
    args, _ = configured
    config = args[1] / "copilot-mcp.json"
    if mutation == "command":
        value = json.loads(config.read_text("utf-8"))
        value["mcpServers"]["synthetic-memory"]["command"] = "copilot"
        config.write_text(json.dumps(value), encoding="utf-8")
    elif mutation == "duplicate":
        config.write_text('{"mcpServers":{},"mcpServers":{}}', encoding="utf-8")
    elif mutation == "large":
        config.write_bytes(b"x" * 262145)
    else:
        config.unlink()

    async def forbidden(**kwargs):
        pytest.fail("Invalid configuration must not execute anything")

    monkeypatch.setattr(sdk_stdio, "_create_platform_compatible_process", forbidden)
    with pytest.raises((setup.SetupError, FileNotFoundError)):
        await setup.verify(*args, "note-001")


@pytest.mark.anyio
@pytest.mark.parametrize("kind,match", [
    ("empty", "absent from the index"),
    ("ineligible", "absent from the index"),
    ("invalid", "INVALID_METADATA"),
    ("duplicate", "DUPLICATE_ID"),
])
async def test_actionable_sdk_failures_and_cleanup(configured, fixture, monkeypatch, kind, match):
    args, note = configured
    if kind == "empty":
        note.unlink()
    elif kind == "ineligible":
        note.write_bytes(source(project="p", status="draft"))
    elif kind == "invalid":
        note.write_bytes(b"not frontmatter")
    else:
        fixture.file(note.parent / "duplicate.md", note.read_bytes())
    processes = capture_processes(monkeypatch)
    with pytest.raises(setup.SetupError, match=match):
        await setup.verify(*args, "note-001")
    assert len(processes) == 1 and processes[0].returncode == 0


@pytest.mark.anyio
async def test_protocol_timeout_reaps_its_owned_process(configured, monkeypatch):
    args, _ = configured
    processes = capture_processes(monkeypatch, stall=True)
    monkeypatch.setattr(setup, "PROTOCOL_TIMEOUT_SECONDS", 0.2)
    started = time.monotonic()
    with pytest.raises(setup.SetupError, match="timed out"):
        with anyio.fail_after(10):
            await setup.verify(*args, "note-001")
    assert time.monotonic() - started < 10
    assert len(processes) == 1 and processes[0].returncode is not None


def cli_args(args):
    parent, output, python, project, root = args
    return ["--owned-parent", str(parent), "--output", str(output), "--python", str(python),
            "--project", project, "--root", str(root), "--synthetic-only"]


def test_cli_failure_is_nonzero_and_actionable(configured):
    args, _ = configured
    command = [sys.executable, "-B", "-m", "validation.copilot_setup", "configure"]
    result = subprocess.run(command + cli_args(args), cwd=REPO, capture_output=True,
                            text=True, timeout=20, check=False)
    assert result.returncode == 1 and result.stdout == ""
    assert "already exists" in result.stderr and "Traceback" not in result.stderr
    result = subprocess.run(command + cli_args(args)[:-1], cwd=REPO, capture_output=True,
                            text=True, timeout=20, check=False)
    assert result.returncode == 2 and "--synthetic-only" in result.stderr


def test_noneditable_runtime_origin(configured):
    args, _ = configured
    origin = subprocess.run([
        sys.executable, "-I", "-B", "-c",
        "import cloud_repo_memory, sys; print(cloud_repo_memory.__file__); print(sys.prefix)",
    ], cwd=args[1], capture_output=True, text=True, timeout=20, check=True)
    module_path, prefix = map(Path, origin.stdout.splitlines())
    if module_path.is_relative_to(REPO / "src"):
        pytest.skip("Non-editable install evidence requires pip install . rather than -e .")
    assert module_path.is_relative_to(prefix / "Lib" / "site-packages")
    assert not module_path.is_relative_to(REPO / "src")


def test_documented_cli_configure_and_verify(configured, fixture):
    args, note = configured
    parent, _, python, project, root = args
    output = parent / "cli config"
    args = (parent, output, python, project, root)
    try:
        prepared = subprocess.run([
            sys.executable, "-B", "-m", "validation.copilot_setup", "configure", *cli_args(args),
        ], cwd=REPO, capture_output=True, text=True, timeout=20, check=False)
        assert prepared.returncode == 0, prepared.stderr
        assert "CONFIGURED" in prepared.stdout and "No client was launched" in prepared.stdout
    finally:
        if output.exists():
            fixture.dirs.append(output)
            fixture.files.extend(output.iterdir())
    result = subprocess.run([
        sys.executable, "-B", "-m", "validation.copilot_setup", "verify",
        *cli_args(args), "--memory-id", "note-001",
    ], cwd=REPO, capture_output=True, text=True, timeout=30, check=False)
    assert result.returncode == 0, result.stderr
    verified = json.loads(result.stdout)
    assert verified["status"] == "SDK_VERIFIED"
    assert verified["source_version"] == version(note.read_bytes())
    assert verified["coding_client"] == "NOT_RUN"
