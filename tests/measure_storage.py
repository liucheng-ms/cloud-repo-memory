"""Repeatable synthetic measurements; no MCP, agent scoring, tokenizer or cloud I/O."""

import argparse
import ctypes
from importlib.metadata import version as package_version
import json
import platform
import time
from unittest.mock import patch

from cloud_repo_memory import storage
from cloud_repo_memory.metadata import version
from cloud_repo_memory.storage import MemoryStore
from support import REPO, Fixture, adapt_kusto, config, source
from test_storage import check


def measure(count):
    fixture = Fixture()
    try:
        root = fixture.directory("project")
        if count == 5:
            bodies = adapt_kusto(fixture, root)
        else:
            bodies = {}
            total = 1048576 if count == 100 else 2097152
            quotient, remainder = divmod(total, count)
            for index in range(count):
                raw = source(f"note-{index:03}", title="T" * 60, summary="S" * 120,
                             read_when="R" * 120, body="")
                size = quotient + int(index < remainder)
                fixture.file(root / f"note-{index:03}.md", raw + b"x" * (size - len(raw)))
        files = sorted(root.iterdir())
        corpus_bytes = sum(path.stat().st_size for path in files)
        corpus_hash = version(b"".join(path.read_bytes() for path in files))
        before = time.monotonic()
        store = MemoryStore(config(("sample-telemetry", root)))
        configuration_ms = (time.monotonic() - before) * 1000
        samples = []
        job = storage._job
        last_internal = {}

        def observe(request):
            nonlocal last_internal
            last_internal = job(request)
            return last_internal

        for _ in range(31):
            before = time.monotonic()
            with patch.object(storage, "_job", observe):
                result = store.list_memory_index("sample-telemetry")
            round_trip = (time.monotonic() - before) * 1000
            check(result)
            assert result["entry_count"] == count
            samples.append({"core_elapsed_ms": round(result["observation"]["elapsed_ms"], 3),
                            "call_round_trip_ms": round(round_trip, 3),
                            "private_worker_metrics": last_internal.get("worker_metrics")})
        p95 = sorted(sample["core_elapsed_ms"] for sample in samples[1:])[28]
        output = {"notes": count, "source_bytes": corpus_bytes,
                  "corpus_source_hash_in_filename_order": corpus_hash,
                  "configuration_ms": round(configuration_ms, 3),
                  "index_utf8_bytes": result["index_utf8_bytes"],
                  "index_version": result["index_version"], "samples": samples,
                  "first_core_elapsed_ms": samples[0]["core_elapsed_ms"],
                  "subsequent_core_p95_ms": p95,
                  "subsequent_call_p95_ms": sorted(
                      sample["call_round_trip_ms"] for sample in samples[1:])[28]}
        if count == 5:
            cases = json.loads((REPO / "validation" / "samples" / "kusto-memory"
                                / "evaluation-cases.json").read_text("utf-8"))["cases"]
            coverage = []
            for case in cases:
                index = check(store.list_memory_index("sample-telemetry"))
                read_ids = []
                for memory_id in case["required_memory_ids"]:
                    _, note = bodies[memory_id]
                    assert f"**{memory_id}**" in index["index_markdown"]
                    body = check(store.get_memory("sample-telemetry", memory_id, note.version), "get")
                    assert body["body_markdown"] == note.body
                    read_ids.append(memory_id)
                coverage.append({"case": case["id"], "scripted_required_ids_read": read_ids})
            output["scripted_storage_coverage_not_agent_retrieval"] = coverage
            output["index_byte_target_pass"] = result["index_utf8_bytes"] <= 2048
        elif count == 100:
            output.update(index_byte_target_pass=result["index_utf8_bytes"] <= 49152,
                          first_scan_target_pass=samples[0]["core_elapsed_ms"] <= 1000,
                          subsequent_p95_target_pass=p95 <= 500)
        else:
            fixture.file(root / "overflow.md", source("overflow"))
            overflow = check(store.list_memory_index("sample-telemetry"), code="LIMIT_EXCEEDED")
            output["over_ceiling"] = {"notes": 201, "code": overflow["error"]["code"],
                                     "scan_complete": overflow["error"]["scan_complete"]}
        return output
    finally:
        fixture.clean()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    output = {"synthetic_only": True, "evaluator_only": True, "os": platform.platform(),
              "python": platform.python_version(), "machine": platform.machine(),
              "server_version": package_version("cloud-repo-memory"),
              "server_source_hash_in_sorted_module_order": version(b"".join(
                  path.read_bytes() for path in sorted(
                      (REPO / "src" / "cloud_repo_memory").glob("*.py")))),
              "pointer_bits": ctypes.sizeof(ctypes.c_void_p) * 8,
              "filesystem": "local fixed NTFS (verified by every root open)",
              "dependencies": {name: package_version(name) for name in (
                  "ruamel.yaml", "pytest", "jsonschema")},
              "tokenizer": None, "tokens": None, "mcp_client_round_trip": None,
              "agent_retrieval": "BLOCKED", "onedrive_pilot": "BLOCKED",
              "method": "First index after configuration plus 30 subsequent fresh workers; "
                        "nearest-rank p95 (rank 29 of 30). Not a cold OS-cache claim.",
              "corpora": [measure(count) for count in (5, 100, 200)]}
    with open(args.output, "w", encoding="utf-8", newline="\n") as stream:
        json.dump(output, stream, indent=2)
        stream.write("\n")
    print(json.dumps([{key: corpus[key] for key in (
        "notes", "source_bytes", "index_utf8_bytes", "first_core_elapsed_ms",
        "subsequent_core_p95_ms")} for corpus in output["corpora"]], indent=2))


if __name__ == "__main__":
    main()
