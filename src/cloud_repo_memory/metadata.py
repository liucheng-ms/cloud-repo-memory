"""Strict YAML 1.2 frontmatter and deterministic literal index rendering."""

from dataclasses import dataclass
import hashlib
import re
from typing import Literal, TypedDict

from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError
from ruamel.yaml.tokens import AliasToken, AnchorToken, KeyToken, ScalarToken, TagToken

MAX_FRONTMATTER = 8192
MAX_INDEX = 131072
FIELDS = ("schema_version", "id", "project", "title", "summary", "read_when",
          "status", "approval")
SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z", re.ASCII)
VERSION = re.compile(r"sha256:[0-9a-f]{64}\Z", re.ASCII)


class Metadata(TypedDict):
    schema_version: int
    id: str
    project: str
    title: str
    summary: str
    read_when: str
    status: Literal["draft", "active", "archived", "superseded"]
    approval: Literal["pending", "approved", "rejected"]


class SourceError(Exception):
    def __init__(self, code: str, memory_id: str | None = None,
                 field: str | None = None):
        super().__init__(code)
        self.code, self.memory_id, self.field = code, memory_id, field


@dataclass(frozen=True)
class Note:
    metadata: Metadata
    body: str
    version: str
    size: int

    @property
    def eligible(self) -> bool:
        return self.metadata["status"] == "active" and self.metadata["approval"] == "approved"


def identifier(value: object) -> bool:
    return isinstance(value, str) and 1 <= len(value) <= 64 and SLUG.fullmatch(value) is not None


def version(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def parse(data: bytes, project: str) -> Note:
    offset = 3 if data.startswith(b"\xef\xbb\xbf") else 0
    first = re.match(rb"---\r?\n", data[offset:])
    if first is None:
        raise SourceError("INVALID_METADATA")
    start = offset + first.end()
    end, body_start = start, None
    while end <= len(data):
        newline = data.find(b"\n", end)
        next_line = len(data) if newline < 0 else newline + 1
        line = data[end:next_line]
        if line in (b"---\n", b"---\r\n", b"---"):
            body_start = next_line
            break
        if next_line > MAX_FRONTMATTER:
            raise SourceError("LIMIT_EXCEEDED")
        if newline < 0:
            break
        end = next_line
    if body_start is None:
        raise SourceError("INVALID_METADATA")
    if body_start > MAX_FRONTMATTER:
        raise SourceError("LIMIT_EXCEEDED")
    try:
        text = data[start:end].decode("utf-8")
        body = data[body_start:].decode("utf-8")
        yaml = YAML(typ="safe", pure=True)
        yaml.version = (1, 2)
        yaml.allow_duplicate_keys = False
        key = False
        for token in yaml.scan(text):
            if (isinstance(token, (AliasToken, AnchorToken, TagToken))
                    or key and isinstance(token, ScalarToken) and token.value == "<<"):
                raise SourceError("INVALID_METADATA")
            key = isinstance(token, KeyToken)
        # Explicit directives may not change the required scalar semantics.
        if any(line.startswith("%") for line in text.splitlines()):
            raise SourceError("INVALID_METADATA")
        value = yaml.load(text)
    except (UnicodeError, YAMLError, ValueError, RecursionError):
        raise SourceError("INVALID_METADATA") from None
    return Note(validate_metadata(value, project), body, version(data), len(data))


def validate_metadata(value: object, project: str) -> Metadata:
    if not isinstance(value, dict):
        raise SourceError("INVALID_METADATA")
    memory_id = value.get("id") if identifier(value.get("id")) else None
    if set(value) != set(FIELDS):
        raise SourceError("INVALID_METADATA", memory_id)
    for field in FIELDS:
        item = value[field]
        valid = type(item) is int and item == 1 if field == "schema_version" else type(item) is str
        if valid and field in ("id", "project"):
            valid = identifier(item)
        if valid and field == "project":
            valid = item == project
        if valid and field in ("title", "summary", "read_when"):
            valid = (0 < len(item) <= (120 if field == "title" else 280)
                     and item.strip() == item and bool(item.strip())
                     and not any(ord(char) < 32 or ord(char) == 127
                                 or char in "\u2028\u2029"
                                 or 0xD800 <= ord(char) <= 0xDFFF for char in item))
        if valid and field == "status":
            valid = item in ("draft", "active", "archived", "superseded")
        if valid and field == "approval":
            valid = item in ("pending", "approved", "rejected")
        if not valid:
            raise SourceError("INVALID_METADATA", memory_id, field)
    metadata = Metadata(schema_version=value["schema_version"], id=value["id"],
                        project=value["project"], title=value["title"],
                        summary=value["summary"], read_when=value["read_when"],
                        status=value["status"], approval=value["approval"])
    return metadata


def escape(text: str) -> str:
    entities = {"&": "&amp;", "<": "&lt;", ">": "&gt;"}
    punctuation = "\\`*_{}[]()#+-.!|"
    return "".join(entities.get(char, "\\" + char if char in punctuation else char)
                   for char in text)


def render(project: str, notes: list[Note]) -> str:
    lines = [f"# Memory index: {project}\n\n",
             "Read relevant bodies with get_memory; summaries are navigation only.\n\n"]
    size = len("".join(lines).encode("utf-8"))
    for note in sorted(notes, key=lambda note: note.metadata["id"]):
        meta = note.metadata
        entry = (f"- **{meta['id']}** \u2014 {escape(meta['title'])}\n"
                 f"  Summary: {escape(meta['summary'])}\n"
                 f"  Read when: {escape(meta['read_when'])}\n"
                 f"  Version: {note.version}\n")
        size += len(entry.encode("utf-8"))
        if size > MAX_INDEX:
            raise SourceError("LIMIT_EXCEEDED")
        lines.append(entry)
    if not notes:
        lines.append("No eligible memories.\n")
    return "".join(lines)
