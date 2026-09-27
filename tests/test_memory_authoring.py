import itertools

import pytest
from jsonschema import Draft202012Validator

from cloud_repo_memory.metadata import FIELDS, SourceError, parse, version
from cloud_repo_memory.schemas import tool_schema
from cloud_repo_memory.storage import MemoryStore
from support import REPO, config

TEMPLATE = REPO / "docs" / "templates" / "local-v1-note.md.example"
GUIDE = REPO / "docs" / "memory-authoring.md"
PROJECT = "example-paper-lantern"
MEMORY_ID = "example-paper-lantern-checklist"


def template_source(status="draft", approval="pending"):
    return (TEMPLATE.read_bytes()
            .replace(b"status: draft", f"status: {status}".encode(), 1)
            .replace(b"approval: pending", f"approval: {approval}".encode(), 1))


def lifecycle_examples():
    table = GUIDE.read_text("utf-8").split(
        "| status | pending | approved | rejected |\n", 1)[1].split("\n\n", 1)[0]
    examples = []
    for row in table.splitlines()[1:]:
        status, *cells = [cell.strip() for cell in row.strip("|").split("|")]
        assert len(cells) == 3
        for approval, cell in zip(("pending", "approved", "rejected"), cells):
            assert cell in ("yes", "no")
            examples.append((status, approval, cell == "yes"))
    return examples


EXAMPLES = lifecycle_examples()


def check(result, definition, code=None):
    Draft202012Validator(tool_schema(definition)).validate(result)
    assert result["ok"] == (code is None), result
    if code:
        assert result["error"]["code"] == code, result
        assert not {"body_markdown", "metadata", "index_markdown"} & result.keys()
    return result


def test_copyable_template_is_valid_but_not_publishable_by_default():
    raw = TEMPLATE.read_bytes()
    note = parse(raw, PROJECT)
    Draft202012Validator(tool_schema("frontmatter")).validate(note.metadata)
    assert set(note.metadata) == set(FIELDS)
    assert note.metadata["id"] == MEMORY_ID
    assert (note.metadata["status"], note.metadata["approval"]) == ("draft", "pending")
    assert not note.eligible
    assert note.version == version(raw)
    assert note.size == len(raw)
    assert "This is a template, not project knowledge." in note.body
    assert TEMPLATE.suffix.lower() != ".md"
    with pytest.raises(SourceError, match="INVALID_METADATA"):
        parse(raw, "different-project")


def test_documented_lifecycle_matrix_is_complete():
    properties = tool_schema("frontmatter")["properties"]
    combinations = set(itertools.product(properties["status"]["enum"],
                                         properties["approval"]["enum"]))
    assert len(EXAMPLES) == len(combinations)
    assert {(status, approval) for status, approval, _ in EXAMPLES} == combinations
    assert [(status, approval) for status, approval, eligible in EXAMPLES if eligible] == [
        ("active", "approved")]


@pytest.mark.parametrize("status,approval,eligible", EXAMPLES)
def test_documented_lifecycle_matches_parser_and_schema(status, approval, eligible):
    note = parse(template_source(status, approval), PROJECT)
    Draft202012Validator(tool_schema("frontmatter")).validate(note.metadata)
    assert note.eligible == eligible
    assert Draft202012Validator(tool_schema("eligibleFrontmatter")).is_valid(
        note.metadata) == eligible


@pytest.mark.parametrize("status,approval,eligible", EXAMPLES)
def test_documented_lifecycle_matches_storage(fixture, status, approval, eligible):
    root = fixture.directory("project")
    fixture.file(root / "note.md", template_source(status, approval))
    store = MemoryStore(config((PROJECT, root)))
    index = check(store.list_memory_index(PROJECT), "listMemoryIndexOutput")
    assert (index["entry_count"], index["excluded_count"]) == (int(eligible), int(not eligible))
    check(store.get_memory(PROJECT, MEMORY_ID), "getMemoryOutput",
          None if eligible else "MEMORY_INELIGIBLE")


def test_unadapted_template_filename_is_not_discovered(fixture):
    root = fixture.directory("project")
    fixture.file(root / TEMPLATE.name, TEMPLATE.read_bytes())
    store = MemoryStore(config((PROJECT, root)))
    index = check(store.list_memory_index(PROJECT), "listMemoryIndexOutput")
    assert (index["entry_count"], index["excluded_count"]) == (0, 0)
    check(store.get_memory(PROJECT, MEMORY_ID), "getMemoryOutput", "MEMORY_NOT_FOUND")


def test_template_edit_changes_exact_source_and_index_versions(fixture):
    root = fixture.directory("project")
    raw = template_source("active", "approved")
    path = fixture.file(root / "note.md", raw)
    store = MemoryStore(config((PROJECT, root)))
    first = check(store.list_memory_index(PROJECT), "listMemoryIndexOutput")
    prior = parse(raw, PROJECT)
    assert prior.version in first["index_markdown"]
    changed = raw + b"\nSynthetic review update.\n"
    path.write_bytes(changed)
    check(store.get_memory(PROJECT, MEMORY_ID, prior.version), "getMemoryOutput", "MEMORY_CHANGED")
    second = check(store.list_memory_index(PROJECT), "listMemoryIndexOutput")
    assert first["index_version"] != second["index_version"]
    current = check(store.get_memory(PROJECT, MEMORY_ID, version(changed)), "getMemoryOutput")
    assert current["body_markdown"] == parse(changed, PROJECT).body
    assert current["source_version"] in second["index_markdown"]
    renamed = root / "renamed.md"
    fixture.files.append(renamed)
    path.rename(renamed)
    assert check(store.list_memory_index(PROJECT), "listMemoryIndexOutput")[
        "index_version"] == second["index_version"]
    renamed.write_bytes(changed.replace(b"status: active", b"status: archived", 1))
    check(store.get_memory(PROJECT, MEMORY_ID, current["source_version"]),
          "getMemoryOutput", "MEMORY_INELIGIBLE")
    withdrawn = check(store.list_memory_index(PROJECT), "listMemoryIndexOutput")
    assert (withdrawn["entry_count"], withdrawn["excluded_count"]) == (0, 1)
    renamed.write_bytes(renamed.read_bytes() + b"\nRetirement context.\n")
    assert check(store.list_memory_index(PROJECT), "listMemoryIndexOutput")[
        "index_version"] == withdrawn["index_version"]
    renamed.unlink()
    check(store.get_memory(PROJECT, MEMORY_ID), "getMemoryOutput", "MEMORY_NOT_FOUND")


@pytest.mark.parametrize("fault,code", [
    ("duplicate", "DUPLICATE_ID"), ("invalid", "INVALID_METADATA"),
])
def test_retired_template_can_block_unrelated_valid_note(fixture, fault, code):
    root = fixture.directory("project")
    raw = template_source("active", "approved")
    fixture.file(root / "valid.md", raw)
    retired = template_source("archived", "approved").replace(
        MEMORY_ID.encode(), b"retired-example", 1)
    fixture.file(root / "retired.md", retired)
    if fault == "duplicate":
        fixture.file(root / "conflict.md", retired)
    else:
        fixture.file(root / "invalid.md", retired.replace(
            b"project: " + PROJECT.encode(), b"project: different-project", 1))
    store = MemoryStore(config((PROJECT, root)))
    check(store.list_memory_index(PROJECT), "listMemoryIndexOutput", code)
    check(store.get_memory(PROJECT, MEMORY_ID), "getMemoryOutput", code)
