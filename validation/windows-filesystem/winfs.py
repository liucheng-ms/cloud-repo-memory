"""Windows-only filesystem feasibility primitive, not an MCP/storage implementation."""

import ctypes as C
from ctypes import wintypes as W
from contextlib import ExitStack
from dataclasses import dataclass
import ntpath
import os
import re

if os.name != "nt":
    raise RuntimeError("This spike requires Windows")

K = C.WinDLL("kernel32", use_last_error=True)


def api(name, result, *args):
    fn = getattr(K, name)
    fn.restype, fn.argtypes = result, args
    return fn


CreateFile = api("CreateFileW", W.HANDLE, W.LPCWSTR, W.DWORD, W.DWORD,
                 C.c_void_p, W.DWORD, W.DWORD, W.HANDLE)
CloseHandle = api("CloseHandle", W.BOOL, W.HANDLE)
GetInfo = api("GetFileInformationByHandle", W.BOOL, W.HANDLE, C.c_void_p)
GetInfoEx = api("GetFileInformationByHandleEx", W.BOOL, W.HANDLE, C.c_int,
                C.c_void_p, W.DWORD)
GetFinalPath = api("GetFinalPathNameByHandleW", W.DWORD, W.HANDLE,
                   W.LPWSTR, W.DWORD, W.DWORD)
GetFileType = api("GetFileType", W.DWORD, W.HANDLE)
ReadFile = api("ReadFile", W.BOOL, W.HANDLE, C.c_void_p, W.DWORD,
               C.POINTER(W.DWORD), C.c_void_p)
GetDriveType = api("GetDriveTypeW", W.UINT, W.LPCWSTR)
GetVolumeInformation = api("GetVolumeInformationW", W.BOOL, W.LPCWSTR,
                           W.LPWSTR, W.DWORD, C.POINTER(W.DWORD),
                           C.POINTER(W.DWORD), C.POINTER(W.DWORD), W.LPWSTR, W.DWORD)

DIRECTORY = 0x10
REPARSE = 0x400
OFFLINE = 0x1000
RECALL_OPEN = 0x40000
RECALL_DATA = 0x400000
CLOUD = 0x9000001A
CLOUD_MASK = 0x0000F000
NAME_SURROGATE = 0x20000000
OPEN_FLAGS = 0x02000000 | 0x00200000 | 0x00100000
MAX_FILE = 262144
MAX_TOTAL = 16777216
MAX_ENTRIES = 2000
MAX_NOTES = 200
MAX_DEPTH = 16


class Refusal(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def check(ok):
    if not ok:
        raise C.WinError(C.get_last_error())


class FileInfo(C.Structure):
    _fields_ = [
        ("attributes", W.DWORD), ("created", W.FILETIME),
        ("accessed", W.FILETIME), ("written", W.FILETIME),
        ("volume", W.DWORD), ("size_high", W.DWORD), ("size_low", W.DWORD),
        ("links", W.DWORD), ("index_high", W.DWORD), ("index_low", W.DWORD),
    ]


class AttributeTag(C.Structure):
    _fields_ = [("attributes", W.DWORD), ("tag", W.DWORD)]


class BasicInfo(C.Structure):
    _fields_ = [
        ("created", C.c_longlong), ("accessed", C.c_longlong),
        ("written", C.c_longlong), ("changed", C.c_longlong),
        ("attributes", W.DWORD),
    ]


@dataclass(frozen=True)
class Snapshot:
    identity: tuple
    size: int
    written: int
    changed: int
    links: int
    attributes: int
    tag: int


def classify(attributes, tag, *, enumeration=False):
    if attributes & REPARSE:
        if tag & NAME_SURROGATE or (tag & ~CLOUD_MASK) != CLOUD:
            raise Refusal("SCOPE_VIOLATION")
    if attributes & (OFFLINE | RECALL_DATA):
        raise Refusal("FILE_UNAVAILABLE")
    # 0x40000 is RECALL_ON_OPEN only in enumeration, not handle metadata.
    if enumeration and attributes & RECALL_OPEN:
        raise Refusal("FILE_UNAVAILABLE")
    return "cloud-local-candidate" if attributes & REPARSE else "ordinary"


def component(name):
    if (not name or name in (".", "..") or name[-1] in " ."
            or any(c in name for c in '\\/:*?"<>|')
            or any(ord(c) < 32 for c in name)
            or re.fullmatch(r"(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", name)):
        raise Refusal("SCOPE_VIOLATION")
    return name


def relative_parts(path):
    return [component(part) for part in path.split("\\")]


def root_parts(path):
    if not re.match(r"^[A-Za-z]:\\", path) or "/" in path:
        raise Refusal("SCOPE_VIOLATION")
    drive, tail = path[:3], path[3:]
    if GetDriveType(drive) != 3:
        raise Refusal("SCOPE_VIOLATION")
    filesystem = C.create_unicode_buffer(32)
    check(GetVolumeInformation(drive, None, 0, None, None, None,
                               filesystem, len(filesystem)))
    if filesystem.value != "NTFS":
        raise Refusal("SCOPE_VIOLATION")
    return drive, [] if not tail else relative_parts(tail)


class Handle:
    def __init__(self, path):
        # Attribute-only access does NOT pin directory names on this host.
        # Read/list access activates the share restrictions; all opens still
        # use OPEN_REPARSE_POINT and OPEN_NO_RECALL, including the first one.
        self.value = CreateFile(path, 0x80000000, 1,
                                None, 3, OPEN_FLAGS, None)
        if self.value == C.c_void_p(-1).value:
            raise C.WinError(C.get_last_error())

    def __enter__(self):
        return self

    def __exit__(self, *_):
        check(CloseHandle(self.value))

    def snapshot(self):
        info, tag, basic = FileInfo(), AttributeTag(), BasicInfo()
        check(GetInfo(self.value, C.byref(info)))
        check(GetInfoEx(self.value, 9, C.byref(tag), C.sizeof(tag)))
        check(GetInfoEx(self.value, 0, C.byref(basic), C.sizeof(basic)))
        if GetFileType(self.value) != 1:
            raise Refusal("SCOPE_VIOLATION")
        classify(tag.attributes, tag.tag)
        return Snapshot((info.volume, info.index_high, info.index_low),
                        (info.size_high << 32) | info.size_low,
                        basic.written, basic.changed, info.links,
                        tag.attributes, tag.tag)

    def final_path(self):
        buffer = C.create_unicode_buffer(32768)
        length = GetFinalPath(self.value, buffer, len(buffer), 1)
        check(length)
        if length >= len(buffer) or not buffer.value.startswith("\\\\?\\Volume{"):
            raise Refusal("SCOPE_VIOLATION")
        return buffer.value


def child(stack, parent, name):
    component(name)
    h = stack.enter_context(Handle(ntpath.join(parent, name)))
    state = h.snapshot()
    final = h.final_path()
    # Compare the exact normalized parent, not a textual root prefix.
    if (ntpath.dirname(final).rstrip("\\") != parent.rstrip("\\")
            or ntpath.basename(final).casefold() != name.casefold()):
        raise Refusal("SCOPE_VIOLATION")
    return h, state, final


class Root:
    def __init__(self, path, expected_identity=None):
        self.path, self.expected_identity = path, expected_identity
        self.stack = ExitStack()

    def __enter__(self):
        try:
            drive, parts = root_parts(self.path)
            handle = self.stack.enter_context(Handle(drive))
            state, final = handle.snapshot(), handle.final_path()
            # Reject SUBST-like drive roots that resolve to a subdirectory.
            if not re.fullmatch(r"\\\\\?\\Volume\{[^}]+\}\\", final):
                raise Refusal("SCOPE_VIOLATION")
            for part in parts:
                handle, state, final = child(self.stack, final, part)
                if not state.attributes & DIRECTORY:
                    raise Refusal("PROJECT_UNAVAILABLE")
            if self.expected_identity is not None and state.identity != self.expected_identity:
                raise Refusal("LOCAL_CHANGE_DETECTED")
            self.handle, self.state, self.final = handle, state, final
            return self
        except BaseException:
            self.stack.close()
            raise

    def __exit__(self, *args):
        return self.stack.__exit__(*args)

    def read(self, relative, expected=None, before_data=None):
        parts = relative_parts(relative)
        with ExitStack() as stack:
            parent = self.final
            for part in parts[:-1]:
                _, state, parent = child(stack, parent, part)
                if not state.attributes & DIRECTORY:
                    raise Refusal("SCOPE_VIOLATION")
            metadata, before, _ = child(stack, parent, parts[-1])
            if before.attributes & DIRECTORY or before.links != 1:
                raise Refusal("SCOPE_VIOLATION")
            if expected is not None and before != expected:
                raise Refusal("LOCAL_CHANGE_DETECTED")
            if before.size > MAX_FILE:
                raise Refusal("LIMIT_EXCEEDED")
            if before_data:
                before_data()
            data_handle, opened, _ = child(stack, parent, parts[-1])
            if before != opened or metadata.snapshot() != before:
                raise Refusal("LOCAL_CHANGE_DETECTED")
            result = bytearray()
            while True:
                # One extra byte detects growth at the inclusive byte ceiling.
                buffer = C.create_string_buffer(min(65536, MAX_FILE + 1 - len(result)))
                count = W.DWORD()
                check(ReadFile(data_handle.value, buffer, len(buffer), C.byref(count), None))
                result.extend(buffer.raw[:count.value])
                if len(result) > MAX_FILE:
                    raise Refusal("LIMIT_EXCEEDED")
                if not count.value:
                    break
            if (metadata.snapshot() != before or data_handle.snapshot() != before
                    or len(result) != before.size):
                raise Refusal("LOCAL_CHANGE_DETECTED")
            return bytes(result)


def scan(path, *, event=lambda _: None, hook=lambda *_: None, expected_root=None):
    """Return exact buffers only after a bounded walk and inventory recheck.

    Hooks are deterministic synthetic race injection, not runtime inputs.
    Use supervisor.run for deadlines; direct calls are intentionally unbounded.
    """
    with Root(path, expected_root) as root, ExitStack() as directory_handles:
        inventories, candidates, result = {}, [], {}
        entries = 0

        def inventory(parent, relative, depth, first):
            nonlocal entries
            found = {}
            with os.scandir(parent) as iterator:
                for entry in iterator:
                    if first:
                        entries += 1
                    if entries > MAX_ENTRIES or len(found) >= MAX_ENTRIES:
                        raise Refusal("LIMIT_EXCEEDED")
                    component(entry.name)
                    event("file_start")
                    # stat(follow_symlinks=False) supplies enumeration-only recall
                    # bits; never use it as the final identity/containment proof.
                    enum = entry.stat(follow_symlinks=False)
                    classify(enum.st_file_attributes, enum.st_reparse_tag, enumeration=True)
                    with ExitStack() as stack:
                        _, state, _ = child(stack, parent, entry.name)
                        found[entry.name] = state
                        rel = ntpath.join(relative, entry.name)
                        if first and state.attributes & DIRECTORY:
                            if depth + 1 > MAX_DEPTH:
                                raise Refusal("LIMIT_EXCEEDED")
                            _, pinned_state, pinned_final = child(
                                directory_handles, parent, entry.name)
                            if state != pinned_state:
                                raise Refusal("LOCAL_CHANGE_DETECTED")
                            event("file_end")
                            inventory(pinned_final, rel, depth + 1, True)
                        elif first and entry.name.lower().endswith(".md") and not (
                                not relative and entry.name.lower() == "memory.md"):
                            if state.links != 1:
                                raise Refusal("SCOPE_VIOLATION")
                            candidates.append((rel, state))
                            if len(candidates) > MAX_NOTES:
                                raise Refusal("LIMIT_EXCEEDED")
                    event("file_end")
            if first:
                inventories[parent] = (relative, depth, found)
            return found

        inventory(root.final, "", 0, True)
        hook("after_inventory", root)
        total = 0
        for relative, state in candidates:
            event("file_start")
            if total + state.size > MAX_TOTAL:
                raise Refusal("LIMIT_EXCEEDED")
            data = root.read(relative, state)
            total += len(data)
            result[relative] = data
            event("file_end")
        hook("after_reads", root)
        for parent, (relative, depth, expected) in inventories.items():
            if inventory(parent, relative, depth, False) != expected:
                raise Refusal("LOCAL_CHANGE_DETECTED")
        if root.handle.snapshot().identity != root.state.identity:
            raise Refusal("LOCAL_CHANGE_DETECTED")
        return result
