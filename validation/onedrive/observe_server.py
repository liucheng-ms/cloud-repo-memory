"""Validation-only passive lifecycle observer around the unmodified stdio server."""

import json
from pathlib import Path
import subprocess
import sys

from cloud_repo_memory import server, storage
from cloud_repo_memory.results import utc_now


def main():
    config, output = sys.argv[1:]
    ledger = Path(output)
    with ledger.open("x", encoding="utf-8") as stream:
        supervisor = storage._SUPERVISOR
        original_run, original_launch = supervisor._run, subprocess.Popen
        processes = []
        evidence_failed = False

        def record(event, *, at=None, **fields):
            nonlocal evidence_failed
            try:
                stream.write(json.dumps({"at": at or utc_now(), "event": event, **fields}) + "\n")
                stream.flush()
            except (OSError, ValueError):
                evidence_failed = True
                raise

        def launch(command, **kwargs):
            # Allocate the record before spawning; never do evidence I/O before
            # returning the live process to the supervisor's ownership handoff.
            entry = {"at": utc_now(), "process": None}
            processes.append(entry)
            entry["process"] = original_launch(command, **kwargs)
            return entry["process"]

        def run(command):
            first = len(processes)
            result = original_run(command)
            finished_at = utc_now()
            for entry in processes[first:]:
                if entry["process"] is not None:
                    record("worker-launched", at=entry["at"], pid=entry["process"].pid)
            record("job-finished", at=finished_at, operation=json.loads(command[-1])["operation"],
                   cleanup_confirmed=result.get("cleanup_confirmed"),
                   pending=supervisor.pending is not None,
                   workers=[{"pid": entry["process"].pid,
                             "returncode": entry["process"].returncode}
                            for entry in processes if entry["process"] is not None],
                   decision_ms=result.get("decision_ms"), elapsed_ms=result.get("elapsed_ms"))
            return result

        subprocess.Popen, supervisor._run = launch, run
        sys.argv = ["cloud-repo-memory", "--config", config]
        try:
            code = server.main()
            if evidence_failed:
                raise RuntimeError("Pilot observer evidence failed; results are incomplete.")
            record("shutdown", code=code, pending=supervisor.pending is not None)
            return code
        finally:
            subprocess.Popen, supervisor._run = original_launch, original_run


if __name__ == "__main__":
    raise SystemExit(main())
