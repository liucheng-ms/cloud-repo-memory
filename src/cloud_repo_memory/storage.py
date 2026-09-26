"""Public callable local-v1 storage core, independent of MCP transport."""

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import sys
import time
from typing import Any

from .metadata import VERSION, identifier
from .results import CLEANUP_MESSAGE, diagnostic, envelope, failure, utc_now, valid_payload
from .supervisor import Supervisor

_SUPERVISOR = Supervisor()


class ConfigurationError(ValueError):
    """Configuration was rejected atomically; no partial mapping is published."""


@dataclass
class Project:
    root: str
    identity: tuple[int, int, int] | None
    final: str | None


def _overlap(left: str, right: str) -> bool:
    left, right = left.rstrip("\\").casefold(), right.rstrip("\\").casefold()
    return left == right or left.startswith(right + "\\") or right.startswith(left + "\\")


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ConfigurationError("Invalid local storage configuration.")
        result[key] = value
    return result


def _job(request: dict[str, Any]) -> dict[str, Any]:
    try:
        return _SUPERVISOR.run([sys.executable, "-B", "-m", "cloud_repo_memory.worker",
                                json.dumps(request, ensure_ascii=True)])
    except (OSError, RuntimeError, MemoryError, ValueError):
        print("Local storage worker setup or protocol failed.", file=sys.stderr)
        return {"ok": False, "code": "INTERNAL_ERROR",
                "supervisor_state": "cleanup-pending" if _SUPERVISOR.pending else "unavailable"}


class MemoryStore:
    """Explicit project mappings; all instances share serialized worker ownership."""

    def __init__(self, configuration: object):
        try:
            self._projects = self._configure(configuration)
        except (ConfigurationError, OSError, ValueError, TypeError):
            print("Invalid local storage configuration; startup refused.", file=sys.stderr)
            raise ConfigurationError("Invalid local storage configuration.") from None

    @classmethod
    def from_json(cls, path: str | os.PathLike[str]) -> "MemoryStore":
        try:
            with open(path, "rb") as stream:
                raw = stream.read(262145)
            if len(raw) > 262144:
                raise ConfigurationError("Invalid local storage configuration.")
            value = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs)
            location = str(Path(path).absolute())
            if isinstance(value, dict) and isinstance(value.get("projects"), list):
                for mapping in value["projects"]:
                    if isinstance(mapping, dict) and isinstance(mapping.get("root"), str):
                        if _overlap(location, mapping["root"]):
                            raise ConfigurationError("Configuration must be outside knowledge roots.")
        except (OSError, ValueError, UnicodeError):
            print("Invalid local storage configuration; startup refused.", file=sys.stderr)
            raise ConfigurationError("Invalid local storage configuration.") from None
        return cls(value)

    @staticmethod
    def _configure(configuration: object) -> dict[str, Project]:
        if os.name != "nt":
            raise ConfigurationError("Windows fixed NTFS is required.")
        if (not isinstance(configuration, dict)
                or set(configuration) != {"schema_version", "projects"}
                or type(configuration["schema_version"]) is not int
                or configuration["schema_version"] != 1
                or not isinstance(configuration["projects"], list)
                or not 1 <= len(configuration["projects"]) <= 32):
            raise ConfigurationError("Invalid configuration.")
        mappings: dict[str, Project] = {}
        # Validate the complete lexical mapping before any filesystem access.
        for entry in configuration["projects"]:
            if (not isinstance(entry, dict) or set(entry) != {"project", "root"}
                    or not identifier(entry.get("project"))
                    or not isinstance(entry.get("root"), str)):
                raise ConfigurationError("Invalid mapping.")
            key, root = entry["project"], entry["root"]
            if (not 3 <= len(root) <= 4096 or not re.match(r"^[A-Za-z]:\\", root)
                    or "/" in root or "%" in root or "$" in root):
                raise ConfigurationError("Invalid root.")
            parts = root[3:].split("\\") if len(root) > 3 else []
            if any(not part or part in (".", "..") or part[-1] in " ."
                   or any(char in part for char in '\\/:*?"<>|')
                   or any(ord(char) < 32 for char in part) for part in parts):
                raise ConfigurationError("Invalid root.")
            if key in mappings or any(_overlap(root, old.root) for old in mappings.values()):
                raise ConfigurationError("Overlapping mappings.")
            mappings[key] = Project(root, None, None)
        with _SUPERVISOR.lock:
            for key, mapping in mappings.items():
                answer = _job({"operation": "probe", "root": mapping.root, "project": key})
                if answer.get("ok") and "identity" in answer and "final" in answer:
                    mapping.identity = tuple(answer["identity"])
                    mapping.final = answer["final"]
                elif answer.get("error", {}).get("code") != "PROJECT_UNAVAILABLE":
                    raise ConfigurationError("Root validation failed.")
            values = list(mappings.values())
            for index, left in enumerate(values):
                for right in values[index + 1:]:
                    if (left.identity is not None and left.identity == right.identity
                            or left.final and right.final and _overlap(left.final, right.final)):
                        raise ConfigurationError("Overlapping filesystem identities.")
        return mappings

    def list_memory_index(self, project: str | None = None, **extra: object) -> dict[str, Any]:
        return self._call("list", {"project": project, **extra})

    def get_memory(self, project: str | None = None, memory_id: str | None = None,
                   expected_version: str | None = None, **extra: object) -> dict[str, Any]:
        arguments: dict[str, Any] = {"project": project, "memory_id": memory_id, **extra}
        if expected_version is not None:
            arguments["expected_version"] = expected_version
        return self._call("get", arguments)

    def _call(self, operation: str, arguments: dict[str, Any]) -> dict[str, Any]:
        started_at, started = utc_now(), time.monotonic()
        allowed = {"project"} if operation == "list" else {
            "project", "memory_id", "expected_version"}
        valid = (not set(arguments) - allowed and identifier(arguments.get("project"))
                 and (operation == "list" or identifier(arguments.get("memory_id")))
                 and ("expected_version" not in arguments or (
                     isinstance(arguments["expected_version"], str)
                     and VERSION.fullmatch(arguments["expected_version"]) is not None)))
        if not valid:
            result = failure("INVALID_ARGUMENT")
        elif arguments["project"] not in self._projects:
            result = failure("UNKNOWN_PROJECT")
        else:
            with _SUPERVISOR.lock:
                mapping = self._projects[arguments["project"]]
                answer = _job({"operation": operation, "root": mapping.root,
                               "identity": mapping.identity, **arguments})
                if answer.get("ok") and self._valid_worker_result(answer, operation, arguments):
                    identity, final = tuple(answer["identity"]), answer["final"]
                    if any(other is not mapping and (
                            other.identity == identity
                            or other.final and _overlap(other.final, final))
                           for other in self._projects.values()):
                        result = failure("SCOPE_VIOLATION")
                    else:
                        if mapping.identity is None:
                            mapping.identity = identity
                            mapping.final = final
                        result = answer["payload"]
                elif "error" in answer and self._valid_worker_result(
                        {"payload": {"ok": False, "error": answer["error"]}},
                        operation, arguments, root_required=False):
                    result = {"ok": False, "error": answer["error"]}
                else:
                    code = answer.get("code", "INTERNAL_ERROR")
                    if code not in ("FILE_UNAVAILABLE", "LIMIT_EXCEEDED", "INTERNAL_ERROR"):
                        code = "INTERNAL_ERROR"
                    item = diagnostic(code)
                    if answer.get("supervisor_state") == "cleanup-pending":
                        item["message"] = CLEANUP_MESSAGE
                    result = failure(code, False, [item])
        return envelope(result, started_at, started)

    @staticmethod
    def _valid_worker_result(answer: dict[str, Any], operation: str,
                             arguments: dict[str, Any], root_required: bool = True) -> bool:
        try:
            if root_required and (
                    not isinstance(answer.get("identity"), (list, tuple))
                    or len(answer["identity"]) != 3
                    or any(type(part) is not int or part < 0 for part in answer["identity"])
                    or not isinstance(answer.get("final"), str)
                    or not answer["final"].startswith("\\\\?\\Volume{")):
                return False
            return valid_payload(answer.get("payload"), operation, arguments)
        except (KeyError, TypeError, ValueError, UnicodeError):
            return False
