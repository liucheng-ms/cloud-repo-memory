"""Owned local NTFS tests only. Never select or discover a real OneDrive path."""

import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import anyio
import pytest

from cloud_repo_memory.metadata import parse, version
from cloud_repo_memory import winfs
from cloud_repo_memory.supervisor import Supervisor
from support import REPO

SPEC = importlib.util.spec_from_file_location(
    "onedrive_pilot", REPO / "validation" / "onedrive" / "pilot.py")
pilot = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pilot)
OBSERVER_SPEC = importlib.util.spec_from_file_location(
    "onedrive_observer", REPO / "validation" / "onedrive" / "observe_server.py")
observer = importlib.util.module_from_spec(OBSERVER_SPEC)
OBSERVER_SPEC.loader.exec_module(observer)


@pytest.fixture
def setup(fixture):
    evidence = pilot.Evidence(fixture.base)
    corpus = pilot.Corpus(fixture.base / "new-notes", evidence)
    try:
        yield corpus, evidence
    finally:
        # Only this owned local fixture is traversed, never a caller/live root.
        fixture.files.clear()
        fixture.dirs[:] = [fixture.base]
        for path in sorted(fixture.base.rglob("*"), key=lambda item: len(item.parts)):
            (fixture.dirs if path.is_dir() else fixture.files).append(path)


def events(evidence):
    return [json.loads(line) for line in evidence.ledger.read_text("utf-8").splitlines()]


def populated(corpus):
    originals = pilot.payloads()
    corpus.create()
    for name, data in originals.items():
        corpus.add(name, data)
    return originals


def test_all_deliberate_cli_gates_required():
    with pytest.raises(SystemExit) as caught:
        pilot.arguments([])
    assert caught.value.code == 2
    gates = ["--approve-new-synthetic-files", "--approve-edit-delete-recreate",
             "--confirm-evidence-outside-sync", "--run-live-sdk"]
    args = ["--root", "C:\\Fictional\\new", "--evidence-parent", "C:\\FictionalEvidence"]
    for gate in gates:
        with pytest.raises(SystemExit):
            pilot.arguments(args + [item for item in gates if item != gate])
    assert pilot.arguments(args + gates).run_live_sdk


def test_only_five_approved_fixture_bodies():
    originals = pilot.payloads()
    assert tuple(originals) == pilot.kit.FILES
    for name, data in originals.items():
        raw = (REPO / "validation" / "samples" / "kusto-memory" / "agent-input"
               / name).read_bytes()
        assert parse(data, pilot.PROJECT).body.encode() == pilot.kit.historical_body(raw)


def test_existing_target_stops_without_enumeration(setup, monkeypatch):
    corpus, evidence = setup
    corpus.path.mkdir()
    sentinel = corpus.path / "existing.txt"
    sentinel.write_bytes(b"untouched fictional sentinel")
    with monkeypatch.context() as patcher:
        patcher.setattr(os, "scandir", lambda *_: pytest.fail("Existing directory enumerated"))
        with pytest.raises(FileExistsError):
            corpus.create()
    assert sentinel.read_bytes() == b"untouched fictional sentinel"
    assert corpus.identity is None
    assert not any(event["event"] == "directory-create-intent" for event in events(evidence))


def test_ambiguous_absence_is_not_missing(setup, monkeypatch):
    corpus, _ = setup
    with monkeypatch.context() as patcher:
        patcher.setattr(os.path, "lexists", lambda _: False)
        def denied(_):
            raise PermissionError("fictional denial")
        patcher.setattr(os, "lstat", denied)
        with pytest.raises(PermissionError):
            pilot.absent(corpus.path)


def test_exclusive_file_create_cannot_overwrite(setup):
    corpus, _ = setup
    populated(corpus)
    name = pilot.kit.FILES[0]
    before = (corpus.path / name).read_bytes()
    with winfs.Root(str(corpus.path), corpus.identity) as root:
        with pytest.raises(OSError):
            pilot.OwnedFile(root.final, name, create=True)
    assert (corpus.path / name).read_bytes() == before


@pytest.mark.parametrize("unexpected_directory", [False, True])
def test_unexpected_entries_stop_before_mutation(setup, unexpected_directory):
    corpus, _ = setup
    originals = populated(corpus)
    unexpected = corpus.path / "unexpected"
    if unexpected_directory:
        unexpected.mkdir()
    else:
        unexpected.write_bytes(b"untouched fictional sentinel")
    with pytest.raises(RuntimeError, match="Unexpected entry"):
        corpus.mutate(pilot.kit.FILES[0], None)
    assert (corpus.path / pilot.kit.FILES[0]).read_bytes() == originals[pilot.kit.FILES[0]]
    assert unexpected.exists()


@pytest.mark.parametrize("replace_identity", [False, True])
def test_hash_or_identity_mismatch_stops_deletion(setup, replace_identity):
    corpus, _ = setup
    originals = populated(corpus)
    path = corpus.path / pilot.kit.FILES[0]
    if replace_identity:
        # Keep the first file allocated so NTFS cannot recycle its ID.
        path.rename(corpus.evidence.path / "displaced.md")
        path.write_bytes(originals[path.name])
    else:
        path.write_bytes(originals[path.name] + b"\nFictional external edit.\n")
    with pytest.raises(RuntimeError, match="identity changed|hash/content changed"):
        corpus.mutate(path.name, None)
    assert path.exists()


def test_redirect_or_unavailable_parent_stops_before_child_stat(setup, monkeypatch):
    corpus, evidence = setup
    target_parent = corpus.path.parent
    original = Path.lstat
    for attributes, tag, code in (
        (winfs.DIRECTORY | winfs.REPARSE, 0xA0000003, "SCOPE_VIOLATION"),
        (winfs.DIRECTORY | winfs.REPARSE | winfs.OFFLINE, winfs.CLOUD, "FILE_UNAVAILABLE"),
    ):
        def metadata(path):
            if path == target_parent:
                return SimpleNamespace(st_file_attributes=attributes, st_reparse_tag=tag)
            assert path != corpus.path
            return original(path)
        with monkeypatch.context() as patcher:
            patcher.setattr(Path, "lstat", metadata)
            with pytest.raises(winfs.Refusal) as caught:
                pilot.preflight_parent(corpus.path, evidence)
        assert caught.value.code == code
    assert not corpus.path.exists()
    assert winfs.classify(winfs.DIRECTORY | winfs.REPARSE, winfs.CLOUD) == "cloud-local-candidate"


def test_evidence_under_sync_parent_refused(setup):
    corpus, _ = setup
    with pytest.raises(RuntimeError, match="Evidence cannot be inside"):
        pilot.main([
            "--root", str(corpus.path), "--evidence-parent", str(corpus.path.parent),
            "--approve-new-synthetic-files", "--approve-edit-delete-recreate",
            "--confirm-evidence-outside-sync", "--run-live-sdk",
        ])
    assert not corpus.path.exists()


def test_ownership_is_persisted_before_bytes_and_no_resume(setup, monkeypatch):
    corpus, evidence = setup
    corpus.create()
    original = pilot.OwnedFile.write

    def inspect(handle, data):
        ledger = events(evidence)
        assert ledger[-1]["event"] == "file-owned-empty"
        assert tuple(ledger[-1]["identity"]) == handle.snapshot().identity
        assert handle.bytes() == b""
        assert any(row["event"] == "directory-owned" for row in ledger)
        original(handle, data)

    with monkeypatch.context() as patcher:
        patcher.setattr(pilot.OwnedFile, "write", inspect)
        name, data = next(iter(pilot.payloads().items()))
        corpus.add(name, data)
    with pytest.raises(FileExistsError):
        pilot.Corpus(corpus.path, evidence).create()
    assert (corpus.path / name).read_bytes() == data


def test_write_failure_retains_partial_file_and_ownership(setup, monkeypatch):
    corpus, evidence = setup
    corpus.create()
    name, data = next(iter(pilot.payloads().items()))

    def fail(_handle, _data):
        raise OSError("Fictional write failure.")

    with monkeypatch.context() as patcher:
        patcher.setattr(pilot.OwnedFile, "write", fail)
        with pytest.raises(OSError, match="Fictional write failure"):
            corpus.add(name, data)
    assert (corpus.path / name).read_bytes() == b""
    assert events(evidence)[-1]["event"] == "file-owned-empty"
    with pytest.raises(FileExistsError):
        pilot.Corpus(corpus.path, evidence).create()
    assert (corpus.path / name).exists()


@pytest.mark.parametrize("failure", ["write", "flush"])
@pytest.mark.parametrize("pending_cleanup", [False, True])
@pytest.mark.parametrize("server_catches_error", [False, True])
def test_observer_evidence_failure_preserves_worker_ownership(
        fixture, monkeypatch, failure, pending_cleanup, server_catches_error):
    supervisor = Supervisor()
    original_run, original_reap = supervisor._run, supervisor.reap
    original_launch, original_open = subprocess.Popen, Path.open
    launched, answers, writes = [], [], []

    class FailedEvidence(io.StringIO):
        def write(self, text):
            writes.append(json.loads(text))
            # The evidence operation must occur AFTER real supervisor cleanup.
            assert len(answers) == 1
            assert answers[0]["cleanup_confirmed"] is (not pending_cleanup)
            assert launched[0].poll() is not None
            if failure == "write":
                raise OSError(28, "Fictional evidence disk full.")
            return super().write(text)

        def flush(self):
            if failure == "flush":
                raise OSError(28, "Fictional evidence disk full.")
            return super().flush()

    def launch(command, **kwargs):
        process = original_launch(command, **kwargs)
        launched.append(process)
        return process

    def run(command):
        result = original_run(command)
        answers.append(result)
        return result

    def reap(reader_wait=0):
        if pending_cleanup and supervisor.pending is not None:
            return False
        return original_reap(reader_wait)

    ledger = fixture.base / "mocked-observer-ledger.jsonl"
    stream = FailedEvidence()

    def open_ledger(path, *args, **kwargs):
        if path == ledger:
            return stream
        return original_open(path, *args, **kwargs)

    def serve():
        # A real local subprocess with no filesystem/provider work. It emits
        # a real result, then waits so supervisor termination is observable.
        script = (
            "import json,time; "
            "print(json.dumps({'kind':'result','at':time.monotonic(),'ok':True}),flush=True); "
            "time.sleep(30)"
        )
        try:
            supervisor.run([sys.executable, "-B", "-c", script,
                            json.dumps({"operation": "probe"})])
        except OSError:
            if server_catches_error:
                # Model a server boundary converting the exception to an error
                # response and later returning a normal shutdown code.
                return 0
            raise
        pytest.fail("Evidence failure was hidden by a successful observer return.")

    monkeypatch.setattr(observer.storage, "_SUPERVISOR", supervisor)
    monkeypatch.setattr(subprocess, "Popen", launch)
    monkeypatch.setattr(supervisor, "_run", run)
    monkeypatch.setattr(supervisor, "reap", reap)
    monkeypatch.setattr(observer.server, "main", serve)
    monkeypatch.setattr(Path, "open", open_ledger)
    monkeypatch.setattr(sys, "argv", ["observer", "unused-config", str(ledger)])
    try:
        error_type = RuntimeError if server_catches_error else OSError
        message = "Pilot observer evidence failed" if server_catches_error else "Fictional evidence disk full"
        with pytest.raises(error_type, match=message) as caught:
            observer.main()
        if not server_catches_error:
            assert caught.value.errno == 28
        assert len(launched) == 1 and len(answers) == 1
        assert answers[0].get("supervisor_state") != "spawn-unavailable"
        assert len(writes) == 1 and writes[0]["event"] == "worker-launched"
        process = launched[0]
        assert process.poll() is not None
        if pending_cleanup:
            assert answers[0]["supervisor_state"] == "cleanup-pending"
            assert supervisor.pending[0] is process
            assert not process.stdout.closed
            # The same real supervisor refuses replacement while ownership is retained.
            rejected = original_run(["must-not-launch"])
            assert rejected["supervisor_state"] == "cleanup-pending"
            assert rejected["cleanup_confirmed"] is False
            assert len(launched) == 1
            assert supervisor.pending[0] is process
        else:
            assert answers[0]["ok"] is True
            assert supervisor.pending is None
            assert process.stdout.closed
    finally:
        for process in launched:
            if process.poll() is None:
                process.terminate()
            process.wait(timeout=5)
        assert original_reap(1)
        assert supervisor.pending is None


def test_real_sdk_lifecycle_on_owned_local_temp_only(setup):
    corpus, evidence = setup
    originals = populated(corpus)
    anyio.run(pilot.exercise, corpus, originals)
    ledger = events(evidence)
    responses = [event for event in ledger if event["event"] == "tool-response"]
    assert len(responses) == 13
    assert len({event["server_pid"] for event in responses}) == 1
    assert [event["response"]["structuredContent"]["error"]["code"]
            for event in responses if event["response"]["isError"]] == [
                "MEMORY_CHANGED", "MEMORY_NOT_FOUND"]
    assert ledger[-1]["event"] == "pilot-passed"
    assert sorted(path.name for path in corpus.path.iterdir()) == sorted(originals)
    assert {name: version((corpus.path / name).read_bytes()) for name in originals} == {
        name: version(data) for name, data in originals.items()}
