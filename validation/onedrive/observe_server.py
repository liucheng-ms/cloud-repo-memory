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

        def record(event, **fields):
            stream.write(json.dumps({"at": utc_now(), "event": event, **fields}) + "\n")
            stream.flush()

        def launch(command, **kwargs):
            process = original_launch(command, **kwargs)
            processes.append(process)
            record("worker-launched", pid=process.pid)
            return process

        def run(command):
            result = original_run(command)
            record("job-finished", operation=json.loads(command[-1])["operation"],
                   cleanup_confirmed=result.get("cleanup_confirmed"),
                   pending=supervisor.pending is not None,
                   workers=[{"pid": p.pid, "returncode": p.returncode} for p in processes],
                   decision_ms=result.get("decision_ms"), elapsed_ms=result.get("elapsed_ms"))
            return result

        subprocess.Popen, supervisor._run = launch, run
        sys.argv = ["cloud-repo-memory", "--config", config]
        try:
            code = server.main()
            record("shutdown", code=code, pending=supervisor.pending is not None)
            return code
        finally:
            subprocess.Popen, supervisor._run = original_launch, original_run


if __name__ == "__main__":
    raise SystemExit(main())
