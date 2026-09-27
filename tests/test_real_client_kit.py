"""Preparation and MCP SDK checks only; no coding-client model invocations."""

import importlib.util
import json
from pathlib import Path
import stat
import subprocess
import sys
from types import SimpleNamespace

import pytest

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

from cloud_repo_memory.metadata import parse, version
from support import ACCEPTANCE, REPO
from test_stdio import check, connect

SPEC = importlib.util.spec_from_file_location(
    "real_client_prepare", REPO / "validation" / "real_clients" / "prepare.py")
kit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(kit)


@pytest.fixture
def anyio_backend():
    return "asyncio"


def generate(fixture):
    output = fixture.base / "kit"
    try:
        return kit.prepare(fixture.base, output, Path(sys.executable))
    finally:
        if output.exists():
            fixture.dirs.append(output)
            for path in sorted(output.rglob("*"), key=lambda value: len(value.parts)):
                (fixture.dirs if path.is_dir() else fixture.files).append(path)


def read(path):
    return json.loads(path.read_text("utf-8"))


def test_corpus_fidelity_and_evaluator_separation(fixture):
    output = generate(fixture)
    source = REPO / "validation" / "samples" / "kusto-memory"
    manifest = read(output / "evaluator" / "source-manifest.json")
    assert sorted(path.name for path in (output / "knowledge").iterdir()) == sorted(kit.FILES)
    assert not (output / "knowledge" / "MEMORY.md").exists()
    assert (output / "evaluator" / "evaluation-cases.json").read_bytes() == (
        source / "evaluation-cases.json").read_bytes()
    for overlay, entry in zip(ACCEPTANCE["fixture_adaptation"]["overlays"], manifest["notes"]):
        original = (source / "agent-input" / overlay["file"]).read_bytes()
        adapted = (output / "knowledge" / overlay["file"]).read_bytes()
        note = parse(adapted, kit.PROJECT)
        assert note.eligible and note.metadata["id"] == overlay["id"]
        assert note.body.encode("utf-8") == kit.historical_body(original)
        assert entry["source_version"] == version(adapted)
        assert entry["historical_source_version"] == version(original)
        assert entry["body_version"] == version(note.body.encode("utf-8"))
    cases = read(output / "evaluator" / "evaluation-cases.json")["cases"]
    for case in cases:
        paths = [output / "sessions" / client / case["id"] / "prompt.txt"
                 for client in ("copilot", "codex")]
        assert paths[0].read_bytes() == paths[1].read_bytes()
        assert paths[0].read_text("utf-8") == kit.PROMPT + case["question"] + "\n"
        assert list(paths[0].parent.iterdir()) == [paths[0]]
    records = read(output / "evaluator" / "results.json")
    assert len(records) == 12
    assert all(row["status"] == "NOT_RUN" and row["score"] == "UNVERIFIED" for row in records)
    assert all(row["boundary_and_leakage"] == "UNVERIFIED" for row in records)


def test_configuration_and_gated_recipes(fixture, monkeypatch):
    monkeypatch.setenv("KIT_PRIVATE_SENTINEL", "synthetic-credential-must-not-be-bundled")
    output = generate(fixture)
    settings = read(output / "config" / "local.json")
    assert settings["projects"] == [{"project": kit.PROJECT, "root": str(output / "knowledge")}]
    copilot = read(output / "config" / "copilot-mcp.json")["mcpServers"]["synthetic-memory"]
    assert Path(copilot["command"]).is_absolute()
    assert copilot["tools"] == kit.TOOLS
    assert copilot["args"] == [
        "-B", "-m", "cloud_repo_memory", "--config", str(output / "config" / "local.json")]
    override = read(output / "config" / "codex-overrides.json")[0]
    codex = tomllib.loads(override)["mcp_servers"]["synthetic_memory"]
    assert codex == {"command": str(Path(sys.executable)), "args": copilot["args"],
                     "enabled_tools": kit.TOOLS, "required": True}
    assert tomllib.loads("path=" + kit.toml_string("C:\\synthetic space\\\U0001f600")) == {
        "path": "C:\\synthetic space\\\U0001f600"}
    for path in (output / "recipes").iterdir():
        recipe = read(path)
        assert recipe["status"].startswith("BLOCKED:")
        assert recipe["model"] == "<USER_REVIEWED_MODEL>"
        assert "<USER_REVIEWED_MODEL>" in recipe["argv"]
        assert Path(recipe["cwd"]).is_absolute()
        assert not any(flag in recipe["argv"] for flag in (
            "--allow-all", "--allow-all-tools", "--allow-all-paths", "--yolo",
            "--dangerously-bypass-approvals-and-sandbox", "--resume", "--continue",
            "--enable-memory", "--ignore-rules",
        ))
        assert not any("HOME" in name or "TOKEN" in name
                       for name in recipe["environment_overrides"])
        if recipe["client"] == "copilot":
            assert "-i" in recipe["argv"] and "-p" not in recipe["argv"]
            assert recipe["environment_overrides"]["COPILOT_OTEL_EXPORTER_TYPE"] == "file"
        else:
            assert "--ignore-user-config" in recipe["argv"]
            assert "--ephemeral" in recipe["argv"] and "--json" in recipe["argv"]
            assert "--ask-for-approval" not in recipe["argv"]
            assert recipe["argv"][recipe["argv"].index("--sandbox") + 1] == "read-only"
            assert recipe["argv"][recipe["argv"].index("-c") + 1] == override
    # Only caller-supplied output/interpreter paths are embedded; no environment lookup.
    generated = b"\n".join(path.read_bytes() for path in output.rglob("*") if path.is_file())
    for forbidden in (b"auth.json", b"config.toml", b"Bearer ", b"GH_TOKEN", b"CODEX_HOME",
                      b"baseline-results", b"required_memory_ids"):
        corpus = b"\n".join(path.read_bytes() for path in (output / "knowledge").iterdir())
        assert forbidden not in corpus
    assert b"Bearer " not in generated
    assert b"synthetic-credential-must-not-be-bundled" not in generated


def test_refuse_reuse_and_outside_parent(fixture):
    output = generate(fixture)
    original = {path: path.read_bytes() for path in output.rglob("*") if path.is_file()}
    with pytest.raises(FileExistsError):
        kit.prepare(fixture.base, output, Path(sys.executable))
    assert original == {path: path.read_bytes() for path in original}
    with pytest.raises(ValueError):
        kit.prepare(fixture.base, fixture.base.parent / "escape", Path(sys.executable))
    with pytest.raises(ValueError):
        kit.prepare(fixture.base, fixture.base / "nested" / "kit", Path(sys.executable))
    with pytest.raises(ValueError):
        kit.prepare(fixture.base, fixture.base / "new", Path("python"))
    occupied = fixture.file("occupied", b"keep")
    with pytest.raises(FileExistsError):
        kit.prepare(fixture.base, occupied, Path(sys.executable))
    assert occupied.read_bytes() == b"keep"


def test_refuse_redirected_ancestor_before_writing(fixture, monkeypatch):
    original = Path.lstat

    def redirected(path, *args, **kwargs):
        if path == fixture.base:
            return SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=0x400)
        return original(path, *args, **kwargs)

    with monkeypatch.context() as patcher:
        patcher.setattr(Path, "lstat", redirected)
        with pytest.raises(ValueError, match="redirected"):
            kit.prepare(fixture.base, fixture.base / "kit", Path(sys.executable))
    assert not (fixture.base / "kit").exists()


@pytest.mark.parametrize("ending", [b"\n", b"\r\n"])
def test_historical_body_delimiters_preserve_bytes(ending):
    body = b"# Body" + ending + b"--- inside body" + ending
    raw = ending.join((b"---", b"id: kst-001", b"---", b"")) + body
    assert kit.historical_body(raw) == body
    with pytest.raises(ValueError):
        kit.historical_body(b"missing frontmatter")


def test_preparation_cli_failure_is_explicit(fixture):
    occupied = fixture.directory("occupied")
    result = subprocess.run([
        sys.executable, "-B", str(REPO / "validation" / "real_clients" / "prepare.py"),
        "--owned-parent", str(fixture.base), "--output", str(occupied),
        "--python", sys.executable,
    ], capture_output=True, text=True, check=False)
    assert result.returncode == 1 and result.stdout == ""
    assert "FileExistsError" in result.stderr and "no client was launched" in result.stderr


@pytest.mark.anyio
async def test_generated_corpus_through_real_sdk(fixture):
    output = generate(fixture)
    manifest = read(output / "evaluator" / "source-manifest.json")
    async with connect(fixture, output / "config" / "local.json") as (session, process, messages):
        assert [tool.name for tool in (await session.list_tools()).tools] == kit.TOOLS
        index = check(await session.call_tool("list_memory_index", {"project": kit.PROJECT}),
                      "list_memory_index")
        assert index["entry_count"] == 5 and index["excluded_count"] == 0
        assert index["index_utf8_bytes"] == len(index["index_markdown"].encode("utf-8"))
        for entry in manifest["notes"]:
            assert entry["memory_id"] in index["index_markdown"]
            assert entry["source_version"] in index["index_markdown"]
            body = check(await session.call_tool("get_memory", {
                "project": kit.PROJECT, "memory_id": entry["memory_id"],
                "expected_version": entry["source_version"],
            }))
            assert body["source_version"] == entry["source_version"]
            assert body["source_utf8_bytes"] == entry["source_utf8_bytes"]
            assert version(body["body_markdown"].encode("utf-8")) == entry["body_version"]
        # This snapshot is produced by MCP, never copied from historical MEMORY.md.
        fixture.file(output / "evaluator" / "sdk-index.json", kit.json_bytes(index))
    assert process.returncode == 0
