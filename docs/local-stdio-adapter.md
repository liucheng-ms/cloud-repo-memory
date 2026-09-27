# Synthetic local stdio MCP adapter

Status: **implemented and verified with a real subprocess MCP SDK protocol
client**, on owned synthetic Windows fixed-NTFS files. This is not two
coding-agent integrations, retrieval/answer-quality evidence, OneDrive
conformance or production-runtime support. Subsequent bounded
[Copilot smoke](real-client-evaluation.md) and
[personal OneDrive directory](personal-onedrive-pilot.md) observations are
reported separately. Routine client registration remains follow-up work;
the server does not discover or modify installed agent settings.

## Install and launch

From this checkout in PowerShell, using the experimental Python 3.10 minimum:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e '.[test]'
.\.venv\Scripts\python -B -m cloud_repo_memory --config C:\SyntheticMemoryConfig\local.json
```

Equivalent console entry point:

```powershell
.\.venv\Scripts\cloud-repo-memory.exe --config C:\SyntheticMemoryConfig\local.json
```

These are tested launcher forms with **placeholder synthetic paths**, not
commands to discover or ingest a real OneDrive folder. Create the explicitly
owned synthetic root and put strict local-v1 Markdown notes inside it. Keep
configuration outside all knowledge roots, for example:

```json
{
  "schema_version": 1,
  "projects": [
    {"project": "sample-telemetry", "root": "C:\\SyntheticMemory\\sample-telemetry"}
  ]
}
```

The [local v1 contract](local-mvp-contract.md) specifies note metadata, ceilings,
eligibility and errors. All notes and metadata are untrusted reference data.
Configuration is explicit and loaded once; restart to change it. Missing or
invalid configuration fails startup with a generic stderr diagnostic and
nonzero status. No implicit root discovery or automatic MCP registration.

The server reads MCP traffic on stdin and writes only MCP traffic to stdout.
It is not an interactive shell; an idle launcher is awaiting protocol messages.
Use absolute interpreter/entry-point and configuration paths when launching from
another directory. `--help` is conventional CLI help, not a running MCP session.
SDK diagnostics are replaced with generic stderr messages: no wire argument
values, paths, note contents, credentials or raw exception text.

For a wheel:

```powershell
.\.venv\Scripts\python -m build
# Install the resulting dist\cloud_repo_memory-0.1.0-py3-none-any.whl
# into a separate owned venv; use that venv's launcher with --config.
```

No HTTP listener, cloud authentication, database, search or mutations are added.
The MCP SDK brings dependencies for other transports, but this adapter does not
configure or activate them.

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
