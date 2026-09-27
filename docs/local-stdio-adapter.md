# Synthetic local stdio MCP adapter and Copilot setup

Status: **implemented and verified with a real subprocess MCP SDK protocol
client**, on owned synthetic Windows fixed-NTFS files. This is not two
coding-agent integrations, retrieval/answer-quality evidence, OneDrive
conformance or production-runtime support. Subsequent bounded
[Copilot smoke](real-client-evaluation.md) and
[personal OneDrive directory](personal-onedrive-pilot.md) observations are
reported separately. A checkout-side setup helper now prepares explicit
session-added Copilot configuration and verifies it with the SDK. It does not
register a server, discover installed clients, or modify agent settings.

## Repeatable synthetic setup: install, map, configure, verify

Use Windows fixed NTFS and Python 3.10 or newer. All paths below are
**placeholders**: substitute explicitly owned, existing, non-redirected local
parents. Do not use a real OneDrive directory, company notes, auth/history
paths, or a synchronized configuration directory. The `--synthetic-only` flag
is an operator assertion, not content classification or authorization.

### 1. Install a durable runtime

From this checkout in PowerShell, install into a **new dedicated venv** outside
the checkout and knowledge root. No client installation or login is needed.

```powershell
if (Test-Path 'C:\OwnedMemoryRuntime\.venv') { throw 'Choose a new runtime venv.' }
python -m venv 'C:\OwnedMemoryRuntime\.venv'
$Python = 'C:\OwnedMemoryRuntime\.venv\Scripts\python.exe'
& $Python -m pip install .
& $Python -I -B -c 'import cloud_repo_memory; print(cloud_repo_memory.__file__)'
& $Python -I -B -m cloud_repo_memory --help
```

Stop if any command fails. The import path must be in this venv's
`Lib\site-packages\cloud_repo_memory`, not this checkout's `src` directory.
Do **not** use `pip install -e` for this durable workflow. This is a normal
runtime install; development/test dependencies are not required.
`-I` ignores Python's current-directory import path, user site and `PYTHONPATH`;
it is not a filesystem or client-profile sandbox. Record the runtime and
dependency versions locally if you need to reproduce an exact environment;
the package's dependency ranges are not a lockfile.

### 2. Supply the project/root and one synthetic note

Choose a project slug explicitly; it is not inferred from Git or the directory
name. This example creates a new root and a complete strict local-v1 note.
If you already have an owned synthetic root, do not recreate it: supply its
path and one of its eligible memory IDs instead. Do not copy the historical
M0 samples unchanged.

```powershell
New-Item -ItemType Directory -Path 'C:\OwnedSyntheticMemory\sample-telemetry' -ErrorAction Stop
$Note = @'
---
schema_version: 1
id: setup-check
project: sample-telemetry
title: Synthetic setup check
summary: Fictional setup verification reference.
read_when: Checking local synthetic memory connectivity.
status: active
approval: approved
---
# Synthetic setup check
The fictional verification label is amber-otter.
'@
New-Item -ItemType File `
  -Path 'C:\OwnedSyntheticMemory\sample-telemetry\setup-check.md' `
  -Value $Note -ErrorAction Stop
```

The [local-v1 contract](local-mvp-contract.md) defines metadata, limits and
eligibility. Notes are human-maintained untrusted reference data. The setup
helper and runtime never create, edit, approve or delete knowledge.

### 3. Generate new, external configuration

Still from this checkout, run the development/setup helper. These arguments
are all explicit; there is no environment, home, Git or OneDrive discovery.
`--output` must be a **new direct child** of `--owned-parent`, outside the
knowledge root (neither directory may contain the other).

```powershell
$SetupArgs = @(
  '--owned-parent', 'C:\OwnedMemoryConfig',
  '--output', 'C:\OwnedMemoryConfig\copilot-001',
  '--python', $Python,
  '--project', 'sample-telemetry',
  '--root', 'C:\OwnedSyntheticMemory\sample-telemetry',
  '--synthetic-only'
)
& $Python -B -m validation.copilot_setup configure @SetupArgs
```

`configure` checks the explicit directories and interpreter and writes exactly
`local.json` (one project/root mapping) and `copilot-mcp.json` (one local
`synthetic-memory` server, absolute Python/config paths, and only
`list_memory_index` / `get_memory`). It does not launch any subprocess or scan
the notes. Root platform/eligibility checks happen in the real runtime during
verification; `CONFIGURED` alone is not a working-server claim.

The helper refuses relative/network paths, redirected directory ancestors,
configuration/knowledge overlap, and any existing output file or directory.
It uses exclusive file creation, never overwrites configuration, and retains
partial output on failure. Inspect it and choose a new output name for retry.
Directory checks are not protection against malicious concurrent same-user
replacement. Keep generated machine-specific configuration local, outside
version control and synchronized knowledge. No secrets, credentials, evaluator
rubrics, prompts or trace directories are generated.

This deliberately supports **one explicit mapping per setup directory**, not
automatic project selection or persistent client registration. Configuration
changes require a new setup directory, re-verification and a fresh server/session.

### 4. Verify through the SDK, without Copilot

```powershell
& $Python -B -m validation.copilot_setup verify @SetupArgs --memory-id setup-check
```

Use the same explicit arguments as configuration. The verifier requires both
files to match the generated bytes exactly before starting anything: edited
commands, extra servers, duplicate keys and mismatched paths are refused.
To change a mapping, generate new files rather than hand-editing this pair.

The verifier starts **only the installed Python MCP runtime**, using the exact
generated command and arguments (`-I -B -m cloud_repo_memory --config ...`),
with the config directory as its working directory. It checks SDK initialization,
the exact two tools/schemas/read-only annotations, an actual project index and
one selected `get_memory` with the version extracted from that index. It checks
matching structured/text results, error flags, identities and versions.
No direct note read is used as a substitute for an MCP call.

Success is one JSON summary with `status: "SDK_VERIFIED"` and
`coding_client: "NOT_RUN"`; it does not print note bodies or persist traces.
The protocol phase has a 20-second deadline. The deadline ends before transport
teardown so it cannot cancel cleanup: the SDK closes stdin, waits up to its
default two seconds and then applies its owned-process termination policy.
This is a bounded protocol check plus SDK cleanup, **not a hard OS termination
guarantee** or evidence of a real client's worker cleanup under provider stalls.

| Failure | Operator action |
| --- | --- |
| Missing interpreter/package, startup or protocol failure | Check stderr; run the absolute venv's `-I -B -m cloud_repo_memory --help`, confirm the installed import path, and reinstall in that owned venv if needed. |
| Missing path, permission or config mismatch | Check the explicit arguments and directory permissions; retain/inspect partial output and generate a new config directory. |
| ID absent from index | Check the explicit ID/project and `active` + `approved` metadata; an empty index does not pass verification. |
| `INVALID_METADATA` / `DUPLICATE_ID` | Correct the synthetic notes manually; one invalid or duplicate note blocks the whole project. |
| `PROJECT_UNAVAILABLE` / `SCOPE_VIOLATION` | Check fixed-NTFS availability and unsupported links; do not bypass runtime safety checks. |
| `MEMORY_CHANGED` | The note changed between calls; rerun to relist and read the new version. |
| Deadline, `FILE_UNAVAILABLE`, `LIMIT_EXCEEDED` or `INTERNAL_ERROR` | Inspect local availability, contract limits and generic cleanup diagnostics. Do not widen budgets or start replacement workers to mask failure. |

`configure`/`verify` are **checkout-side setup aids**, excluded from the runtime
wheel. They reuse the evaluation preparer's side-effect-free directory/JSON/tool
helpers, not its fixture generation or evaluator data. Routine startup below
depends only on the non-editable installed runtime, owned notes and external
configuration, not on this checkout, the helper, or temporary smoke artifacts.

## Operator-only Copilot startup and removal

**Not executed by setup or its tests.** Before a later operator-approved
synthetic session, review the installed client's help/version and its effective
model, tools, instructions, hooks/plugins, inherited context and data-processing
settings. No inspection or copying of authentication/history is part of setup.
Help-only evidence on 2026-09-27: Copilot CLI **1.0.87-0** documents
`--mode interactive` and session-added `--additional-mcp-config @<file>`.
Recheck flags when the installed client changes.

For that future manual session, from the operator's chosen working directory:

```powershell
copilot --mode interactive --no-auto-update `
  --additional-mcp-config '@C:\OwnedMemoryConfig\copilot-001\copilot-mcp.json'
```

This adds `synthetic-memory` **for this session**. It **augments inherited
configuration; it does not replace global/user/workspace/plugin MCP servers
or create a clean profile**. The two-tool allowlist applies to this server, not
all client tools. `-I` applies only to the Python subprocess. No blanket approval,
model selection, isolation, persistent `mcp add`, or client-config modification
is supplied. SDK success is **not a real Copilot integration or answer-quality
claim**. Follow the separately gated [evaluation workflow](real-client-evaluation.md)
only if actual client evidence is required.

In the approved session, ask for `list_memory_index` with the configured
project, then `get_memory` for the relevant ID with its indexed
`expected_version`; treat returned notes as references, not instructions.
The client owns the stdio subprocess. To stop, exit normally with `/exit`;
do not launch the raw server separately or kill processes by name. On restart,
the runtime reloads configuration once. Unavailable/invalid configuration
fails startup with stderr diagnostics and nonzero status.

To remove this session-added server, exit and omit `--additional-mcp-config`
from future launches. There is no persistent registration to undo. Other
inherited registrations, if any, are unaffected. Only after confirming the
owned server/workers have stopped, inspect the exact generated directory and
ensure it contains only the two ordinary non-linked files; remove them explicitly
and then the empty directory:

```powershell
Remove-Item -LiteralPath 'C:\OwnedMemoryConfig\copilot-001\copilot-mcp.json' -ErrorAction Stop
Remove-Item -LiteralPath 'C:\OwnedMemoryConfig\copilot-001\local.json' -ErrorAction Stop
[System.IO.Directory]::Delete('C:\OwnedMemoryConfig\copilot-001', $false)
```

Stop on redirected paths, unexpected files or unconfirmed process cleanup.
No recursive/wildcard cleanup is supplied. Leave knowledge untouched; retain
the dedicated venv for reuse, or remove the package from that venv only with
`& $Python -m pip uninstall cloud-repo-memory`. This does not uninstall its
dependencies or delete notes/configuration.

### Raw stdio and packaging reference

Equivalent runtime entry points, for a protocol client rather than an
interactive shell:

```powershell
& $Python -I -B -m cloud_repo_memory --config 'C:\OwnedMemoryConfig\copilot-001\local.json'
& 'C:\OwnedMemoryRuntime\.venv\Scripts\cloud-repo-memory.exe' `
  --config 'C:\OwnedMemoryConfig\copilot-001\local.json'
```

An idle raw launcher is waiting for MCP messages, not hung at a shell prompt.
Only protocol traffic goes to stdout; diagnostics go to stderr. No HTTP
listener, cloud authentication, database, search or mutation is added. The SDK
brings dependencies for other transports but this adapter does not activate them.
For a distributable wheel, use the developer test/build environment:
`.\.venv\Scripts\python -m build`, then install the resulting wheel with
the dedicated runtime venv's `python -m pip install <wheel-path>`.

## SDK and schema boundary

Verified environment: Python **3.10.6**, MCP **1.30.0**, AnyIO **4.15.1**,
jsonschema **4.26.0**, ruamel.yaml **0.18.17**, pytest **8.4.2**, Windows 10
build 19045 AMD64. No interpreter upgrade or global install was performed.
`mcp>=1.30,<2` intentionally selects the supported 1.x maintenance line.
The [version-tagged upstream README](https://github.com/modelcontextprotocol/python-sdk/blob/v1.30.0/README.md)
states that 1.x receives critical bug fixes and security patches. This is not
a claim that 1.x is the latest stable SDK.

The SDK low-level `Server`, typed request handlers, stdio transport and
`ClientSession` implement the protocol; there is no custom JSON-RPC stack.
Direct registration of the typed `CallToolRequest` handler avoids the SDK
decorator's automatic validation/error-to-text normalization and raw exception
messages. [SDK implementation at the tested tag](https://github.com/modelcontextprotocol/python-sdk/blob/v1.30.0/src/mcp/server/lowlevel/server.py).

Malformed transport frames use the SDK's nonfatal handling
(`raise_exceptions=False`): a generic protocol logging notification is emitted,
not a fabricated local memory envelope, and later valid requests remain usable.
All registered request handlers, including discovery and SDK ping, have an
explicit exception boundary before the SDK can stringify an unexpected error.
Known-tool failures produce the normal `INTERNAL_ERROR` envelope; unexpected
discovery/ping failures produce a generic `-32603` protocol error. Each emits a
generic stderr notice. Unexpected `McpError` payloads are sanitized too;
intentional unknown-tool errors remain `-32602`. These guards catch `Exception`,
not cancellation or other `BaseException` subclasses, and checkpoint cancellation
before publishing an error from previously running thread work.

Exactly `list_memory_index` and `get_memory` are advertised, with read-only,
non-destructive, idempotent and closed-world annotations. Each input/output
schema preserves its named normative definition and adds the same document's
`$schema` and `$defs` so references resolve standalone. No schema rules change.
Draft 2020-12 validation runs before calling storage; in particular explicit
`expected_version: null` fails even though the Python API treats `None` as
omission. Tool argument errors return `INVALID_ARGUMENT`; valid unknown projects
and storage failures preserve their existing domain envelopes. Unknown tool
names and malformed SDK request parameters return protocol errors, not a
fabricated memory result.

Every dispatched tool result has the exact contract object in
`structuredContent`, one text block with the matching JSON object, and
`isError = !ok`. Output validation rejects malformed internal payloads with a
generic `INTERNAL_ERROR`. No private timing/worker fields are exposed.

Setuptools maps the existing `contracts` directory to
`cloud_repo_memory.contracts`; the allowlisted package data is only
`local-mvp-v1.schema.json`. There is no second maintained or generated schema.
Both wheel variants contain exactly the ten runtime Python modules
(`__init__`, `__main__`, `metadata`, `results`, `schemas`, `server`, `storage`,
`supervisor`, `winfs`, `worker`), `contracts/__init__.py`, the one normative JSON
resource, and standard distribution metadata/license/entry-point records.
The sdist includes the same normative source JSON. Tests, injection hooks,
validation fixtures and historical M0 manifests are excluded from distribution.

## Cancellation, ownership and shutdown

Admission uses a cancellable capacity-one limiter. Only admitted work moves to
an AnyIO thread with `abandon_on_cancel=False`; synchronous filesystem calls
never block the event loop. An active job may finish under existing budgets.
Cancellation then checkpoints before returning, so a late successful result
cannot be published. Waiting admissions are cancelled without launching work.
The tested SDK cancels and joins in-flight handlers when transport reaches EOF.

Storage still owns a single serialized supervisor. The original 2-second file,
5-second scan and further 500-ms cleanup-observation semantics are unchanged.
Worker ownership is registered immediately after launch. If cleanup remains
unconfirmed, subsequent calls return cleanup-pending errors without starting a
replacement. The minimal public `MemoryStore.reap_workers()` helper only tries
to release exited workers/resources; it never spawns or cancels jobs.

After protocol closure, shutdown attempts reaping off the event loop. If
unconfirmed, it emits one generic stderr notice and remains the owner, checking
the same worker/resources every 100 ms. It admits no more requests and exits
only after confirmed release. This can remain **blocked indefinitely** if the
OS never confirms cleanup: it is not a hard kernel-I/O completion guarantee.
There is no detached worker, replacement loop or global process termination.

Protocol tests use the SDK's real subprocess transport and client. Test-only
instrumentation delays one real runtime worker by one second and records its
exact process/ownership events outside tool output. Separate fault injection
withholds cleanup confirmation for 1.2 seconds after process exit; that tests
the unhealthy latch and retained resources, **not a real provider stall**.
Tests close the actual subprocess stdin for EOF, allow up to ten seconds to
observe owned graceful exit, and check the worker process handle is signaled.
They do not change the SDK client's default two-second forced-termination
policy. Real coding clients may kill the server/tree earlier; that behavior and
real provider cancellation remain unverified.

## Reproducible evidence

For developer checks, prepare a separate owned `.venv` in this checkout with
`python -m venv .venv` and
`.\.venv\Scripts\python -m pip install '.[test]'` (do not recreate an existing
venv). Use a non-editable installation for the setup import-origin assertion.
The runtime-only installation above intentionally does not include pytest/build.

Routine setup's targeted checks:

```powershell
.\.venv\Scripts\python -B -m pytest -q tests\test_copilot_setup.py `
  tests\test_real_client_kit.py tests\test_stdio.py tests\test_supervisor.py
```

Observed on 2026-09-27: **73 passed**, including **21 setup-specific checks**,
with Python 3.10.6 and the dependency versions listed above. Coverage includes
explicit absolute paths with spaces, non-launching/exclusive configuration,
unchanged synthetic source bytes, overlap/redirect rejection (including a
simulated canonical-path alias), tampered-command/duplicate-key refusal,
real SDK discovery/index/versioned get, empty/ineligible/invalid/duplicate note
failures, CLI exit diagnostics, and confirmed normal subprocess exit.
A test-only unresponsive subprocess exercises a shortened protocol deadline;
its exact owned process exited within the test's ten-second observation bound.
This does not simulate a stuck filesystem provider or prove client cleanup.
The installed-runtime check observes imports from the dedicated venv's
`Lib\site-packages`, not `src`, under `-I` from an unrelated working directory;
that one check declares a skip for editable installs rather than claiming
non-editable evidence. All 73 checks passed without skips in this run.
Owned generated test files/directories were removed. No client/model was
launched, registered or configured globally. Runtime, packaging and normative
schema files were unchanged; prior packaging evidence below is not a new build.

Broader adapter and packaging checks:

```powershell
.\.venv\Scripts\python -B -m pytest -q
.\.venv\Scripts\python -B validation\windows-filesystem\test_winfs.py
.\.venv\Scripts\python -B tests\check_wheel.py
```

Adapter delivery results on this host:

| Check | Observed result |
| --- | --- |
| Full storage/parser/fault/protocol suite after protocol correction | 317 passed, 7 declared missing-evidence skips; 78.83 s |
| Retained Windows harness after protocol correction | 31 passed, 7 actual WinError 1314 symlink blocks; 22.266 s |
| Ten repeated Windows jobs | 174 handles before/after; one thread |
| Direct wheel, isolated off-checkout install | Resource-byte parity; module and console stdio launchers pass |
| Wheel rebuilt from sdist, isolated off-checkout install | Same parity, allowlisted inventory and both launchers pass |
| Owned external packaging workspaces | Both venvs, builds, synthetic files and copied probe removed; absence asserted |

Protocol coverage includes initialization/discovery, exact schemas/annotations,
matching result representations/error flags, successful synthetic index/body
reads, missing/invalid/extra/null arguments, unknown tools/projects, unavailable
roots, invalid/duplicate metadata, lifecycle, conditional version mismatch,
edits/deletion and recovery. Cancellation and EOF prove queued calls do not
start, active work stays owned, pings remain responsive, cancelled jobs do not
publish success, cleanup-pending prevents replacement and confirmed release
permits later recovery. Startup failures have stderr-only diagnostics; captured
stdout is parsed by the SDK with no non-protocol frames.

Coordinator review of the initial 312-pass delivery found that
`raise_exceptions=True` terminated the session on malformed transport input.
The correction adds five real-subprocess regressions: invalid boolean/object
methods and invalid JSON followed by ping and successful retrieval; unexpected
tool `RuntimeError`/`McpError`, discovery and ping errors followed by recovery.
Captured stdout results/notifications and stderr contain no injected private
sentinel. Existing cancellation/EOF and retained-worker cases still pass.
Both isolated wheel variants were rebuilt and rechecked after the correction.

`check_wheel.py` runs `build --wheel` directly, then default `build` (sdist then
wheel), verifies artifact inventories, and installs each into a fresh venv
outside the checkout. Its copied standalone probe runs Python isolated mode
from an unrelated directory with only synthetic notes/config. It asserts
imports come from that venv, not the checkout, and compares the packaged
resource hash to the normative source. It uses only public third-party package
retrieval and owned local files.

The seven declared skips are not attempted device tests. The separate seven
symlink blocks are actual privilege failures. No platform gate was weakened.
The earlier 100-note/1 MiB p95 **594 ms still misses 500 ms**; no tuning,
remeasurement or changed performance target accompanies this adapter.
Tokenizer identity/counts, agent selection and answer scoring, two actual coding
clients, OneDrive placeholders/hydration/cleanup, remaining Windows platform
cases and a second-device update/deletion pilot remain unverified and blocked.
