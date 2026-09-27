"""Build direct/sdist wheels, install off-checkout, run real stdio, remove owned files."""

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import zipfile

REPO = Path(__file__).resolve().parents[1]


def run(command, cwd):
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=240)
    if result.returncode:
        raise RuntimeError(f"Packaging check failed:\n{result.stdout}\n{result.stderr}")
    return result.stdout


def main():
    expected = (REPO / "contracts" / "local-mvp-v1.schema.json").read_bytes()
    with tempfile.TemporaryDirectory(prefix="cloud-memory-wheel-check-") as temporary:
        base = Path(temporary).resolve()
        assert not base.is_relative_to(REPO)
        cwd = base / "unrelated-cwd"
        cwd.mkdir()
        notes = cwd / "notes"
        notes.mkdir()
        (notes / "note.md").write_text(
            "---\nschema_version: 1\nid: note-001\nproject: p\ntitle: Synthetic\n"
            "summary: Synthetic only\nread_when: Testing\nstatus: active\n"
            "approval: approved\n---\nUntrusted synthetic reference.\n", encoding="utf-8")
        configuration = cwd / "config.json"
        configuration.write_text(json.dumps({
            "schema_version": 1, "projects": [{"project": "p", "root": str(notes)}]}),
            encoding="utf-8")
        probe = cwd / "wheel_probe.py"
        probe.write_bytes(Path(__file__).with_name("wheel_probe.py").read_bytes())
        for variant, flags in (("direct", ["--wheel"]), ("from-sdist", [])):
            output = base / variant
            # Default `build` makes an sdist, then rebuilds the wheel from that sdist.
            run([sys.executable, "-m", "build", *flags, "--outdir", str(output), str(REPO)], cwd)
            wheel, = output.glob("*.whl")
            with zipfile.ZipFile(wheel) as archive:
                assert archive.read("cloud_repo_memory/contracts/local-mvp-v1.schema.json") == expected
                intended = {"cloud_repo_memory/" + path.name
                            for path in (REPO / "src" / "cloud_repo_memory").glob("*.py")}
                intended.update({"cloud_repo_memory/contracts/__init__.py",
                                 "cloud_repo_memory/contracts/local-mvp-v1.schema.json"})
                assert {name for name in archive.namelist()
                        if name.startswith("cloud_repo_memory/")} == intended
                assert all(name in intended or ".dist-info/" in name for name in archive.namelist())
                print(variant + " wheel inventory: " + ", ".join(sorted(archive.namelist())))
            if variant == "from-sdist":
                sdist, = output.glob("*.tar.gz")
                with tarfile.open(sdist) as archive:
                    names = [name.partition("/")[2] for name in archive.getnames()]
                    assert not any(name.startswith(("tests/", "validation/")) for name in names)
                    resources = [name for name in names if name.startswith("contracts/")]
                    assert sorted(resources) == ["contracts/__init__.py",
                                                 "contracts/local-mvp-v1.schema.json"]
                    schema, = [item for item in archive.getmembers()
                               if item.name.endswith("/contracts/local-mvp-v1.schema.json")]
                    with archive.extractfile(schema) as stream:
                        assert stream.read() == expected
            environment = base / (variant + "-venv")
            run([sys.executable, "-m", "venv", str(environment)], cwd)
            python = environment / "Scripts" / "python.exe"
            run([str(python), "-m", "pip", "install", "--quiet", str(wheel)], cwd)
            print(variant + ": " + run([
                str(python), "-I", "-B", str(probe), str(configuration),
                hashlib.sha256(expected).hexdigest()], cwd).strip())
    assert not base.exists()
    print("Owned external build directories, synthetic notes and isolated venvs removed: PASS")


if __name__ == "__main__":
    main()
