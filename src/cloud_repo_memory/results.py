"""Path-free local-v1 errors and observations."""

from datetime import datetime, timezone
import time
from typing import Any

from .metadata import FIELDS, SourceError, VERSION, identifier, validate_metadata, version
MESSAGES = {
    "INVALID_ARGUMENT": "Use valid project, memory ID and version arguments only.",
    "UNKNOWN_PROJECT": "The project is not configured.",
    "PROJECT_UNAVAILABLE": "The configured project root is not locally accessible.",
    "INVALID_METADATA": "Correct the note's UTF-8 frontmatter and required metadata.",
    "DUPLICATE_ID": "Reconcile duplicate memory IDs in this project.",
    "FILE_UNAVAILABLE": "A project entry could not be read or validated within its work budget.",
    "SCOPE_VIOLATION": "Remove unsupported links or correct the configured local layout.",
    "LIMIT_EXCEEDED": "Reduce the project to the documented resource limits.",
    "LOCAL_CHANGE_DETECTED": "The local project changed during observation; retry later.",
    "MEMORY_NOT_FOUND": "No memory with this ID exists in the configured project.",
    "MEMORY_INELIGIBLE": "The memory lifecycle does not permit serving it.",
    "MEMORY_CHANGED": "The memory version changed; relist before reading it.",
    "INTERNAL_ERROR": "The local storage operation failed; inspect local diagnostics.",
}
CLEANUP_MESSAGE = "Worker cleanup is pending; new filesystem jobs are blocked."


def diagnostic(code: str, memory_id: str | None = None,
               field: str | None = None) -> dict[str, str]:
    result = {"code": code, "message": MESSAGES[code]}
    if memory_id is not None:
        result["memory_id"] = memory_id
    if field is not None:
        result["field"] = field
    return result


def failure(code: str, complete: bool = False,
            diagnostics: list[dict[str, str]] | None = None) -> dict[str, Any]:
    ordered = sorted(diagnostics or [], key=lambda d: (
        d["code"], d.get("memory_id", ""), d.get("field", ""), d["message"]))
    return {"ok": False, "error": {
        "code": code, "message": MESSAGES[code], "diagnostics": ordered[:20],
        "diagnostics_omitted": max(0, len(ordered) - 20), "scan_complete": complete}}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def envelope(result: dict[str, Any], started_at: str, started: float) -> dict[str, Any]:
    return {"contract_version": "local-mvp-v1", **result, "observation": {
        "started_at": started_at, "finished_at": utc_now(),
        "elapsed_ms": max(0, (time.monotonic() - started) * 1000),
        "consistency": "local-best-effort", "cloud_freshness": "unknown"}}


def valid_payload(result: object, operation: str, arguments: dict[str, Any]) -> bool:
    """Validate the private worker boundary before publishing any of its payload."""
    if not isinstance(result, dict) or type(result.get("ok")) is not bool:
        return False
    if not result["ok"]:
        error = result.get("error")
        if (set(result) != {"ok", "error"} or not isinstance(error, dict)
                or set(error) != {"code", "message", "diagnostics",
                                  "diagnostics_omitted", "scan_complete"}
                or error.get("code") not in MESSAGES
                or error["message"] != MESSAGES[error["code"]]
                or type(error["scan_complete"]) is not bool
                or type(error["diagnostics_omitted"]) is not int
                or error["diagnostics_omitted"] < 0
                or not isinstance(error["diagnostics"], list)
                or len(error["diagnostics"]) > 20):
            return False
        for item in error["diagnostics"]:
            if (not isinstance(item, dict) or not {"code", "message"} <= set(item)
                    or set(item) - {"code", "message", "memory_id", "field"}
                    or item.get("code") not in MESSAGES
                    or item["message"] != MESSAGES[item["code"]]
                    or "memory_id" in item and not identifier(item["memory_id"])
                    or "field" in item and item["field"] not in FIELDS):
                return False
        return True
    if result.get("project") != arguments["project"]:
        return False
    if operation == "list":
        if set(result) != {"ok", "project", "index_markdown", "index_version",
                           "index_utf8_bytes", "entry_count", "excluded_count"}:
            return False
        markdown = result["index_markdown"]
        if (not isinstance(markdown, str)
                or not markdown.startswith(f"# Memory index: {arguments['project']}\n\n")
                or not markdown.endswith("\n")
                or any(type(result[field]) is not int or result[field] < 0
                       for field in ("index_utf8_bytes", "entry_count", "excluded_count"))
                or result["entry_count"] + result["excluded_count"] > 200):
            return False
        raw = markdown.encode("utf-8")
        return (0 < len(raw) <= 131072 and result["index_utf8_bytes"] == len(raw)
                and result["index_version"] == version(raw))
    if set(result) != {"ok", "project", "memory_id", "metadata", "body_markdown",
                       "source_version", "source_utf8_bytes"}:
        return False
    try:
        metadata = validate_metadata(result["metadata"], arguments["project"])
    except SourceError:
        return False
    return (metadata["id"] == result["memory_id"] == arguments["memory_id"]
            and metadata["status"] == "active" and metadata["approval"] == "approved"
            and isinstance(result["source_version"], str)
            and VERSION.fullmatch(result["source_version"]) is not None
            and arguments.get("expected_version") in (None, result["source_version"])
            and type(result["source_utf8_bytes"]) is int
            and 0 < result["source_utf8_bytes"] <= 262144
            and isinstance(result["body_markdown"], str)
            and len(result["body_markdown"].encode("utf-8")) < result["source_utf8_bytes"])
