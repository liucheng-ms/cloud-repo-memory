import itertools
import json

import pytest
from jsonschema import Draft202012Validator

from cloud_repo_memory.metadata import (
    FIELDS, Note, SourceError, escape, parse, render, version,
)
from support import ACCEPTANCE, REPO, source


@pytest.mark.parametrize("example", ACCEPTANCE["schema_examples"], ids=lambda e: e["id"])
def test_specification_schema_examples(example):
    schema = json.loads((REPO / "contracts" / "local-mvp-v1.schema.json").read_text("utf-8"))
    validator = Draft202012Validator({"$ref": "#/$defs/" + example["definition"],
                                     "$defs": schema["$defs"]})
    assert validator.is_valid(example["value"]) == example["valid"]


@pytest.mark.parametrize("newline,bom,body", itertools.product(
    ["\n", "\r\n"], [b"", b"\xef\xbb\xbf"], ["", "\n# Exact\n\n  body \n", "雪🙂\n"]))
def test_exact_source_bytes(newline, bom, body):
    raw = bom + source(body=body, title="雪🙂").replace(b"\n", newline.encode())
    note = parse(raw, "sample-telemetry")
    assert note.body == body.replace("\n", newline)
    assert note.size == len(raw)
    assert note.version == version(raw)
    assert note.metadata["title"] == "雪🙂"


@pytest.mark.parametrize("status,approval", itertools.product(
    ["draft", "active", "archived", "superseded"], ["pending", "approved", "rejected"]))
def test_lifecycle_matrix(status, approval):
    note = parse(source(status=status, approval=approval), "sample-telemetry")
    assert note.eligible == (status == "active" and approval == "approved")


@pytest.mark.parametrize("field", FIELDS)
def test_each_missing_field(field):
    raw = b"\n".join(line for line in source().split(b"\n")
                     if not line.startswith(field.encode() + b":"))
    with pytest.raises(SourceError, match="INVALID_METADATA"):
        parse(raw, "sample-telemetry")


@pytest.mark.parametrize("field", FIELDS)
@pytest.mark.parametrize("value", [None, [], {}, True, 1.0])
def test_wrong_scalar_types(field, value):
    with pytest.raises(SourceError, match="INVALID_METADATA"):
        parse(source(**{field: value}), "sample-telemetry")


@pytest.mark.parametrize("field", ["title", "summary", "read_when"])
@pytest.mark.parametrize("text", ["", " ", " x", "x ", "x\nx", "x\tx", "x\x00",
                                  "x\x7f", "x\u2028", "x\u2029", "\u00a0x", "x\u00a0"])
def test_text_constraints(field, text):
    with pytest.raises(SourceError, match="INVALID_METADATA"):
        parse(source(**{field: text}), "sample-telemetry")


@pytest.mark.parametrize("field,limit", [("title", 120), ("summary", 280), ("read_when", 280)])
def test_text_inclusive_lengths(field, limit):
    assert parse(source(**{field: "雪" * limit}), "sample-telemetry")
    with pytest.raises(SourceError):
        parse(source(**{field: "雪" * (limit + 1)}), "sample-telemetry")


@pytest.mark.parametrize("change", [
    {"extra": "no"}, {"schema_version": "1"}, {"schema_version": 2},
    {"status": "unknown"}, {"approval": "unknown"}, {"project": "other"},
    {"id": "../bad"}, {"id": "Upper"}, {"id": "x" * 65},
])
def test_other_metadata_errors(change):
    with pytest.raises(SourceError, match="INVALID_METADATA"):
        parse(source(**change), "sample-telemetry")


@pytest.mark.parametrize("addition", [
    b"id: note-001\n", b"title: &title hi\n", b"title: *title\n",
    b"title: !!str hi\n", b"title: !custom hi\n", b"<<: {id: note-001}\n",
])
def test_forbidden_yaml_features(addition):
    raw = source().replace(b"---\n#", addition + b"---\n#", 1)
    with pytest.raises(SourceError, match="INVALID_METADATA"):
        parse(raw, "sample-telemetry")


@pytest.mark.parametrize("raw", [b"", b"---\nx: y\n", b" ---\nx\n---\n",
                                 source() + b"\xff", b"\xef\xbb\xbf\xef\xbb\xbf" + source()])
def test_invalid_source_format(raw):
    with pytest.raises(SourceError, match="INVALID_METADATA"):
        parse(raw, "sample-telemetry")


def test_yaml_12_no_date_or_boolean_string_coercion():
    raw = source().replace(b'"Synthetic title"', b"yes")
    assert parse(raw, "sample-telemetry").metadata["title"] == "yes"
    for replacement in (b"true", b"2026-09-26", b"123"):
        with pytest.raises(SourceError):
            parse(source().replace(b'"Synthetic title"', replacement), "sample-telemetry")


def test_escaped_surrogate_is_invalid_metadata():
    with pytest.raises(SourceError, match="INVALID_METADATA"):
        parse(source().replace(b'"Synthetic title"', b'"\\uD800"'), "sample-telemetry")


def test_frontmatter_inclusive_byte_limit():
    raw = source(body="")
    exact = raw[:-4] + b"#" + b"x" * (8192 - len(raw) - 2) + b"\n---\n"
    assert len(exact) == 8192
    assert parse(exact, "sample-telemetry").body == ""
    with pytest.raises(SourceError, match="LIMIT_EXCEEDED"):
        parse(exact.replace(b"#x", b"#xx", 1), "sample-telemetry")


def test_literal_markdown_and_sorting():
    text = r"&<>\`*_{}[]()#+-.!|"
    escaped = r"&amp;&lt;&gt;\\\`\*\_\{\}\[\]\(\)\#\+\-\.\!\|"
    assert escape(text) == escaped
    first = parse(source("a", title=text, summary=text, read_when=text), "sample-telemetry")
    second = parse(source("z", body="not in directory"), "sample-telemetry")
    actual = render("sample-telemetry", [second, first])
    expected = ("# Memory index: sample-telemetry\n\n"
                "Read relevant bodies with get_memory; summaries are navigation only.\n\n"
                f"- **a** \u2014 {escaped}\n  Summary: {escaped}\n  Read when: {escaped}\n"
                f"  Version: {first.version}\n"
                "- **z** \u2014 Synthetic title\n  Summary: Synthetic summary\n"
                f"  Read when: Synthetic investigation\n  Version: {second.version}\n")
    assert actual == expected
    assert actual == render("sample-telemetry", [first, second])
    assert render("sample-telemetry", []).endswith("No eligible memories.\n")


def test_inclusive_index_bytes_no_truncation():
    notes = [parse(source(f"n-{index}", title="x", summary="x", read_when="x"),
                   "sample-telemetry") for index in range(200)]
    remaining = 131072 - len(render("sample-telemetry", notes).encode())
    for note in notes:
        for field, maximum in (("title", 120), ("summary", 280), ("read_when", 280)):
            add = min(remaining, maximum - 1)
            note.metadata[field] += "x" * add
            remaining -= add
    assert remaining == 0
    assert len(render("sample-telemetry", notes).encode()) == 131072
    notes[-1].metadata["summary"] += "x"
    with pytest.raises(SourceError, match="LIMIT_EXCEEDED"):
        render("sample-telemetry", notes)
