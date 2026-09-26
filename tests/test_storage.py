import itertools
import json
import os
from unittest.mock import patch

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from cloud_repo_memory import storage
from cloud_repo_memory.metadata import version
from cloud_repo_memory.storage import ConfigurationError, MemoryStore
from support import REPO, adapt_kusto, config, source

SCHEMA = json.loads((REPO / "contracts" / "local-mvp-v1.schema.json").read_text("utf-8"))


def check(result, tool="list", code=None):
    definition = "listMemoryIndexOutput" if tool == "list" else "getMemoryOutput"
    Draft202012Validator({"$defs": SCHEMA["$defs"], "$ref": "#/$defs/" + definition},
                        format_checker=FormatChecker()).validate(result)
    assert result["ok"] == (code is None), result
    if code:
        assert result["error"]["code"] == code, result
        assert not any(key in result for key in ("body_markdown", "index_markdown", "metadata"))
    elif tool == "list":
        raw = result["index_markdown"].encode("utf-8")
        assert len(raw) == result["index_utf8_bytes"]
        assert version(raw) == result["index_version"]
        assert result["entry_count"] + result["excluded_count"] <= 200
    else:
        assert result["project"] == result["metadata"]["project"]
        assert result["memory_id"] == result["metadata"]["id"]
    assert result["observation"]["elapsed_ms"] >= 0
    encoded = json.dumps(result)
    for private in ("cleanup_confirmed", "supervisor_state", "decision_ms", "worker_metrics",
                    "fixture-", "Traceback"):
        assert private not in encoded
    return result


@pytest.fixture
def project(fixture):
    root = fixture.directory("project")
    return root, MemoryStore(config(("sample-telemetry", root)))


def test_kusto_index_then_exact_bodies_rename_repeat(fixture, project):
    root, store = project
    bodies = adapt_kusto(fixture, root)
    first = check(store.list_memory_index("sample-telemetry"))
    assert first["entry_count"] == 5
    for memory_id, (path, note) in bodies.items():
        result = check(store.get_memory("sample-telemetry", memory_id, note.version), "get")
        assert result["body_markdown"] == note.body
        assert result["source_version"] == version(path.read_bytes())
        assert result["source_utf8_bytes"] == len(path.read_bytes())
    path, _ = bodies["kst-001"]
    renamed = root / "renamed.MD"
    fixture.files.append(renamed)
    path.rename(renamed)
    second = check(store.list_memory_index("sample-telemetry"))
    assert first["index_markdown"] == second["index_markdown"]
    assert first["index_version"] == second["index_version"]
    check(store.get_memory("sample-telemetry", "kst-001"), "get")


@pytest.mark.parametrize("status,approval", itertools.product(
    ["draft", "active", "archived", "superseded"], ["pending", "approved", "rejected"]))
def test_all_lifecycle_outputs(fixture, project, status, approval):
    root, store = project
    fixture.file(root / "note.md", source(status=status, approval=approval))
    eligible = status == "active" and approval == "approved"
    result = check(store.list_memory_index("sample-telemetry"))
    assert (result["entry_count"], result["excluded_count"]) == (int(eligible), int(not eligible))
    result = check(store.get_memory("sample-telemetry", "note-001"), "get",
                   None if eligible else "MEMORY_INELIGIBLE")
    if not eligible:
        assert result["error"]["scan_complete"]


def test_update_metadata_body_version_demote_delete(fixture, project):
    root, store = project
    path = fixture.file(root / "note.md", source())
    first = check(store.get_memory("sample-telemetry", "note-001"), "get")
    path.write_bytes(source(body="new body\r\n"))
    check(store.get_memory("sample-telemetry", "note-001", first["source_version"]),
          "get", "MEMORY_CHANGED")
    assert check(store.get_memory("sample-telemetry", "note-001"), "get")["body_markdown"] == "new body\r\n"
    path.write_bytes(source(title="Changed title", status="archived"))
    check(store.get_memory("sample-telemetry", "note-001", first["source_version"]),
          "get", "MEMORY_INELIGIBLE")
    path.write_bytes(source(title="Changed title"))
    assert "Changed title" in check(store.list_memory_index("sample-telemetry"))["index_markdown"]
    path.unlink()
    check(store.get_memory("sample-telemetry", "note-001", first["source_version"]),
          "get", "MEMORY_NOT_FOUND")


@pytest.mark.parametrize("bad", ["../x", "..\\x", "C:\\x", "/x", "%2e%2e", "Upper", "/", ".", "\0",
                                 "x\n", None, 42, [], {}])
def test_invalid_arguments_before_filesystem(project, bad):
    _, store = project
    with patch.object(storage, "_job") as job:
        check(store.list_memory_index(bad), code="INVALID_ARGUMENT")
        check(store.get_memory("sample-telemetry", bad), "get", "INVALID_ARGUMENT")
        job.assert_not_called()


def test_unknown_arguments_ids_projects(project):
    _, store = project
    with patch.object(storage, "_job") as job:
        check(store.list_memory_index(), code="INVALID_ARGUMENT")
        check(store.get_memory("sample-telemetry"), "get", "INVALID_ARGUMENT")
        check(store.list_memory_index("sample-telemetry", path="secret"), code="INVALID_ARGUMENT")
        check(store.get_memory("sample-telemetry", "n", remote_url="secret"), "get", "INVALID_ARGUMENT")
        check(store.get_memory("sample-telemetry", "n", "latest"), "get", "INVALID_ARGUMENT")
        check(store.list_memory_index("unknown"), code="UNKNOWN_PROJECT")
        check(store.get_memory("unknown", "n"), "get", "UNKNOWN_PROJECT")
        job.assert_not_called()
    check(store.get_memory("sample-telemetry", "absent"), "get", "MEMORY_NOT_FOUND")


def test_project_scoping_missing_and_replaced_root(fixture):
    alpha, beta = fixture.directory("alpha"), fixture.directory("beta")
    fixture.file(alpha / "note.md", source("shared", "alpha", body="alpha"))
    fixture.file(beta / "note.md", source("shared", "beta", body="beta"))
    fixture.file(beta / "only.md", source("beta-only", "beta"))
    missing = fixture.base / "missing"
    store = MemoryStore(config(("alpha", alpha), ("beta", beta), ("missing", missing)))
    assert check(store.get_memory("alpha", "shared"), "get")["body_markdown"] == "alpha"
    assert check(store.get_memory("beta", "shared"), "get")["body_markdown"] == "beta"
    check(store.get_memory("alpha", "beta-only"), "get", "MEMORY_NOT_FOUND")
    check(store.list_memory_index("missing"), code="PROJECT_UNAVAILABLE")
    fixture.directory("missing")
    check(store.list_memory_index("missing"))
    moved = fixture.base / "moved"
    missing.rename(moved)
    fixture.dirs.append(moved)
    missing.mkdir()
    check(store.list_memory_index("missing"), code="LOCAL_CHANGE_DETECTED")
    check(store.list_memory_index("alpha"))


@pytest.mark.parametrize("lifecycle", ["active", "archived"])
def test_duplicates_even_ineligible(fixture, project, lifecycle):
    root, store = project
    fixture.file(root / "first.md", source())
    fixture.file(root / "conflict.md", source(status=lifecycle, body="conflict"))
    for result in (store.list_memory_index("sample-telemetry"),
                   store.get_memory("sample-telemetry", "unrelated")):
        check(result, "get" if "memory_id" in result else "list", "DUPLICATE_ID")
        assert result["error"]["scan_complete"]


def test_metadata_availability_precedence_and_diagnostic_cap(fixture, project):
    root, store = project
    for index in range(25):
        fixture.file(root / f"invalid-{index}.md", b"invalid synthetic")
    first = check(store.list_memory_index("sample-telemetry"), code="INVALID_METADATA")
    assert len(first["error"]["diagnostics"]) == 20
    assert first["error"]["diagnostics_omitted"] == 5
    assert not first["error"]["scan_complete"]
    locked = fixture.file(root / "locked.md", source())
    fixture.file(root / "valid.md", source("valid"))
    with locked.open("r+b"):
        result = check(store.get_memory("sample-telemetry", "valid"), "get", "FILE_UNAVAILABLE")
        assert any(d["code"] == "FILE_UNAVAILABLE" for d in result["error"]["diagnostics"])
        assert result["error"]["diagnostics_omitted"] >= 6


def test_invalid_ineligible_blocks_project_and_collects_duplicates(fixture, project):
    root, store = project
    fixture.file(root / "invalid.md", source(title=" ", status="archived"))
    fixture.file(root / "duplicate.md", source())
    result = check(store.get_memory("sample-telemetry", "note-001"), "get", "INVALID_METADATA")
    assert {d["code"] for d in result["error"]["diagnostics"]} == {
        "DUPLICATE_ID", "INVALID_METADATA"}


def test_reserved_root_nested_hidden_and_uppercase(fixture, project):
    root, store = project
    fixture.file(root / "MEMORY.md", b"ignored invalid")
    fixture.file(root / "ignore.json", b"ignored evaluator-like data")
    check(store.list_memory_index("sample-telemetry"))
    hidden = fixture.directory(root / ".hidden")
    fixture.file(hidden / "valid.MD", source())
    assert check(store.list_memory_index("sample-telemetry"))["entry_count"] == 1
    fixture.file(hidden / "MEMORY.md", b"invalid nested")
    check(store.list_memory_index("sample-telemetry"), code="INVALID_METADATA")


def test_hardlink_refusal_precedes_collected_errors(fixture, project):
    root, store = project
    fixture.file(root / "bad.md", b"invalid")
    original = fixture.file(root / "note.md", source())
    linked = root / "linked.md"
    os.link(original, linked)
    fixture.files.append(linked)
    check(store.list_memory_index("sample-telemetry"), code="SCOPE_VIOLATION")


def test_candidate_limit_no_truncation(fixture, project):
    root, store = project
    for index in range(200):
        fixture.file(root / f"n-{index}.md", source(f"n-{index}"))
    assert check(store.list_memory_index("sample-telemetry"))["entry_count"] == 200
    fixture.file(root / "overflow.md", source("overflow"))
    check(store.list_memory_index("sample-telemetry"), code="LIMIT_EXCEEDED")


def test_source_byte_and_frontmatter_limits(fixture, project):
    root, store = project
    raw = source(body="")
    exact = raw + b"x" * (262144 - len(raw))
    path = fixture.file(root / "note.md", exact)
    result = check(store.get_memory("sample-telemetry", "note-001"), "get")
    assert result["source_utf8_bytes"] == 262144
    assert result["source_version"] == version(exact)
    path.write_bytes(exact + b"x")
    check(store.list_memory_index("sample-telemetry"), code="LIMIT_EXCEEDED")
    exact_front = raw[:-4] + b"#" + b"x" * (8192 - len(raw) - 2) + b"\n---\n"
    path.write_bytes(exact_front)
    check(store.list_memory_index("sample-telemetry"))
    path.write_bytes(exact_front.replace(b"#x", b"#xx", 1))
    check(store.list_memory_index("sample-telemetry"), code="LIMIT_EXCEEDED")


def test_aggregate_source_limit_with_valid_metadata(fixture, project):
    root, store = project
    for index in range(64):
        raw = source(f"n-{index}", body="")
        fixture.file(root / f"n-{index}.md", raw + b"x" * (262144 - len(raw)))
    assert check(store.list_memory_index("sample-telemetry"))["entry_count"] == 64
    fixture.file(root / "overflow.md", source("overflow"))
    check(store.list_memory_index("sample-telemetry"), code="LIMIT_EXCEEDED")


def test_render_limit_never_returns_partial_index(fixture, project):
    from cloud_repo_memory.metadata import parse, render

    root, store = project
    notes = [parse(source(f"n-{index}", title="x", summary="x", read_when="x"),
                   "sample-telemetry") for index in range(200)]
    remaining = 131072 - len(render("sample-telemetry", notes).encode())
    for index, note in enumerate(notes):
        for field, maximum in (("title", 120), ("summary", 280), ("read_when", 280)):
            add = min(remaining, maximum - 1)
            note.metadata[field] += "x" * add
            remaining -= add
        fixture.file(root / f"n-{index}.md", source(f"n-{index}", **{
            field: note.metadata[field] for field in ("title", "summary", "read_when")}))
    assert check(store.list_memory_index("sample-telemetry"))["index_utf8_bytes"] == 131072
    (root / "n-199.md").write_bytes(source("n-199", title="x", summary="xx", read_when="x"))
    check(store.list_memory_index("sample-telemetry"), code="LIMIT_EXCEEDED")


def test_root_becomes_regular_file_and_other_mapping_works(fixture):
    root, other = fixture.directory("project"), fixture.directory("other")
    store = MemoryStore(config(("p", root), ("q", other)))
    root.rmdir()
    fixture.file(root, b"not a directory")
    check(store.list_memory_index("p"), code="PROJECT_UNAVAILABLE")
    check(store.list_memory_index("q"))
    root.unlink()


@pytest.mark.parametrize("root", ["relative", "C:relative", "\\\\server\\share", "\\\\?\\C:\\x",
                                  "C:\\x\\..\\y", "C:\\x:stream", "C:/x", "C:\\%HOME%", "C:\\$HOME"])
def test_configuration_bad_roots(root, capsys):
    with pytest.raises(ConfigurationError):
        MemoryStore(config(("p", root)))
    output = capsys.readouterr()
    assert not output.out
    assert "startup refused" in output.err
    assert root not in output.err


def test_configuration_overlaps_duplicate_keys_and_types(fixture, capsys):
    root = fixture.directory("project")
    for configuration in (
        config(("p", root), ("p", fixture.base / "other")),
        config(("p", root), ("q", str(root).upper())),
        config(("p", root), ("q", root / "nested")),
        {"schema_version": True, "projects": [{"project": "p", "root": str(root)}]},
        {"schema_version": 1, "projects": []},
    ):
        with pytest.raises(ConfigurationError):
            MemoryStore(configuration)
    path = fixture.file("config.json", b'{"schema_version":1,"schema_version":1,"projects":[]}')
    with pytest.raises(ConfigurationError):
        MemoryStore.from_json(path)
    path.write_text(json.dumps(config(("p", root))), encoding="utf-8")
    check(MemoryStore.from_json(path).list_memory_index("p"))
    inside = fixture.file(root / "config.json", path.read_bytes())
    with pytest.raises(ConfigurationError):
        MemoryStore.from_json(inside)
    assert not capsys.readouterr().out


@pytest.mark.parametrize("evidence", [
    "real OneDrive local placeholder reads", "real hydration cancellation and cleanup",
    "actual ACL-denial layout", "volume-mount and non-NTFS devices",
    "case-sensitive NTFS directories and mapped-file writers", "two MCP clients and tokenizer",
    "second-device update and deletion",
])
def test_missing_platform_and_pilot_evidence(evidence):
    pytest.skip("BLOCKED: " + evidence)
