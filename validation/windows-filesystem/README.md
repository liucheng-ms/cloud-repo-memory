# Windows filesystem feasibility harness

Dependency-free Python 3.10+ on Windows; PowerShell 7 (`pwsh`) creates synthetic
directory junctions in tests. The tested filesystem is local fixed-drive NTFS.
Other filesystem types fail closed. No package installation, administrator
elevation, developer-mode changes, network calls, or real OneDrive content are
needed. Symlink tests explicitly skip if Windows returns privilege error 1314.

From the repository root in PowerShell:

```powershell
python -B validation\windows-filesystem\test_winfs.py
```

Or use standard discovery:

```powershell
python -B -m unittest discover -s validation\windows-filesystem -v
```

Fixtures are unique `fixture-*` directories immediately under this directory.
The harness creates only fictional bytes. The "outside" sentinel is outside the
synthetic **project** but inside the same owned fixture. The script needs write
permission here to construct fixtures; source reading itself is read-only.
Cleanup removes ledgered links, files, and then empty directories individually,
never recursively follows a junction. A cleanup failure is a test error, not
ignored. `-B` avoids bytecode cache artifacts.

Files:

- `winfs.py`: direct Win32 handle checks and small recursive scan/read primitive.
  Direct calls have **no hard deadline**; the supervisor is required for the
  deadline experiment.
- `supervisor.py`: one disposable worker per job; 2-second file and 5-second
  whole-job budgets, failure-only late results, a 500-ms cleanup observation
  budget, retained ownership/fault latch if cleanup is unconfirmed. Its private
  `--worker` and stall modes are test machinery, not a server interface.
- `test_winfs.py`: synthetic positives, redirects, replacement regressions,
  inclusive limits, timeout/resource observations and clearly labeled policy
  mocks.

The supervisor's internal result contains **relative fixture names, byte counts,
and hashes**, not body text. It is not the MCP contract envelope and must not be
exposed as one. Tests call the primitive directly to check exact source buffers.
Do not point this experimental harness at company knowledge or a real OneDrive
folder. Passing tests do not authorize that access.

See [findings and gate decision](../../docs/windows-filesystem-feasibility.md)
for observed results, API sources, limitations and required real-device work.
