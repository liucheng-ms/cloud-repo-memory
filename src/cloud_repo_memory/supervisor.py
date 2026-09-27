"""Serialized disposable workers with retained ownership until confirmed cleanup."""

import json
import math
import queue
import subprocess
import threading
import time
from collections.abc import Sequence
from typing import Any

FILE_SECONDS = 2.0
SCAN_SECONDS = 5.0
CLEANUP_SECONDS = 0.5
MAX_MESSAGE = 2_000_000


class Supervisor:
    def __init__(self) -> None:
        self.pending: tuple[subprocess.Popen[str], threading.Thread | None] | None = None
        self.lock = threading.RLock()

    def reap(self, reader_wait: float = 0) -> bool:
        with self.lock:
            if self.pending is None:
                return True
            process, reader = self.pending
            try:
                if process.poll() is None:
                    return False
                if reader is not None and reader.ident is not None:
                    reader.join(reader_wait)
                    if reader.is_alive():
                        return False
                if process.stdout is not None:
                    process.stdout.close()
                # Popen otherwise retains its Windows process handle until GC.
                handle = getattr(process, "_handle", None)
                if handle is not None:
                    handle.Close()
            except (OSError, RuntimeError, ValueError):
                return False
            self.pending = None
            return True

    def run(self, command: Sequence[str]) -> dict[str, Any]:
        with self.lock:
            return self._run(command)

    def _run(self, command: Sequence[str]) -> dict[str, Any]:
        if not self.reap():
            return {"ok": False, "code": "INTERNAL_ERROR", "cleanup_confirmed": False,
                    "supervisor_state": "cleanup-pending"}
        started = time.monotonic()
        messages: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=128)
        reader_failed = threading.Event()
        scan_end, file_end = started + SCAN_SECONDS, None
        answer = None

        def receive() -> None:
            try:
                if process.stdout is None:
                    raise ValueError("Missing worker pipe")
                while True:
                    line = process.stdout.readline(MAX_MESSAGE + 1)
                    if not line:
                        messages.put({"kind": "eof"}, timeout=0.05)
                        return
                    if len(line) > MAX_MESSAGE or not line.endswith("\n"):
                        raise ValueError("Invalid worker frame")
                    message = json.loads(line)
                    if not isinstance(message, dict):
                        raise ValueError("Invalid worker message")
                    messages.put(message, timeout=0.05)
            except (ValueError, OSError, RuntimeError, MemoryError, queue.Full):
                reader_failed.set()

        try:
            process = subprocess.Popen(
                command, stdout=subprocess.PIPE, text=True, encoding="utf-8",
                stdin=subprocess.DEVNULL,
            )
        except (OSError, ValueError, RuntimeError, MemoryError):
            return {"ok": False, "code": "INTERNAL_ERROR", "cleanup_confirmed": True,
                    "supervisor_state": "spawn-unavailable"}
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
                if reader_failed.is_set():
                    answer = {"ok": False, "code": "INTERNAL_ERROR"}
                    break
                try:
                    message = messages.get(timeout=min(0.05, deadline - now))
                except queue.Empty:
                    continue
                if time.monotonic() >= deadline:
                    continue
                kind, at = message.get("kind"), message.get("at")
                if (kind not in ("file_start", "file_end", "result")
                        or type(at) not in (float, int) or not math.isfinite(at)
                        or at > time.monotonic()):
                    answer = {"ok": False, "code": "INTERNAL_ERROR"}
                elif kind == "file_start":
                    if file_end is not None:
                        answer = {"ok": False, "code": "INTERNAL_ERROR"}
                    else:
                        file_end = at + FILE_SECONDS
                elif kind == "file_end":
                    if file_end is None:
                        answer = {"ok": False, "code": "INTERNAL_ERROR"}
                    elif at > file_end:
                        answer = {"ok": False, "code": "FILE_UNAVAILABLE"}
                    file_end = None
                elif file_end is not None or type(message.get("ok")) is not bool:
                    answer = {"ok": False, "code": "INTERNAL_ERROR"}
                else:
                    answer = {key: value for key, value in message.items()
                              if key not in ("kind", "at")}
        finally:
            decision_ms = (time.monotonic() - started) * 1000
            cleanup_end = time.monotonic() + CLEANUP_SECONDS
            cleanup_failed = False
            try:
                if process.poll() is None:
                    process.terminate()
                process.wait(timeout=max(0, cleanup_end - time.monotonic()))
            except subprocess.TimeoutExpired:
                pass
            except (OSError, RuntimeError, ValueError):
                cleanup_failed = True
            cleanup = self.reap(max(0, cleanup_end - time.monotonic()))
        if not cleanup:
            return {"ok": False, "code": "INTERNAL_ERROR", "cleanup_confirmed": False,
                    "supervisor_state": "cleanup-pending"}
        if cleanup_failed or reader_failed.is_set():
            answer = {"ok": False, "code": "INTERNAL_ERROR"}
        if answer is None:
            answer = {"ok": False, "code": "INTERNAL_ERROR"}
        answer.update(decision_ms=round(decision_ms, 2),
                      elapsed_ms=round((time.monotonic() - started) * 1000, 2),
                      cleanup_confirmed=True)
        return answer
