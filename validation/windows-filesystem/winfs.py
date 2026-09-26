"""Test-only compatibility and deterministic race injection over shared primitives."""

from unittest.mock import patch
from cloud_repo_memory import winfs as shared

SharedRoot = shared.Root
shared_scan = shared.scan
Refusal = shared.Refusal


class Root(SharedRoot):
    def read(self, relative, expected=None, before_data=None):
        original = shared.child
        count = 0

        def child(*args):
            nonlocal count
            count += 1
            if count == len(shared.relative_parts(relative)) + 1 and before_data:
                before_data()
            return original(*args)

        with patch.object(shared, "child", child):
            return super().read(relative, expected)


def scan(path, *, event=lambda _: None, hook=lambda *_: None, expected_root=None):
    read_sources, recheck = shared.Scanner.read_sources, shared.Scanner.recheck

    def read(scanner, consume):
        hook("after_inventory", scanner.root)
        return read_sources(scanner, consume)

    def check(scanner):
        hook("after_reads", scanner.root)
        return recheck(scanner)

    with patch.object(shared.Scanner, "read_sources", read), patch.object(
            shared.Scanner, "recheck", check):
        return shared_scan(path, event=event, expected_root=expected_root)
