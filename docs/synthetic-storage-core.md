# Synthetic local storage core

Status: implemented for **owned synthetic data on Windows fixed NTFS**, ready
for coordinator review. No MCP transport, tool registration, client integration,
real OneDrive access or production-runtime support commitment. Stage 2A remains
**CONDITIONAL GO**, not platform/OneDrive conformance.

## Setup and callable interface

From the repository root in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e '.[test]'
.\.venv\Scripts\python -B -m pytest -q
.\.venv\Scripts\python -B validation\windows-filesystem\test_winfs.py
.\.venv\Scripts\python -B tests\measure_storage.py --output validation\synthetic-storage-results.json
```

Use only an explicitly owned synthetic root. Do not substitute a real OneDrive,
account or company-knowledge folder:

```python
from cloud_repo_memory.storage import MemoryStore

store = MemoryStore({
    "schema_version": 1,
    "projects": [{"project": "sample-telemetry",
                  "root": r"C:\SyntheticMemory\sample-telemetry"}],
})
index = store.list_memory_index("sample-telemetry")
body = store.get_memory("sample-telemetry", "kst-001")
# Pass the exact source version from an index entry or previous body read:
if body["ok"]:
    conditional = store.get_memory("sample-telemetry", "kst-001",
                                   expected_version=body["source_version"])
```

`MemoryStore.from_json(config_path)` loads bounded UTF-8 JSON, rejects duplicate
keys, and requires the configuration file outside the configured roots.
The constructor accepts the same explicit mapping as an in-memory object.
Configuration errors raise a generic `ConfigurationError` and write a generic
stderr diagnostic, without publishing a partial store. No roots are discovered
from Git, environment variables, account folders or current working directory.
Restart/recreate the store for configuration changes.

The two methods return local-v1 output objects, including observations on errors.
Missing/malformed project/ID values and extra keyword fields return
`INVALID_ARGUMENT`. Python `expected_version=None` means no precondition; a
future MCP adapter must still reject explicit JSON null under the input schema.
There is intentionally no `structuredContent`, `content` or `isError` transport
wrapper yet. Source content remains untrusted data.

The editable package installs `ruamel.yaml` for safe YAML 1.2 parsing; pytest and
jsonschema are test extras. The tested versions are Python **3.10.6**, ruamel.yaml
**0.18.17**, pytest **8.4.2**, jsonschema **4.26.0**, on Windows 10 build 19045
AMD64/64-bit. `pure=True` deliberately selects the YAML parser's Python path.
Package interpreter compatibility is not a production lifecycle/support promise.
No global interpreter, Git, privilege, proxy, security or tenant settings changed.

## Implementation boundary

`src/cloud_repo_memory` contains the reusable implementation:

- `storage.py`: atomic explicit configuration, filesystem identity binding,
  serialized calls, argument precedence and validation of private worker output.
- `metadata.py`: required typed fields, lifecycle validation, safe YAML
  restrictions, source-byte hashing, body fidelity and deterministic literal
  Markdown rendering. Each source is validated even when ineligible.
- `winfs.py`: the promoted handle-based fixed-NTFS primitives and bounded scanner.
  Namespace pinning still uses real `GENERIC_READ` with `FILE_SHARE_READ`, not
  attribute-only access. Root ancestors, ignored entries, final volume paths,
  hard-link counts, identity/stat values and final inventories are checked.
- `worker.py`: source-buffer parsing and project-wide diagnostics within the
  isolated scan. Metadata, duplicates and recoverable entry/read availability
  failures are collected; limit/scope/change failures abort with no content.
- `supervisor.py`: shared serialized disposable jobs, monotonic 2-second file
  and 5-second scan budgets, 500-ms cleanup observation, retained exact worker
  ownership and an unhealthy latch when process/reader/pipe cleanup is unconfirmed.
- `results.py`: sanitized errors, deterministic diagnostic ordering/caps, and
  local-best-effort/unknown-cloud observations.

Root probes also run in isolated bounded jobs. Existing root identity is bound
at configuration; a temporarily missing root binds on its first usable call.
Subsequent identity replacement fails rather than silently rebinding. Distinct
roots are checked lexically and against available final paths/identities. Calls
never fall back to another project or a last-good cache.

Worker ownership is assigned immediately after `Popen`, before reader
construction/start. Spawn, reader, malformed/oversized protocol, termination,
wait and resource-release failures do not publish partial success. The original
worker and resources remain owned until reaping confirms release; new calls
cannot spawn replacement workers while cleanup is pending. The public response
contains only a generic `INTERNAL_ERROR` diagnostic, not private worker fields.
Private instrumentation is available only to the evaluator's capture wrapper,
never the two callable result envelopes.

Timeouts discard late results and terminate the current job; they do not imply
that a driver completed kernel I/O within the budget. The checks remain
best-effort local observations, not atomic snapshots, a malicious-same-user
sandbox, a cloud freshness guarantee or a hydration guarantee.

The original Windows harness now imports the shared primitives/supervisor.
Race injection and stall modes remain exclusively in `validation/windows-filesystem`;
the installed package contains neither those hooks nor evaluator fixtures.
Tests remove explicitly ledgered files/links and empty directories, without
recursive junction traversal.

## Executed synthetic evidence

Final callable/parser/fault suite: **223 passed, 7 skipped**, 30.04 seconds.
Those seven are **declared missing platform/pilot evidence**, not seven attempted
filesystem operations that passed.

Retained Windows harness: **38 tests, 31 passed, 7 skipped/BLOCKED**, zero
failures/errors, 21.278 seconds. These seven are **actual symlink creation
attempts blocked by WinError 1314**. Junctions, hard links, namespace-pinning
and replacement regressions remain passing. The repeated-job resource check
observed 174 handles before/after ten jobs and one thread before/after.
Synthetic file expiries observed 2,250/2,281 ms including startup; scan expiry
was observed at 5,015 ms, returned at 5,031 ms with cleanup confirmed. These are
host observations, not real-time guarantees.

Coverage includes schema examples and real result shapes; byte hashes/counts
and cross-field identity; BOM/LF/CRLF/Unicode/empty bodies; all 12 lifecycle
combinations; every required field and invalid scalar type; duplicate keys,
anchors/aliases/tags/merge keys; control/whitespace/length constraints; literal
Markdown escaping; project isolation and root replacement; updates/deletions/
conditional reads; metadata/availability/duplicate precedence and diagnostic
caps; reserved/hidden/uppercase candidates; inclusive source/frontmatter/index/
aggregate ceilings and overflow; inherited entry/depth ceilings; no late
content; setup/reader/protocol/termination/resource faults and no-respawn latching.

The five historical Kusto topics are adapted only into owned temporary test
directories. Their exact bodies and IDs are preserved; evaluator files, the old
handwritten index, historical samples, M0 manifest and M0 corpus are unchanged.
The measurement runner performs the six scenarios' **scripted required-ID reads**
after discovery with matching source versions. This is deterministic storage
coverage, **not agent selection, answer quality or real-client retrieval evidence**.

## Measurements and remaining performance miss

Raw evidence:
[before optimization](../validation/synthetic-storage-before.json) and
[final results](../validation/synthetic-storage-results.json). Each contains the
first call plus all 30 subsequent observations per corpus. The final file records
package versions and a hash of sorted runtime module bytes. All sources were
locally available synthetic files on this host's fixed NTFS drive.

| Corpus | Source bytes | Index bytes | First call, before / after | Subsequent p95, before / after |
| --- | ---: | ---: | ---: | ---: |
| 5 adapted notes | 6,220 | 1,541 | 219 / 203 ms | 235 / 219 ms |
| 100 notes | 1,048,576 | 43,004 | 687 / 594 ms | 688 / 594 ms |
| 200 notes | 2,097,152 | 85,904 | 1,156 / 891 ms | 1,187 / 907 ms |

The 100-note corpus uses exactly 60-character titles and 120-character
summary/read-when fields. Both index-byte targets pass (2,048 bytes at five;
49,152 bytes at 100), and the 100-note first-call target of 1,000 ms passes.
**The 100-note subsequent-scan p95 remains a MISS: 594 ms > 500 ms.**
The 201st candidate returns `LIMIT_EXCEEDED`, `scan_complete: false`, no index.
No latency gate is asserted for 200 notes.

One bounded optimization removed a redundant YAML composition pass, retaining
the token safety pass and safe load plus strict typed metadata validation.
Regression testing caught implicit merge flattening; explicit merge-key token
rejection was restored before the final passing run and measurements. No
persistent cache, weaker checks, changed limit, worker pool or corpus truncation.

For 100 notes, final subsequent medians were: callable elapsed **547 ms**,
worker imports **94 ms**, worker work **375 ms**, scan including parsing
**360 ms**, parsing **242 ms**. These stages overlap (parsing is part of scan),
so do not sum them. Approximately 78 ms remains between the median callable
and import/work figures for interpreter launch, scheduling, IPC, cleanup and
parent processing; this is a residual, not separately measured kernel time.
Monotonic timer granularity and ordinary host load limit precision.

P95 is nearest rank 29 of 30. Calls use a fresh worker and full scan every time.
"First" is the first index after configuration, **not proof of a cold OS disk
cache**. Callable elapsed and caller round-trip are recorded separately;
100-note caller p95 was also 594 ms. Actual MCP-client round-trip, tokenizer
identity/token counts and the 12,000-token gate remain **unknown**, not inferred
from byte counts.

## Still blocked / next review

The coordinator must review the remaining performance miss and the core before
any MCP implementation. Do not automatically start transport/client work.
Real locally available/offline/partially hydrated OneDrive placeholders,
recall-on-open, provider cancellation/cleanup, actual symlinks on an authorized
host, ACL-denial cases, other/mounted filesystems, case-sensitive NTFS and
mapped-file writers remain unverified. The restrictive sharing/ancestor-read
requirements can still conflict with editors or sync providers.

Two actual MCP clients, fresh-session agent retrieval/answer scoring, token
counts, and a second-device controlled update/deletion pilot are blocked.
No company knowledge, tenant changes or real-data deployment is authorized.
