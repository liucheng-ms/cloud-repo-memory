"""Owned local NTFS tests only. Never select or discover a real OneDrive path."""

import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace

import anyio
import pytest

from cloud_repo_memory.metadata import parse, version
from cloud_repo_memory import winfs
from support import REPO

SPEC = importlib.util.spec_from_file_location(
    "onedrive_pilot", REPO / "validation" / "onedrive" / "pilot.py")
pilot = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pilot)


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
