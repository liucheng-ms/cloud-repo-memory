"""Test-only subprocess fault injection; never included in the installed package."""

import json
from pathlib import Path
import subprocess
import sys
import time

from cloud_repo_memory import server, storage
from mcp import types

config_path, ledger_path, mode = sys.argv[1:]
ledger = Path(ledger_path)


def record(event, **fields):
    with ledger.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({"event": event, **fields}) + "\n")


supervisor = storage._SUPERVISOR
original_run, original_reap = supervisor._run, supervisor.reap
original_popen, original_create = subprocess.Popen, server.create_server
slow_pid = None
hold_until = None
first = True


def launch(command, **kwargs):
    global slow_pid, first
    request = json.loads(command[-1])
    if request["operation"] == "list" and first:
        first = False
        # The real runtime worker still parses/scans; only its startup is delayed.
        script = (
            "import runpy,sys,time; time.sleep(1.0); "
            "sys.argv=['cloud_repo_memory.worker',sys.argv[1]]; "
            "runpy.run_module('cloud_repo_memory.worker',run_name='__main__')"
        )
        command = [sys.executable, "-B", "-c", script, command[-1]]
        process = original_popen(command, **kwargs)
        slow_pid = process.pid
    else:
        process = original_popen(command, **kwargs)
    record("launch", operation=request["operation"], pid=process.pid)
    return process


def reap(reader_wait=0):
    global hold_until
    if mode == "cleanup" and supervisor.pending is not None:
        process, reader = supervisor.pending
        if process.pid == slow_pid and process.poll() is not None:
            if hold_until is None:
                hold_until = time.monotonic() + 1.2
                record("cleanup-withheld", pid=process.pid)
            if time.monotonic() < hold_until:
                return False
    return original_reap(reader_wait)


def run(command):
    operation = json.loads(command[-1])["operation"]
    result = original_run(command)
    record("job-finished", operation=operation, pending=supervisor.pending is not None,
           cleanup=result.get("cleanup_confirmed"))
    return result


def create(store):
    app = original_create(store)
    handle = app.request_handlers[types.CallToolRequest]

    async def call(request):
        record("request", name=request.params.name)
        return await handle(request)

    app.request_handlers[types.CallToolRequest] = call
    return app


subprocess.Popen = launch
supervisor._run, supervisor.reap = run, reap
server.create_server = create
sys.argv = ["cloud-repo-memory", "--config", config_path]
code = server.main()
record("shutdown", pending=supervisor.pending is not None, code=code)
raise SystemExit(code)
