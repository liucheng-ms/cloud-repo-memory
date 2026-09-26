import json
import subprocess
import sys
import threading
import time
from unittest.mock import Mock, patch

import pytest

from cloud_repo_memory import storage
from cloud_repo_memory.results import CLEANUP_MESSAGE
from cloud_repo_memory.supervisor import Supervisor
from cloud_repo_memory.storage import MemoryStore
from support import config
from test_storage import check


def test_spawn_failure_is_explicit():
    supervisor = Supervisor()
    with patch("cloud_repo_memory.supervisor.subprocess.Popen", side_effect=OSError("private path")):
        result = supervisor.run(["unused"])
    assert result["code"] == "INTERNAL_ERROR"
    assert result["cleanup_confirmed"]
    assert supervisor.pending is None
    assert "private" not in json.dumps(result)


@pytest.mark.parametrize("frame", [
    "not JSON", "[]", "{}", '{"kind":"file_end","at":0}',
    '{"kind":"file_start","at":"bad"}',
    '{"kind":"file_start","at":NaN}', '{"kind":"file_start","at":Infinity}',
    '{"kind":"result","at":0,"ok":"true"}',
])
def test_invalid_protocol_never_succeeds(frame):
    result = Supervisor().run([sys.executable, "-c", f"print({frame!r}, flush=True)"])
    assert result["code"] == "INTERNAL_ERROR"
    assert result["cleanup_confirmed"]


def test_oversized_protocol_and_abnormal_exit():
    for script in ("print('x' * 2000001)", "raise SystemExit(7)"):
        result = Supervisor().run([sys.executable, "-c", script])
        assert result["code"] == "INTERNAL_ERROR"
        assert result["cleanup_confirmed"]


@pytest.mark.parametrize("failure", ["terminate", "wait", "close"])
def test_termination_wait_and_pipe_failure_retain_original(failure):
    supervisor = Supervisor()
    process = Mock()
    process.poll.return_value = None
    process.wait.side_effect = subprocess.TimeoutExpired("private", 0.5)
    if failure == "terminate":
        process.terminate.side_effect = OSError("private")
    elif failure == "wait":
        process.wait.side_effect = OSError("private")
    else:
        process.poll.return_value = 0
        process.stdout.close.side_effect = OSError("private")
    with patch("cloud_repo_memory.supervisor.subprocess.Popen", return_value=process) as launch, patch(
            "cloud_repo_memory.supervisor.threading.Thread", side_effect=RuntimeError("private")):
        first = supervisor.run(["unused"])
        assert first["supervisor_state"] == "cleanup-pending"
        assert supervisor.pending[0] is process
        for _ in range(100):
            assert not supervisor.run(["unused"])["cleanup_confirmed"]
        launch.assert_called_once()
        process.poll.return_value = 1
        process.stdout.close.side_effect = None
        assert supervisor.reap()
        assert supervisor.pending is None


def test_reader_retained_until_finished():
    supervisor = Supervisor()
    process, reader = Mock(), Mock()
    process.poll.return_value = 1
    reader.ident = 1
    reader.is_alive.return_value = True
    supervisor.pending = process, reader
    assert not supervisor.reap()
    process.stdout.close.assert_not_called()
    reader.is_alive.return_value = False
    assert supervisor.reap()


def test_public_reaper_retains_exact_worker_until_release():
    supervisor = Supervisor()
    process = Mock()
    process.poll.return_value = None
    supervisor.pending = process, None
    with patch.object(storage, "_SUPERVISOR", supervisor):
        assert MemoryStore.reap_workers() is False
        assert supervisor.pending == (process, None)
        process.stdout.close.assert_not_called()
        process.poll.return_value = 0
        assert MemoryStore.reap_workers() is True
        assert supervisor.pending is None
        process.stdout.close.assert_called_once()
        process._handle.Close.assert_called_once()


def test_shared_supervisor_serializes_jobs():
    supervisor = Supervisor()
    active = 0
    maximum = 0

    def work(_command):
        nonlocal active, maximum
        active += 1
        maximum = max(maximum, active)
        time.sleep(0.01)
        active -= 1
        return {"ok": True}

    with patch.object(supervisor, "_run", side_effect=work):
        threads = [threading.Thread(target=supervisor.run, args=(["unused"],)) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=2)
            assert not thread.is_alive()
    assert maximum == 1


@pytest.mark.parametrize("answer", [
    {"ok": False, "code": "INTERNAL_ERROR", "cleanup_confirmed": False,
     "supervisor_state": "cleanup-pending", "path": "secret"},
    {"ok": True, "payload": {"ok": True, "body_markdown": "secret"}},
    {"ok": True, "payload": {"ok": False, "error": {"code": "private"}}},
    {"ok": False, "error": {"code": "INVALID_METADATA", "message": "secret"}},
    {"ok": False, "code": "unknown-private-code", "files": {"secret": "body"}},
])
def test_public_protocol_and_cleanup_sanitization(fixture, answer):
    root = fixture.directory("project")
    store = MemoryStore(config(("p", root)))
    with patch.object(storage, "_job", return_value=answer):
        result = check(store.list_memory_index("p"), code="INTERNAL_ERROR")
        assert "secret" not in json.dumps(result)
        if answer.get("supervisor_state") == "cleanup-pending":
            assert result["error"]["diagnostics"][0]["message"] == CLEANUP_MESSAGE


def test_worker_protocol_partial_success_rejected(fixture):
    root = fixture.directory("project")
    store = MemoryStore(config(("p", root)))
    with storage._SUPERVISOR.lock:
        answer = storage._job({"operation": "list", "project": "p", "root": str(root)})
    answer["payload"]["body_markdown"] = "private"
    with patch.object(storage, "_job", return_value=answer):
        check(store.list_memory_index("p"), code="INTERNAL_ERROR")


def test_non_windows_configuration_is_explicit(fixture):
    root = fixture.directory("project")
    with patch.object(storage.os, "name", "posix"):
        with pytest.raises(storage.ConfigurationError):
            MemoryStore(config(("p", root)))


def test_prelaunch_resource_failure_is_sanitized(fixture, capsys):
    root = fixture.directory("project")
    store = MemoryStore(config(("p", root)))
    with patch("cloud_repo_memory.supervisor.queue.Queue", side_effect=MemoryError("private")):
        check(store.list_memory_index("p"), code="INTERNAL_ERROR")
    output = capsys.readouterr()
    assert output.err == "Local storage worker setup or protocol failed.\n"
    assert not output.out
