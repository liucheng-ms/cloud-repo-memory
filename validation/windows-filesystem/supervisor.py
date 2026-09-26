"""Disposable-worker deadline experiment. No real-time or driver guarantees."""

import argparse
import hashlib
import json
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path

from winfs import Refusal, Root, scan

FILE_SECONDS = 2.0
SCAN_SECONDS = 5.0
CLEANUP_SECONDS = 0.5


def emit(kind, **fields):
    print(json.dumps({"kind": kind, "at": time.monotonic(), **fields}), flush=True)


def worker(root, mode):
    if mode == "late-result":
        # Synthetic delayed delivery: the operation start predates its budget.
        print(json.dumps({"kind": "file_start", "at": time.monotonic() - 3}), flush=True)
        emit("result", ok=True, files={"late.md": {"bytes": 1}})
        return
    if mode in ("stall-file", "stall-scan"):
        with Root(root) as pinned:
            if mode == "stall-file":
                emit("file_start")
                # Keep a real fixture handle open while synthetically stalled.
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
    except OSError as error:
        emit("result", ok=False, code="FILE_UNAVAILABLE", winerror=error.winerror)


class Supervisor:
    """One worker at a time; retain and fault on unconfirmed cleanup."""

    def __init__(self):
        self.pending = None

    def reap(self, reader_wait=0):
        if self.pending is None:
            return True
        process, reader = self.pending
        if process.poll() is None:
            return False
        if reader is not None and reader.ident is not None:
            reader.join(reader_wait)
            if reader.is_alive():
                return False
        process.stdout.close()
        self.pending = None
        return True

    def run(self, root, mode="scan"):
        if not self.reap():
            return {"ok": False, "code": "INTERNAL_ERROR", "cleanup_confirmed": False,
                    "supervisor_state": "cleanup-pending"}
        started = time.monotonic()
        messages = queue.Queue()
        scan_end, file_end = started + SCAN_SECONDS, None
        answer = None

        def receive():
            try:
                for line in process.stdout:
                    messages.put(json.loads(line))
            except (ValueError, OSError) as error:
                messages.put({"kind": "protocol_error", "detail": type(error).__name__})
            finally:
                messages.put({"kind": "eof"})

        process = subprocess.Popen(
            [sys.executable, "-B", str(Path(__file__).resolve()), "--worker", mode, root],
            stdout=subprocess.PIPE, text=True, encoding="utf-8",
            stdin=subprocess.DEVNULL,
        )
        self.pending = process, None
        try:
            try:
                reader = threading.Thread(target=receive, daemon=True)
                self.pending = process, reader
                reader.start()
            except (RuntimeError, MemoryError, OSError):
                answer = {"ok": False, "code": "INTERNAL_ERROR",
                          "supervisor_state": "reader-unavailable"}
            while answer is None:
                now = time.monotonic()
                deadline = min(scan_end, file_end if file_end is not None else scan_end)
                if now >= deadline:
                    answer = {"ok": False, "code": (
                        "FILE_UNAVAILABLE" if file_end is not None and file_end <= scan_end
                        else "LIMIT_EXCEEDED")}
                    break
                try:
                    message = messages.get(timeout=deadline - now)
                except queue.Empty:
                    continue
                # Never accept a queued success after a deadline.
                if time.monotonic() >= deadline:
                    continue
                kind = message["kind"]
                if kind == "file_start":
                    file_end = message["at"] + FILE_SECONDS
                elif kind == "file_end":
                    if file_end is not None and message["at"] > file_end:
                        answer = {"ok": False, "code": "FILE_UNAVAILABLE"}
                    file_end = None
                elif kind == "result":
                    answer = {key: value for key, value in message.items()
                              if key not in ("kind", "at")}
                else:
                    answer = {"ok": False, "code": "INTERNAL_ERROR"}
        finally:
            decision_ms = (time.monotonic() - started) * 1000
            cleanup_end = time.monotonic() + CLEANUP_SECONDS
            if process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=max(0, cleanup_end - time.monotonic()))
            except subprocess.TimeoutExpired:
                # Keep the process/pipe/thread owned; refuse subsequent work.
                pass
            cleanup = self.reap(max(0, cleanup_end - time.monotonic()))
        answer.update(decision_ms=round(decision_ms, 2),
                      elapsed_ms=round((time.monotonic() - started) * 1000, 2),
                      cleanup_confirmed=cleanup)
        if not cleanup:
            answer = {**answer, "ok": False, "code": "INTERNAL_ERROR",
                      "supervisor_state": "cleanup-pending"}
            answer.pop("files", None)
        return answer


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", choices=["scan", "stall-file", "stall-scan", "late-result"])
    parser.add_argument("root")
    arguments = parser.parse_args()
    if arguments.worker:
        worker(arguments.root, arguments.worker)
    else:
        print(json.dumps(Supervisor().run(arguments.root), indent=2))
