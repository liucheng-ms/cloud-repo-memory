# Personal OneDrive directory pilot

## Result and evidence boundary

**PASS for one bounded, single-device local-directory experiment, not OneDrive
synchronization or Files On-Demand acceptance.** On 2026-09-27, the opt-in
[runner](../validation/onedrive/pilot.py) exclusively created the user-approved
`<approved-OneDrive-test-directory>` and generated only five fictional Markdown
notes. One real MCP SDK stdio session observed baseline reads, an edit, deletion,
and restoration without restarting its server. Exactly **one live invocation,
zero retries, 13 tool calls, and 14 filesystem workers** (including configuration
probing) ran. Total observed elapsed time was **6,703 ms**.

The folder was under the user's configured **personal** OneDrive directory.
Every observed source had **tag zero**, not a cloud reparse tag. This is evidence
of actual directory-path behavior, **not a cloud-placeholder read pass**, company
tenant validation, cloud upload confirmation, second-device synchronization,
pinning, offline availability, online-only/partial hydration, absence of implicit
hydration, atomic snapshots, global freshness, or hard kernel cancellation.
No existing personal/company file contents or account settings were inspected.

This supplements, but does not satisfy, the broader
[OneDrive deployment runbook](onedrive-deployment.md). The
[local-v1 contract](local-mvp-contract.md) and
[filesystem feasibility limits](windows-filesystem-feasibility.md) still apply.
The production runtime was not changed. No coding agent, model, Microsoft Graph
request, sign-in/token inspection, sync pause, network change, cloud-tag creation,
pin/dehydrate action, or conflict/race experiment was performed.

## Reproduction: explicit approval, new directory only

This runner is **not** part of automatic tests and has no default live path.
Do not rerun it against the retained pilot directory: **any existing target,
including an empty directory or dangling redirect, requires stopping for a new
coordinator/user decision**. There is no resume, reset, force, or cleanup mode.
A different live directory also needs separate approval.

Use the installed project dependencies described in
[local stdio installation](local-stdio-adapter.md), with the interpreter/runtime
and evidence outside all synchronized directories. Run from this repository.
Replace the three placeholders only with explicitly approved absolute paths:

```powershell
& '<absolute-local-python-executable>' -B validation\onedrive\pilot.py `
  --root '<approved-OneDrive-test-directory>' `
  --evidence-parent '<existing-owned-nonsynchronized-evidence-directory>' `
  --approve-new-synthetic-files `
  --approve-edit-delete-recreate `
  --confirm-evidence-outside-sync `
  --run-live-sdk
```

All four flags and both directory arguments are required. These flags acknowledge
authorization; they do not obtain it or verify account identity. No account,
profile, registry, OneDrive-root enumeration, or automatic path discovery occurs.
The caller attests that the evidence parent is outside synchronization; local
nonredirected-directory checks do not discover every possible sync provider.

The runner uses the acceptance artifact's five metadata overlays and preserves
the historical fictional Kusto bodies, reusing the client kit's body-extraction
helper without invoking its directory/configuration generator. It creates no
`MEMORY.md`, configuration, manifest, diagnostic, or evaluator file in OneDrive.

Safety and failure behavior:

- Check ancestors outermost-first, using non-following metadata and the existing
  fixed-NTFS final-handle containment checks. Ordinary cloud-family tags are
  classified rather than blanket-rejected; redirect/unknown tags and unavailable
  flags stop the run. No hydration/download API is called.
- Recheck absence with `lexists` plus non-following `lstat`, then exclusive
  `mkdir` under a pinned parent. Persist directory identity outside OneDrive
  before any generated file write.
- Create each source with Win32 `CREATE_NEW`, no-follow/no-recall flags, and
  deny-write/delete sharing. Persist creation intent and the new empty file's
  handle identity before writing bytes.
- Before calls/mutations, enumerate only the owned test directory and reject
  unexpected names, subdirectories, redirects, hard links, identities or bytes.
  Before editing/deleting, recheck the latest ledgered identity, exact hash,
  note ID and bytes through the same exclusive mutation handle. Deletion uses
  that validated handle, not a later path-based unlink.
- Preserve partial files and private evidence on failure; do not remove
  unexpected files, roll back blindly, retry, or delete the directory. Only
  after the expected deletion checks succeed is the original note recreated
  exclusively and its restored version verified.

The SDK has a 10-second request timeout and a 90-second observation window.
There are no polling/retry loops. Existing runtime worker budgets remain
2 seconds per file, 5 seconds per scan, plus bounded cleanup observation.
These are not hard deadlines for Windows/provider I/O: runner-side metadata
and mutation primitives are synchronous, and cancellation cannot prove kernel
completion. A driver-blocked native operation remains a limitation, not a
successful or safely cancelled test.

## Observed metadata, not inferred sync state

Runtime: 64-bit CPython 3.10.6 on Windows fixed NTFS; package 0.1.0,
MCP SDK 1.30.0, AnyIO 4.15.1, jsonschema 4.26.0, ruamel.yaml 0.18.17.
The runtime dependency check initially failed in the default interpreter, so
declared dependencies were installed in a new isolated session-local environment.
No OneDrive application version or account identifier was queried.

All following times are **UTC, 2026-09-27**. Metadata timestamps precede the
corresponding body/protocol operation; they are not upload-completion times.

| Phase | Directory metadata timestamp | Directory attributes | Directory tag |
| --- | --- | --- | --- |
| Approved parent, non-following metadata | 02:02:25.818680 | `0x00000031` | `0x00000000` |
| Approved parent, verified handle | 02:02:25.826772 | `0x00000031` | `0x00000000` |
| New directory ownership recorded | 02:02:25.835772 | `0x00000010` | `0x00000000` |
| Baseline index | 02:02:27.712120 | `0x00000010` | `0x00000000` |
| Baseline body kst-001 | 02:02:28.038422 | `0x00000010` | `0x00000000` |
| Baseline body kst-002 | 02:02:28.339584 | `0x00000010` | `0x00000000` |
| Baseline body kst-003 | 02:02:28.639190 | `0x00000010` | `0x00000000` |
| Baseline body kst-004 | 02:02:28.976374 | `0x00000010` | `0x00000000` |
| Baseline body kst-005 | 02:02:29.292626 | `0x00000031` | `0x00000000` |
| Before edit | 02:02:29.641928 | `0x00000031` | `0x00000000` |
| Updated index | 02:02:29.731910 | `0x00000031` | `0x00000000` |
| Stale expected version | 02:02:30.086773 | `0x00000031` | `0x00000000` |
| Updated body | 02:02:30.362580 | `0x00000031` | `0x00000000` |
| Before deletion | 02:02:30.683970 | `0x00000031` | `0x00000000` |
| Deleted index | 02:02:30.764511 | `0x00000031` | `0x00000000` |
| Deleted body | 02:02:31.078968 | `0x00000031` | `0x00000000` |
| Restored index | 02:02:31.429543 | `0x00000031` | `0x00000000` |
| Restored body | 02:02:31.788002 | `0x00000031` | `0x00000000` |
| Final baseline after server exit | 02:02:32.341283 | `0x00000031` | `0x00000000` |

**Every source observation after creation** had attributes `0x00000020`
(archive), tag `0x00000000`, both in enumeration and handle observations.
There were 78 source-handle metadata records; the deleted note was absent in
the two deletion phases. No observed source had `PINNED`, `UNPINNED`, `OFFLINE`,
`RECALL_ON_DATA_ACCESS`, or enumeration `RECALL_ON_OPEN` set. Those observations
do not establish the user's **Always keep on this device** setting.

`0x10` is directory; `0x31` is directory + archive + read-only. The directory
attribute change was observed but not attributed to a specific process or sync
operation. An earlier coordinator preflight reported a reparse attribute for
the approved parent; this run's later `lstat` and handle observations both
reported tag zero/no reparse bit. That difference is retained as a limitation,
not used to infer synchronization or stable cloud metadata.

## Protocol results and retained baseline

All tool outputs passed the local-v1 output schema and matched their text/JSON
representations. Every successful index matched the exact expected rendered
corpus and hash; each baseline body matched the original fictional body,
metadata, source byte count and source hash. Every response explicitly reported
`consistency: local-best-effort` and `cloud_freshness: unknown`.

| Call, in order | Response recorded at UTC | SDK call ms | Observed result |
| --- | --- | ---: | --- |
| Baseline index | 02:02:28.019420 | 265 | 5 eligible, 0 excluded |
| Versioned kst-001 | 02:02:28.330584 | 266 | Exact original |
| Versioned kst-002 | 02:02:28.629187 | 266 | Exact original |
| Versioned kst-003 | 02:02:28.963393 | 266 | Exact original |
| Versioned kst-004 | 02:02:29.281625 | 266 | Exact original |
| Versioned kst-005 | 02:02:29.630904 | 297 | Exact original |
| Updated index | 02:02:30.066799 | 281 | 5 eligible; new title, summary and hash |
| Old expected version | 02:02:30.357556 | 218 | Expected `MEMORY_CHANGED`, no body |
| New expected version | 02:02:30.675969 | 266 | Exact edited metadata/body/hash |
| Index after deletion | 02:02:31.061964 | 265 | 4 eligible; kst-001 omitted |
| Deleted kst-001 read | 02:02:31.382540 | 266 | Expected `MEMORY_NOT_FOUND`, no body |
| Index after exclusive recreation | 02:02:31.764998 | 282 | 5 eligible; original index hash |
| Restored versioned kst-001 | 02:02:32.135061 | 266 | Exact original metadata/body/hash |

The sole edited/deleted note was `environment-routing.md` (`kst-001`). The
edit changed its title to `Environment routing pilot revision`, its summary to
`Fictional local pilot metadata revision.`, and appended the fictional body
marker `Fictional local pilot revision two.`. The edit completed at
02:02:29.725056; deletion completed at 02:02:30.760511; exclusive recreation of
the **original**, not edited, content completed at 02:02:31.425561. Other notes
were never mutated after creation. No extra duplicate/invalid fixture was added.

Final retained filenames and full baseline source versions:

| File | ID | Source version |
| --- | --- | --- |
| `environment-routing.md` | `kst-001` | `sha256:f0f0de92c05637c675a6cf3f8a999aa0dcd954e2d9b70242327bb03e82fc437e` |
| `request-latency.md` | `kst-002` | `sha256:cc036418b9cdd6e499750a531b01bb619aa7a8f63fbe26a57bc526163d22df02` |
| `request-traces.md` | `kst-003` | `sha256:0fb44b09ff240659935ddd73b5f1c5e39bff1f2c8bd5d8f86657d2871dd76521` |
| `ingestion-delay.md` | `kst-004` | `sha256:81d21b59c045d1dd010c844c1371f4d225f19467b2e007063831071cdf326f1b` |
| `retention.md` | `kst-005` | `sha256:b3e0ce867ca3000d6fb2345e1716f375b2d6d00d1090216b66ef17fbca9cf628` |

| Version check | Exact version |
| --- | --- |
| Edited kst-001 source | `sha256:171b3d32f26e1c9ab2f9b2df9df4d7c8197898b72ce9e227fe849551fc58b955` |
| Baseline and restored index | `sha256:e1f7cf8431718d297a04cdf1020c343766b2a827f248bdd19a2c3aff531583af` |
| Updated index | `sha256:e028403f39b9bbefee4d6f34277c883962e153e91e6cee8943376a285c6c9640` |
| Index while kst-001 absent | `sha256:eafef4b7915ac81d0e19a7afe18dfd76c466718f364f064bd036c2f723f0e7b3` |

## Lifecycle, private evidence and remaining checks

The [validation-only server observer](../validation/onedrive/observe_server.py)
wrapped launch/job completion to record existing behavior; it did not inject
delays, failures, timeout settings, storage results or cleanup states.
The same observed server process remained alive across all edits and all
13 calls. At 02:02:32.241686 its shutdown record reported code **0** and
`pending: false`; the SDK observed exit **0** at 02:02:32.326282.

All **14** filesystem jobs reported `cleanup_confirmed: true`, `pending: false`,
and observed process exit. Each worker's exit code was **1**, consistent with
the existing supervisor terminating disposable workers after receiving their
result; do not describe these as fourteen natural exit-zero shutdowns.
The sanitized worker ledger follows; every row has exit **1**, cleanup confirmed,
and no pending ownership. `probe` precedes the thirteen tool calls.

| Worker | Operation | Completion recorded at UTC | Decision ms | Including cleanup ms |
| --- | --- | --- | ---: | ---: |
| 1 | probe | 02:02:27.697576 | 219 | 219 |
| 2 | list | 02:02:27.981402 | 218 | 218 |
| 3 | get | 02:02:28.296584 | 219 | 219 |
| 4 | get | 02:02:28.595188 | 219 | 234 |
| 5 | get | 02:02:28.926368 | 235 | 235 |
| 6 | get | 02:02:29.248146 | 219 | 219 |
| 7 | get | 02:02:29.595432 | 250 | 265 |
| 8 | list | 02:02:30.029558 | 234 | 234 |
| 9 | get | 02:02:30.355557 | 218 | 218 |
| 10 | get | 02:02:30.641380 | 219 | 234 |
| 11 | list | 02:02:31.028318 | 218 | 218 |
| 12 | get | 02:02:31.379540 | 266 | 266 |
| 13 | list | 02:02:31.730000 | 250 | 250 |
| 14 | get | 02:02:32.099049 | 234 | 234 |

Worker elapsed observations ranged from 218 to 266 ms. Server stderr was empty.
These observations establish completed process/resource ownership checks for
this run, **not** universal cleanup guarantees, driver-stalled cancellation,
hard real-time response, or synchronization quiescence.

Private evidence is in a newly generated, nonsynchronized session artifact
directory whose exact path was handed to the coordinator, not committed here:

| Artifact | Contents |
| --- | --- |
| `events.jsonl` | Timestamped ownership/write intent, file IDs/hashes, metadata observations, complete SDK results, server exit, final baseline and elapsed time |
| `workers.jsonl` | Worker launches, observed exits, cleanup/pending states and shutdown |
| `config.json` | Only the explicit local project mapping; outside OneDrive |
| `stderr.txt` | Server diagnostics; zero bytes in this run |
| `failure-traceback.txt` | Created only on failure; absent in this successful run |

The committed report contains no personal filesystem paths, account IDs,
credentials, file IDs, volume IDs, or raw private logs.
[Runner tests](../tests/test_onedrive_pilot.py) use newly owned local fixtures,
not OneDrive: explicit gates, existing/ambiguous targets, no overwrite, ledger
before writes, unexpected entries, changed hashes/identities, redirect/unavailable
policy, evidence separation, and the full real-SDK local lifecycle.
Final local-only validation: **22 passed in 14.03 seconds** (14 pilot regressions
and 8 existing client-kit regressions); no live sequence was repeated.
Run only those local regressions with:

```powershell
python -B -m pytest -q tests\test_onedrive_pilot.py tests\test_real_client_kit.py
```

**Minimal next step, user-operated only:** In File Explorer, right-click only
`<approved-OneDrive-test-directory>` and use its OneDrive **View online** command,
if available. In that exact web folder, confirm the five filenames listed above
and preview only `environment-routing.md`: it should have the original
`Environment routing` title and no `Fictional local pilot revision two.` marker.
Report just that folder's visible-file/content result or its displayed
pending/error status, without account identifiers or unrelated screenshots.
If the folder-specific command is unavailable, stop and report that rather
than browse account-wide files or change settings. Web visibility would be a
separate user observation, not retroactive proof of upload during this run.

Leave the five notes and directory intact. No further automated live reads,
mutations, retries, second-device experiments or account/provider checks are
authorized by this result.
