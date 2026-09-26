"""Run: python -B -m unittest discover -s validation\\windows-filesystem -v"""

import ctypes as C
from ctypes import wintypes as W
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

import winfs
from winfs import Refusal, Root, scan
from supervisor import Supervisor

HERE = Path(__file__).resolve().parent
SENTINEL = b"OUTSIDE_SYNTHETIC_SCOPE_DO_NOT_RETURN"


class Fixture:
    """Ledger cleanup: unlink exact files/links, rmdir exact empty directories."""

    def __init__(self):
        self.base = Path(tempfile.mkdtemp(prefix="fixture-", dir=HERE))
        self.files, self.links, self.dirs = [], [], [self.base]

    def directory(self, relative):
        path = self.base / relative
        path.mkdir()
        self.dirs.append(path)
        return path

    def file(self, relative, content=b"synthetic note\n"):
        path = self.base / relative
        path.write_bytes(content)
        self.files.append(path)
        return path

    def junction(self, relative, target):
        path = self.base / relative
        quote = lambda value: "'" + str(value).replace("'", "''") + "'"
        subprocess.run(
            ["pwsh", "-NoProfile", "-Command",
             f"New-Item -ItemType Junction -Path {quote(path)} -Target {quote(target)} "
             "| Out-Null"], check=True, capture_output=True, text=True)
        self.links.append((path, True))
        return path

    def symlink(self, relative, target, directory=False):
        path = self.base / relative
        try:
            os.symlink(target, path, target_is_directory=directory)
        except OSError as error:
            if error.winerror == 1314:
                raise unittest.SkipTest("Symlink privilege/developer mode unavailable (1314)")
            raise
        self.links.append((path, directory))
        return path

    def clean(self):
        for path, directory in reversed(self.links):
            if os.path.lexists(path):
                (os.rmdir if directory else os.unlink)(path)
        for path in reversed(self.files):
            if os.path.lexists(path):
                # Refuse cleanup through a redirected parent, even inside fixture.
                parent = path.parent
                while parent != self.base.parent:
                    if os.lstat(parent).st_file_attributes & winfs.REPARSE:
                        raise RuntimeError("Refusing cleanup through reparse parent")
                    parent = parent.parent
                os.unlink(path)
        for path in reversed(self.dirs):
            if os.path.lexists(path):
                os.rmdir(path)


class FilesystemTests(unittest.TestCase):
    def setUp(self):
        self.fixture = Fixture()
        self.addCleanup(self.fixture.clean)
        self.root = self.fixture.directory("project")
        self.outside = self.fixture.directory("project-sibling")
        self.fixture.file("project-sibling\\sentinel.md", SENTINEL)

    def refusal(self, code, operation, no_read=False):
        with patch("winfs.ReadFile", wraps=winfs.ReadFile) as read:
            with self.assertRaises(Refusal) as raised:
                operation()
            self.assertEqual(raised.exception.code, code)
            if no_read:
                read.assert_not_called()

    def test_regular_exact_bytes_and_identity(self):
        data = b"\xef\xbb\xbf---\r\nid: synthetic\r\n---\r\n# Body\r\n"
        path = self.fixture.file("project\\note.md", data)
        with Root(str(self.root)) as root:
            self.assertTrue(root.final.startswith("\\\\?\\Volume{"))
            with winfs.Handle(str(path)) as handle:
                state = handle.snapshot()
                self.assertEqual(state.identity[1] << 32 | state.identity[2], path.stat().st_ino)
                self.assertEqual(state.links, 1)
            self.assertEqual(root.read("note.md"), data)
        self.assertEqual(scan(str(self.root)), {"note.md": data})

    def test_candidate_selection_hidden_nested_uppercase(self):
        nested = self.fixture.directory("project\\hidden")
        set_attributes = winfs.api("SetFileAttributesW", W.BOOL, W.LPCWSTR, W.DWORD)
        winfs.check(set_attributes(str(nested), 2))
        self.fixture.file("project\\MEMORY.md", b"derived ignored")
        self.fixture.file("project\\ignored.txt")
        self.fixture.file("project\\hidden\\MEMORY.md", b"nested included")
        self.fixture.file("project\\UPPER.MD", b"uppercase included")
        self.assertEqual(set(scan(str(self.root))), {"hidden\\MEMORY.md", "UPPER.MD"})

    def test_traversal_stream_device_and_absolute_paths(self):
        bad = ["..\\project-sibling\\sentinel.md", ".\\note.md", "note.md:stream",
               "C:\\file.md", "\\\\server\\share", "\\\\?\\C:\\file.md",
               "nested/escape.md", "note.md.", "note.md ", "NUL", "", "x\\\\y"]
        with Root(str(self.root)) as root:
            for relative in bad:
                with self.subTest(relative=relative):
                    self.refusal("SCOPE_VIOLATION", lambda: root.read(relative), True)

    def test_invalid_roots(self):
        for path in ["project", "C:project", "\\\\server\\share", "\\\\?\\C:\\project",
                     "C:\\a\\..\\b", "C:\\a:stream", "C:/project"]:
            with self.subTest(path=path):
                self.refusal("SCOPE_VIOLATION", lambda: scan(path), True)

    def test_file_symlink_outside(self):
        self.fixture.symlink("project\\link.md", self.outside / "sentinel.md")
        self.refusal("SCOPE_VIOLATION", lambda: scan(str(self.root)), True)

    def test_file_symlink_inside(self):
        self.fixture.file("project\\note.md")
        self.fixture.symlink("project\\link.md", self.root / "note.md")
        self.refusal("SCOPE_VIOLATION", lambda: scan(str(self.root)), True)

    def test_directory_symlink_outside(self):
        self.fixture.symlink("project\\redirect", self.outside, True)
        self.refusal("SCOPE_VIOLATION", lambda: scan(str(self.root)), True)

    def test_root_symlink(self):
        root = self.fixture.symlink("root-link", self.outside, True)
        self.refusal("SCOPE_VIOLATION", lambda: scan(str(root)), True)

    def test_ancestor_symlink(self):
        self.fixture.directory("project-sibling\\nested")
        parent = self.fixture.symlink("parent-link", self.outside, True)
        self.refusal("SCOPE_VIOLATION", lambda: scan(str(parent / "nested")), True)

    def test_junction_outside(self):
        self.fixture.junction("project\\redirect", self.outside)
        self.refusal("SCOPE_VIOLATION", lambda: scan(str(self.root)), True)

    def test_junction_inside(self):
        nested = self.fixture.directory("project\\nested")
        self.fixture.junction("project\\redirect", nested)
        self.refusal("SCOPE_VIOLATION", lambda: scan(str(self.root)), True)

    def test_root_junction(self):
        root = self.fixture.junction("root-link", self.outside)
        self.refusal("SCOPE_VIOLATION", lambda: scan(str(root)), True)

    def test_ancestor_junction(self):
        self.fixture.directory("project-sibling\\nested")
        parent = self.fixture.junction("parent-link", self.outside)
        self.refusal("SCOPE_VIOLATION", lambda: scan(str(parent / "nested")), True)

    def test_hardlink_outside_and_inside(self):
        link = self.root / "linked.md"
        os.link(self.outside / "sentinel.md", link)
        self.fixture.files.append(link)
        self.refusal("SCOPE_VIOLATION", lambda: scan(str(self.root)), True)
        link.unlink()
        original = self.fixture.file("project\\note.md")
        os.link(original, link)
        self.refusal("SCOPE_VIOLATION", lambda: scan(str(self.root)), True)

    def test_ignored_redirect_is_not_silently_skipped(self):
        self.fixture.symlink("project\\ignored.txt", self.outside / "sentinel.md")
        self.refusal("SCOPE_VIOLATION", lambda: scan(str(self.root)), True)

    def test_replacement_before_data_open_denied(self):
        source = self.fixture.file("project\\note.md")
        replacement = self.fixture.file("replacement.md", SENTINEL)
        observed = []

        def replace():
            with self.assertRaises(OSError) as raised:
                os.replace(replacement, source)
            observed.append(raised.exception.winerror)

        with Root(str(self.root)) as root:
            self.assertEqual(root.read("note.md", before_data=replace), b"synthetic note\n")
        self.assertEqual(len(observed), 1)
        self.assertIn(observed[0], (5, 32))

    def test_root_and_ancestor_rename_denied_while_pinned(self):
        parent = self.fixture.directory("parent")
        root = self.fixture.directory("parent\\root")
        with Root(str(root)):
            for target in (root, parent):
                self.fixture.dirs.append(Path(str(target) + "-moved"))
                with self.assertRaises(OSError) as raised:
                    os.rename(target, str(target) + "-moved")
                self.assertIn(raised.exception.winerror, (5, 32))

    def test_preexisting_writer_fails_closed(self):
        path = self.fixture.file("project\\note.md")
        with path.open("r+b"):
            with self.assertRaises(OSError) as raised:
                scan(str(self.root))
            self.assertEqual(raised.exception.winerror, 32)

    def test_same_size_mtime_replacement_detected_before_read(self):
        path = self.fixture.file("project\\note.md")
        stat = path.stat()
        with winfs.Handle(str(path)) as handle:
            expected = handle.snapshot()
        replacement = self.fixture.file("replacement.md", b"x" * stat.st_size)
        os.utime(replacement, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        os.replace(replacement, path)
        with Root(str(self.root)) as root:
            self.refusal("LOCAL_CHANGE_DETECTED", lambda: root.read("note.md", expected), True)

    def test_scan_replacement_outside_sentinel_denied_or_detected(self):
        path = self.fixture.file("project\\note.md")
        replacement = self.fixture.file("replacement.md", SENTINEL)
        denied = []

        def replace(phase, root):
            if phase == "after_inventory":
                try:
                    os.replace(replacement, path)
                except OSError as error:
                    self.assertIn(error.winerror, (5, 32))
                    denied.append(error.winerror)

        try:
            result = scan(str(self.root), hook=replace)
        except Refusal as error:
            self.assertEqual(error.code, "LOCAL_CHANGE_DETECTED")
        else:
            self.assertTrue(denied)
            self.assertNotIn(SENTINEL, result.values())
            self.assertEqual(result["note.md"], b"synthetic note\n")

    def test_pinned_directory_cannot_be_replaced_by_outside_junction(self):
        directory = self.fixture.directory("project\\nested")
        self.fixture.file("project\\nested\\note.md")
        redirect = self.fixture.junction("redirect", self.outside)
        observed = []

        def replace(phase, root):
            if phase == "after_inventory":
                moved = self.root / "nested-moved"
                with self.assertRaises(OSError) as raised:
                    try:
                        os.rename(directory, moved)
                    except OSError:
                        raise
                    else:
                        # Restore the fixture ledger before asserting failure.
                        os.rename(moved, directory)
                        self.fail("Pinned directory rename unexpectedly succeeded")
                self.assertIn(raised.exception.winerror, (5, 32))
                with self.assertRaises(OSError):
                    os.replace(redirect, directory)
                observed.append(raised.exception.winerror)

        result = scan(str(self.root), hook=replace)
        self.assertEqual(len(observed), 1)
        self.assertEqual(result, {"nested\\note.md": b"synthetic note\n"})

    def test_file_replaced_with_symlink_before_read(self):
        path = self.fixture.file("project\\note.md")
        link = self.fixture.symlink("replacement-link", self.outside / "sentinel.md")
        with winfs.Handle(str(path)) as handle:
            expected = handle.snapshot()
        os.replace(link, path)
        with Root(str(self.root)) as root:
            self.refusal("SCOPE_VIOLATION", lambda: root.read("note.md", expected), True)

    def test_root_identity_change_between_calls(self):
        empty = self.fixture.directory("empty")
        with Root(str(empty)) as root:
            expected = root.state.identity
        moved = self.fixture.base / "moved"
        empty.rename(moved)
        self.fixture.dirs.append(moved)
        empty.mkdir()
        self.refusal("LOCAL_CHANGE_DETECTED",
                     lambda: scan(str(empty), expected_root=expected), True)

    def test_end_inventory_add_delete_edit(self):
        for change in ("add", "delete", "edit"):
            with self.subTest(change=change):
                path = self.fixture.file("project\\note.md")

                def mutate(phase, _):
                    if phase == "after_reads":
                        if change == "add":
                            self.fixture.file("project\\added.md")
                        elif change == "delete":
                            path.unlink()
                        else:
                            path.write_bytes(b"changed")

                self.refusal("LOCAL_CHANGE_DETECTED",
                             lambda: scan(str(self.root), hook=mutate))
                added = self.root / "added.md"
                if added.exists():
                    added.unlink()

    def test_inclusive_file_size_and_overflow(self):
        path = self.fixture.file("project\\note.md", b"x" * winfs.MAX_FILE)
        self.assertEqual(len(scan(str(self.root))["note.md"]), winfs.MAX_FILE)
        path.write_bytes(b"x" * (winfs.MAX_FILE + 1))
        self.refusal("LIMIT_EXCEEDED", lambda: scan(str(self.root)), True)

    def test_inclusive_candidate_limit(self):
        for index in range(200):
            self.fixture.file(f"project\\n{index}.md", b"")
        self.assertEqual(len(scan(str(self.root))), 200)
        self.fixture.file("project\\overflow.md", b"")
        self.refusal("LIMIT_EXCEEDED", lambda: scan(str(self.root)), True)

    def test_inclusive_entry_limit(self):
        for index in range(2000):
            self.fixture.file(f"project\\n{index}.txt", b"")
        self.assertEqual(scan(str(self.root)), {})
        self.fixture.file("project\\overflow.txt", b"")
        self.refusal("LIMIT_EXCEEDED", lambda: scan(str(self.root)), True)

    def test_inclusive_depth_limit(self):
        relative = "project"
        for _ in range(16):
            relative += "\\d"
            self.fixture.directory(relative)
        self.assertEqual(scan(str(self.root)), {})
        self.fixture.directory(relative + "\\overflow")
        self.refusal("LIMIT_EXCEEDED", lambda: scan(str(self.root)), True)

    def test_inclusive_aggregate_limit(self):
        for index in range(64):
            self.fixture.file(f"project\\n{index}.md", b"x" * winfs.MAX_FILE)
        self.assertEqual(sum(map(len, scan(str(self.root)).values())), winfs.MAX_TOTAL)
        self.fixture.file("project\\overflow.md", b"x")
        self.refusal("LIMIT_EXCEEDED", lambda: scan(str(self.root)))

    def test_tag_policy_only_not_cloud_validation(self):
        for variant in range(16):
            self.assertEqual(winfs.classify(winfs.REPARSE, winfs.CLOUD | variant << 12),
                             "cloud-local-candidate")
        for tag in (0xA0000003, 0xA000000C, 0x80000099, 0x80000021):
            self.refusal("SCOPE_VIOLATION", lambda: winfs.classify(winfs.REPARSE, tag))
        for attr in (winfs.OFFLINE, winfs.RECALL_DATA, winfs.RECALL_OPEN):
            self.refusal("FILE_UNAVAILABLE", lambda: winfs.classify(
                winfs.REPARSE | attr, winfs.CLOUD, enumeration=True))
        self.assertEqual(winfs.classify(winfs.RECALL_OPEN, 0), "ordinary")

    def test_final_parent_check_rejects_prefix_sibling(self):
        self.fixture.file("project\\note.md")
        with Root(str(self.root)) as root:
            with patch.object(winfs.Handle, "final_path",
                              return_value=root.final + "-sibling\\note.md"):
                self.refusal("SCOPE_VIOLATION", lambda: root.read("note.md"), True)

    def test_supervised_normal_scan(self):
        self.fixture.file("project\\note.md", b"normal")
        supervisor = Supervisor()
        answer = supervisor.run(str(self.root))
        self.assertTrue(answer["ok"], answer)
        self.assertTrue(answer["cleanup_confirmed"], answer)
        self.assertEqual(answer["files"]["note.md"]["sha256"],
                         hashlib.sha256(b"normal").hexdigest())
        self.assertIsNone(supervisor.pending)
        print("NORMAL", json.dumps(answer))

    def test_synthetic_file_and_scan_stalls_cleanup_and_recovery(self):
        path = self.fixture.file("project\\note.md")
        supervisor = Supervisor()
        for mode, expected, minimum in (
                ("stall-file", "FILE_UNAVAILABLE", 2000),
                ("stall-file", "FILE_UNAVAILABLE", 2000),
                ("stall-scan", "LIMIT_EXCEEDED", 5000)):
            answer = supervisor.run(str(self.root), mode)
            print("STALL", mode, json.dumps(answer))
            self.assertFalse(answer["ok"])
            self.assertEqual(answer["code"], expected)
            self.assertGreaterEqual(answer["decision_ms"], minimum)
            # Host observation tolerance, not a hard real-time guarantee.
            self.assertLess(answer["elapsed_ms"], minimum + 1500)
            self.assertTrue(answer["cleanup_confirmed"])
            self.assertNotIn("files", answer)
            self.assertIsNone(supervisor.pending)
            path.write_bytes(b"reopened after worker exit")
        self.assertTrue(supervisor.run(str(self.root))["ok"])

    def test_cleanup_pending_latches_without_respawn(self):
        # Policy test only: never pretend a mock is a stuck Windows driver.
        class Pending:
            def poll(self):
                return None

        supervisor = Supervisor()
        supervisor.pending = (Pending(), None)
        with patch("supervisor.subprocess.Popen") as launch:
            for _ in range(100):
                answer = supervisor.run(str(self.root))
                self.assertEqual(answer["code"], "INTERNAL_ERROR")
                self.assertFalse(answer["cleanup_confirmed"])
                self.assertEqual(answer["supervisor_state"], "cleanup-pending")
            launch.assert_not_called()

    def test_reader_initialization_failure_cleans_real_workers_before_retry(self):
        self.fixture.file("project\\note.md")
        real_popen = subprocess.Popen
        for failure in ("constructor", "start"):
            with self.subTest(failure=failure):
                supervisor = Supervisor()
                processes = []

                def launch(*args, **kwargs):
                    process = real_popen(*args, **kwargs)
                    processes.append(process)

                    def cleanup():
                        if process.poll() is None:
                            process.terminate()
                        process.wait(timeout=1)
                        process.stdout.close()

                    self.addCleanup(cleanup)
                    return process

                target = ("supervisor.threading.Thread" if failure == "constructor"
                          else "supervisor.threading.Thread.start")
                with patch("supervisor.subprocess.Popen", side_effect=launch), patch(
                        target, side_effect=RuntimeError("synthetic reader failure")):
                    for _ in range(3):
                        answer = supervisor.run(str(self.root), "stall-scan")
                        self.assertFalse(answer["ok"], answer)
                        self.assertEqual(answer["code"], "INTERNAL_ERROR")
                        self.assertEqual(answer["supervisor_state"], "reader-unavailable")
                        self.assertTrue(answer["cleanup_confirmed"])
                        self.assertIsNone(supervisor.pending)
                        self.assertIsNotNone(processes[-1].poll())
                        self.assertTrue(processes[-1].stdout.closed)
                self.assertEqual(len(processes), 3)
                self.assertTrue(supervisor.run(str(self.root))["ok"])

    def test_reader_initialization_failure_retains_unconfirmed_worker(self):
        # Fault injection only, not a claim about real uncancellable kernel I/O.
        for failure in ("constructor", "start"):
            with self.subTest(failure=failure):
                supervisor = Supervisor()
                process = Mock()
                process.poll.return_value = None
                process.wait.side_effect = subprocess.TimeoutExpired("synthetic worker", 0.5)
                target = ("supervisor.threading.Thread" if failure == "constructor"
                          else "supervisor.threading.Thread.start")
                with patch("supervisor.subprocess.Popen", return_value=process) as launch, patch(
                        target, side_effect=RuntimeError("synthetic reader failure")):
                    answer = supervisor.run(str(self.root))
                    self.assertEqual(answer["code"], "INTERNAL_ERROR")
                    self.assertEqual(answer["supervisor_state"], "cleanup-pending")
                    self.assertFalse(answer["cleanup_confirmed"])
                    self.assertIs(supervisor.pending[0], process)
                    reader = supervisor.pending[1]
                    if failure == "constructor":
                        self.assertIsNone(reader)
                    else:
                        self.assertIsNone(reader.ident)
                    for _ in range(100):
                        self.assertFalse(supervisor.run(str(self.root))["cleanup_confirmed"])
                    launch.assert_called_once()
                    process.terminate.assert_called_once()
                    process.wait.assert_called_once()
                    process.stdout.close.assert_not_called()
                    process.poll.return_value = 1
                    self.assertTrue(supervisor.reap())
                    process.stdout.close.assert_called_once()
                    self.assertIsNone(supervisor.pending)

    def test_late_success_discarded(self):
        answer = Supervisor().run(str(self.root), "late-result")
        self.assertFalse(answer["ok"], answer)
        self.assertEqual(answer["code"], "FILE_UNAVAILABLE")
        self.assertNotIn("files", answer)
        self.assertTrue(answer["cleanup_confirmed"])

    def test_repeated_jobs_do_not_accumulate_resources(self):
        self.fixture.file("project\\note.md")
        count_handles = winfs.api("GetProcessHandleCount", W.BOOL, W.HANDLE,
                                 C.POINTER(W.DWORD))

        def count():
            result = W.DWORD()
            winfs.check(count_handles(W.HANDLE(-1), C.byref(result)))
            return result.value

        supervisor = Supervisor()
        self.assertTrue(supervisor.run(str(self.root))["ok"])
        before, threads = count(), threading.active_count()
        for _ in range(10):
            self.assertTrue(supervisor.run(str(self.root))["ok"])
            self.assertIsNone(supervisor.pending)
        after = count()
        self.assertLessEqual(after, before + 2)
        self.assertEqual(threading.active_count(), threads)
        print("RESOURCES", json.dumps({"jobs": 10, "handles_before": before,
                                      "handles_after": after, "threads": threads}))


if __name__ == "__main__":
    print("ENVIRONMENT", platform.platform(), platform.python_version(),
          platform.machine(), "pointer_bits", C.sizeof(C.c_void_p) * 8)
    unittest.main(verbosity=2)
