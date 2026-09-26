"""Owned synthetic fixture ledger, shared by tests and the measurement runner."""

import json
import os
from pathlib import Path
import tempfile

from cloud_repo_memory.metadata import parse

REPO = Path(__file__).resolve().parents[1]
ACCEPTANCE = json.loads((REPO / "validation" / "local-mvp-acceptance.json").read_text("utf-8"))


class Fixture:
    def __init__(self):
        self.base = Path(tempfile.mkdtemp(prefix="fixture-", dir=Path(__file__).parent))
        self.files, self.dirs = [], [self.base]

    def directory(self, name):
        path = self.base / name
        path.mkdir()
        self.dirs.append(path)
        return path

    def file(self, name, content):
        path = self.base / name
        path.write_bytes(content)
        self.files.append(path)
        return path

    def clean(self):
        for path in reversed(self.files):
            if os.path.lexists(path):
                parent = path.parent
                while parent != self.base.parent:
                    if os.lstat(parent).st_file_attributes & 0x400:
                        raise RuntimeError("Refusing redirected fixture cleanup")
                    parent = parent.parent
                os.unlink(path)
        for path in reversed(self.dirs):
            if os.path.lexists(path):
                os.rmdir(path)


def source(memory_id="note-001", project="sample-telemetry", body="# Synthetic\n",
           **changes):
    values = {"schema_version": 1, "id": memory_id, "project": project,
              "title": "Synthetic title", "summary": "Synthetic summary",
              "read_when": "Synthetic investigation", "status": "active",
              "approval": "approved", **changes}
    return ("---\n" + "".join(f"{key}: {json.dumps(value, ensure_ascii=False)}\n"
                             for key, value in values.items()) + "---\n" + body).encode("utf-8")


def config(*roots):
    return {"schema_version": 1, "projects": [
        {"project": name, "root": str(path)} for name, path in roots]}


def adapt_kusto(fixture, root):
    bodies = {}
    base = REPO / "validation" / "samples" / "kusto-memory" / "agent-input"
    for overlay in ACCEPTANCE["fixture_adaptation"]["overlays"]:
        raw = (base / overlay["file"]).read_bytes()
        body = raw.split(b"---", 2)[2]
        body = body[2:] if body.startswith(b"\r\n") else body[1:]
        data = source(overlay["id"], body=body.decode("utf-8"),
                      **{key: overlay[key] for key in ("title", "summary", "read_when")})
        path = fixture.file(root / overlay["file"], data)
        bodies[overlay["id"]] = (path, parse(data, "sample-telemetry"))
    return bodies
