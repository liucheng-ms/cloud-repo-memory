"""Test-only worker modes; the lifecycle supervisor is the shared implementation."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import threading
import time

from cloud_repo_memory.supervisor import Supervisor as SharedSupervisor
from winfs import Refusal, Root, scan


def emit(kind, **fields):
    print(json.dumps({"kind": kind, "at": time.monotonic(), **fields}), flush=True)


class Supervisor(SharedSupervisor):
    def run(self, root, mode="scan"):
        return super().run(
            [sys.executable, "-B", str(Path(__file__).resolve()), "--worker", mode, root])


def worker(root, mode):
    if mode == "late-result":
        print(json.dumps({"kind": "file_start", "at": time.monotonic() - 3}), flush=True)
        emit("result", ok=True, files={"late.md": {"bytes": 1}})
        return
    if mode in ("stall-file", "stall-scan"):
        with Root(root) as pinned:
            if mode == "stall-file":
                emit("file_start")
                pinned.read("note.md", before_data=lambda: time.sleep(60))
            else:
                time.sleep(60)
        return
    try:
        data = scan(root, event=emit)
        emit("result", ok=True, files={
            name: {"bytes": len(value), "sha256": hashlib.sha256(value).hexdigest()}
            for name, value in data.items()
        })
    except Refusal as error:
        emit("result", ok=False, code=error.code)
    except OSError:
        emit("result", ok=False, code="FILE_UNAVAILABLE")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", choices=["scan", "stall-file", "stall-scan", "late-result"])
    parser.add_argument("root")
    arguments = parser.parse_args()
    if arguments.worker:
        worker(arguments.root, arguments.worker)
    else:
        print(json.dumps(Supervisor().run(arguments.root), indent=2))
