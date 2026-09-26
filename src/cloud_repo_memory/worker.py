"""Private filesystem worker. Never a public tool response or test-mode entrypoint."""

import time

IMPORT_STARTED = time.monotonic()

from contextlib import ExitStack
import json
import sys
from typing import Any

from .metadata import Note, SourceError, parse, render, version
from .results import diagnostic, failure
from .winfs import Refusal, Root, Scanner

IMPORT_MS = (time.monotonic() - IMPORT_STARTED) * 1000


def emit(kind: str, **fields: Any) -> None:
    print(json.dumps({"kind": kind, "at": time.monotonic(), **fields},
                     ensure_ascii=True), flush=True)


def execute(request: dict[str, Any]) -> dict[str, Any]:
    expected = request.get("identity")
    root = Root(request["root"], tuple(expected) if expected is not None else None)
    try:
        root.__enter__()
    except OSError:
        return failure("PROJECT_UNAVAILABLE")
    except Refusal as error:
        return failure(error.code)
    diagnostics: list[dict[str, str]] = []
    notes: list[Note] = []
    ids: set[str] = set()
    parse_ms = 0.0
    scan_ms = 0.0

    def remember(memory_id: str | None) -> None:
        if memory_id is not None:
            if memory_id in ids:
                diagnostics.append(diagnostic("DUPLICATE_ID", memory_id))
            ids.add(memory_id)

    def consume(_name: str, data: bytes) -> None:
        nonlocal parse_ms
        started = time.monotonic()
        try:
            note = parse(data, request["project"])
        except SourceError as error:
            if error.code == "LIMIT_EXCEEDED":
                raise Refusal(error.code) from None
            remember(error.memory_id)
            diagnostics.append(diagnostic(error.code, error.memory_id, error.field))
        else:
            remember(note.metadata["id"])
            notes.append(note)
        finally:
            parse_ms += (time.monotonic() - started) * 1000

    try:
        if request["operation"] == "probe":
            return {"ok": True, "identity": root.state.identity, "final": root.final}
        with ExitStack() as handles:
            started = time.monotonic()
            try:
                Scanner(root, handles, emit, lambda code: diagnostics.append(
                    diagnostic(code))).run(consume)
            finally:
                scan_ms = (time.monotonic() - started) * 1000
        if diagnostics:
            codes = {item["code"] for item in diagnostics}
            code = next(code for code in (
                "FILE_UNAVAILABLE", "INVALID_METADATA", "DUPLICATE_ID") if code in codes)
            result = failure(code, codes == {"DUPLICATE_ID"}, diagnostics)
        elif request["operation"] == "list":
            eligible = [note for note in notes if note.eligible]
            markdown = render(request["project"], eligible)
            raw = markdown.encode("utf-8")
            result = {"ok": True, "project": request["project"],
                      "index_markdown": markdown, "index_version": version(raw),
                      "index_utf8_bytes": len(raw), "entry_count": len(eligible),
                      "excluded_count": len(notes) - len(eligible)}
        else:
            note = next((n for n in notes if n.metadata["id"] == request["memory_id"]), None)
            if note is None:
                result = failure("MEMORY_NOT_FOUND", True)
            elif not note.eligible:
                result = failure("MEMORY_INELIGIBLE", True)
            elif request.get("expected_version") not in (None, note.version):
                result = failure("MEMORY_CHANGED", True)
            else:
                result = {"ok": True, "project": request["project"],
                          "memory_id": note.metadata["id"], "metadata": note.metadata,
                          "body_markdown": note.body, "source_version": note.version,
                          "source_utf8_bytes": note.size}
    except (Refusal, SourceError) as error:
        result = failure(error.code, False, diagnostics + [diagnostic(error.code)])
    except OSError:
        result = failure("FILE_UNAVAILABLE", False,
                         diagnostics + [diagnostic("FILE_UNAVAILABLE")])
    finally:
        root.__exit__(None, None, None)
    return {"ok": True, "payload": result, "identity": root.state.identity, "final": root.final,
            "worker_metrics": {"scan_ms": round(scan_ms, 3), "parse_ms": round(parse_ms, 3)}}


def main() -> None:
    try:
        request = json.loads(sys.argv[1])
        started = time.monotonic()
        result = execute(request)
        result.setdefault("worker_metrics", {}).update(
            import_ms=round(IMPORT_MS, 3),
            work_ms=round((time.monotonic() - started) * 1000, 3))
    except Exception:
        # This process boundary must never print raw exception values or source data.
        print("Local storage worker failed unexpectedly.", file=sys.stderr)
        result = {"ok": False, "code": "INTERNAL_ERROR"}
    emit("result", **result)


if __name__ == "__main__":
    main()
