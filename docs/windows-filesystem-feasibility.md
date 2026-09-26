# Windows filesystem feasibility: stage 2A

## Decision and evidence boundary

**Conditional GO for synthetic-only storage implementation, after coordinator
review; NO GO for full OneDrive conformance or real-data rollout.** The small
[executable harness](../validation/windows-filesystem/README.md) establishes
useful local NTFS primitives, not a finished storage adapter or MCP service.
Do not mark stage 2A's real-device conditions passed.

Recommend **Python with standard-library `ctypes` Win32 bindings** for the next
bounded implementation step, provisionally. Python 3.10.6 x64 is already
installed; it exposes the required Windows APIs without a native package,
compiler or dependency installation. Node v24.11.1 is installed but its ordinary
filesystem API does not expose this complete handle/tag/share-mode surface;
a native binding or helper would still be needed. The .NET SDK (`dotnet`) is
not installed. PowerShell 7.6.6 is available for fixture creation.

The tradeoff is explicit ABI definitions, Windows-only code and an isolated
worker/supervisor lifecycle. Generic Python `open`, `Path.resolve`, or a timer
around a blocked thread is insufficient. This is not a commitment to ship
Python 3.10 as the supported production runtime; support lifecycle, packaging,
MCP/YAML dependencies and worker startup overhead still need a separate decision.

Only owned synthetic fixtures were used. Their outside-project sentinel stayed
inside the fixture parent under this worktree. No OneDrive folder/account was
searched; no credentials, company knowledge, cloud reparse points, network
configuration, privileges, ACLs or security settings were changed. Ancestor
handles inspect metadata only; no ancestor directory outside the fixture is
enumerated and no outside-fixture file body is read.

## Reproduction and host

Run from the repository root:

```powershell
python -B validation\windows-filesystem\test_winfs.py
```

Observed on 2026-09-26: Windows 10 build 19045, AMD64, 64-bit CPython 3.10.6,
PowerShell 7.6.6, local fixed-drive **NTFS**. Each root check queries
`GetDriveTypeW` and `GetVolumeInformationW`; non-fixed/non-NTFS roots fail closed.
The suite does not require administrator privileges. Junction creation uses
`pwsh -NoProfile` with `New-Item -ItemType Junction` on exact fixture paths.

Final recorded run after the lifecycle review fix: **38 tests, 31 PASS,
7 skipped/BLOCKED, zero failures/errors, 19.226 seconds**. Test names are the
reproducible evidence identifiers in the matrix below. The seven skips are
actual `os.symlink` failures with WinError
1314, not assumed failures or substitute junction results.

Temporary files and junctions were removed using the exact fixture ledger.
One initial failing regression left empty directories; after inspecting their
exact paths, those named empty directories were removed individually with
`System.IO.Directory.Delete`, without recursion. No fixtures remained.

## What the primitive actually does

1. Reject traversal components, drive-relative/UNC/device roots, path separators
   embedded in names, alternate data streams, DOS device names and ambiguous
   trailing dot/space names. It never expands configuration strings.
2. Open the volume root, each root ancestor and the configured root one component
   at a time using `CreateFileW(OPEN_EXISTING, GENERIC_READ, FILE_SHARE_READ)`.
   Flags are `FILE_FLAG_BACKUP_SEMANTICS | FILE_FLAG_OPEN_REPARSE_POINT |
   FILE_FLAG_OPEN_NO_RECALL`. Hold ancestor handles throughout the operation.
   Backup semantics allows directory handles; no privilege is enabled.
3. Query `GetFileInformationByHandleEx(FileAttributeTagInfo)` and reject name
   surrogates/unknown tags. Query `GetFinalPathNameByHandleW` using normalized
   **volume GUID paths**, then compare each child's exact final parent to the
   pinned parent's final path. This is not string-prefix containment. Subsequent
   opens use the verified volume path, not repeated drive-letter resolution.
   Redirected drive aliases resolving below the volume root are also rejected.
4. Enumerate only under verified pinned directories, keeping those directory
   handles through the inventory recheck. Every entry is checked, even ignored
   files. `os.scandir`/non-following stat supplies enumeration attributes, but
   never supplies the final identity proof: every entry is opened and its
   handle checked before traversal/read.
5. For candidates, compare NTFS volume serial/file ID, link count, byte length,
   last-write/change times, tag and attributes before/after opening and reading.
   Require exactly one hard link. Keep the first handle open during the second
   open and read. Read exact bytes into a bounded buffer; no path-based reopen
   is used to obtain a body after validation. Recheck directory inventories and
   identities before publishing the buffers.

The primitive exposes optional expected root identity for future startup
mapping/recheck integration; the simple supervisor demo does not implement
persistent project configuration. The whole adapter must still wire that in.
NTFS 64-bit file IDs are used deliberately; ReFS/other filesystem support is
not inferred. Alternate short-name aliases may be conservatively refused.

### The important failed first approach

The first run used **FILE_READ_ATTRIBUTES-only** handles with the same sharing
flags. A root directory rename unexpectedly succeeded on this host. Therefore
attribute-only metadata handles are **not sufficient namespace pins**. Merely
adding `OPEN_REPARSE_POINT` to a whole path is also insufficient for ancestor
redirects.

The final primitive uses real read/list access. Permanent regressions attempt
root and ancestor renames while pinned, attempt a nested-directory rename and
replacement with an outside junction, and attempt source replacement with an
outside sentinel both after inventory and between the two opens. The final
tests demonstrate denial or identity-change refusal, never sentinel output.
Same-size/mtime replacement between observations also fails before `ReadFile`.
Windows returned access-denied/sharing-violation errors, not always error 32;
tests accept the explicit relevant denial codes rather than assuming one.

**Cost:** `GENERIC_READ` requires directory list/read-attributes/read-EA,
read-control and synchronize permissions, and data-read permission for files.
The spike requires this even for ancestors and ignored regular entries. This
is more restrictive than traversal-only permissions or checking ignored files'
attributes. It can reject otherwise navigable trees and temporarily conflict
with editors/sync. A preexisting writer gives explicit WinError 32; the worker
returns failure, not a partial index. Actual ACL-denial cases were not induced.
No fallback to weak attribute-only handles is permitted. Narrowing rights
without losing the demonstrated namespace pinning requires new regression
evidence. This is a scope/availability tradeoff to review before shipping.

## Property matrix

PASS means the stated bounded synthetic property, not generalized OneDrive
validation. Policy-only tests are identified explicitly.

| Property | Status | Evidence and limit |
| --- | --- | --- |
| Ordinary source read, exact BOM/CRLF bytes, final volume path and file ID | PASS | `regular_exact_bytes_and_identity`; handle ID equals synthetic file stat ID; exact bytes returned |
| Hidden recursion, `.MD`, root `MEMORY.md` exclusion, nested `MEMORY.md` inclusion | PASS | `candidate_selection_hidden_nested_uppercase` |
| Traversal, streams, device/absolute input, invalid root syntax | PASS | `traversal_stream_device_and_absolute_paths`, `invalid_roots`; no `ReadFile` call |
| Final-parent comparison does not accept prefix siblings | PASS | `final_parent_check_rejects_prefix_sibling`; injected wrong final-path result is a **policy test**, plus real handle paths in normal tests |
| Directory junction inside/outside root | PASS | `junction_inside`, `junction_outside`; no source reads |
| Root and ancestor junction redirects | PASS | `root_junction`, `ancestor_junction`; no source reads |
| File symlink inside/outside root | BLOCKED | `file_symlink_inside`, `file_symlink_outside`: privilege error 1314 |
| Directory/root/ancestor symlinks | BLOCKED | `directory_symlink_outside`, `root_symlink`, `ancestor_symlink`: error 1314 |
| Ignored file symlink, source replaced by symlink before read | BLOCKED | `ignored_redirect_is_not_silently_skipped`, `file_replaced_with_symlink_before_read`: error 1314 |
| Candidate hard links, both inside and outside project | PASS | `hardlink_outside_and_inside`; multiple links rejected before source read |
| Root/ancestor rename while pinned | PASS | `root_and_ancestor_rename_denied_while_pinned`; regression for the attribute-only failure |
| Pinned nested directory cannot be replaced with outside junction | PASS | `pinned_directory_cannot_be_replaced_by_outside_junction`; rename denied, original note returned, no sentinel |
| Unsafe source replacement after inventory/before data open | PASS | `scan_replacement_outside_sentinel_denied_or_detected`, `replacement_before_data_open_denied`; original bytes only or explicit failure |
| Same-size/mtime source replacement; root replacement across calls | PASS | `same_size_mtime_replacement_detected_before_read`, `root_identity_change_between_calls`; identity mismatch, no source read |
| Detected addition/deletion/edit during scan | PASS | `end_inventory_add_delete_edit`; no successful partial result |
| Preexisting source writer | PASS | `preexisting_writer_fails_closed`; sharing failure, not silent skipping |
| Inclusive 262,144-byte file, 200 notes, 2,000 entries, depth 16, 16,777,216-byte aggregate and one-over failures | PASS | Five `inclusive_*` tests use actual thresholds, not smaller proxies; no claim these maxima meet the 5-second supervised budget |
| Cloud versus redirect/unknown tag classification | PASS | `tag_policy_only_not_cloud_validation`: **integer policy tests only**, no synthetic cloud reparse points |
| Real locally available/pinned OneDrive placeholders | BLOCKED | No provider files opened; flags and tag acceptance alone do not establish readable local bytes |
| Real offline, partial hydration, recall-on-open and unavailable provider behavior | BLOCKED | No real provider I/O tested; no no-hydration guarantee inferred |
| Ordinary supervised scan | PASS | `supervised_normal_scan`; exact expected SHA-256/length and confirmed worker exit |
| 2-second file and 5-second scan synthetic stalls | PASS | `synthetic_file_and_scan_stalls_cleanup_and_recovery`; real pinned handles plus synthetic sleep, worker terminated, file writable afterward |
| Reject late successful result | PASS | `late_success_discarded`; injected expired operation timestamp followed by a success message, no files published |
| Cleanup-pending stops additional workers | PASS | `cleanup_pending_latches_without_respawn`: **policy mock**, 100 rejected calls and zero subprocess launches |
| Reader construction/start failure does not abandon workers | PASS | `reader_initialization_failure_cleans_real_workers_before_retry`: injected failure at each point, three actual workers per point exited/pipe closed before retry; normal job then succeeds |
| Reader initialization failure with unconfirmed exit retains ownership | PASS | `reader_initialization_failure_retains_unconfirmed_worker`: **policy mock** at both failure points, one launch/terminate/wait, 100 additional refusals without respawn, successful reaping after exit confirmation |
| No repeated-job resource growth on normal exit | PASS | `repeated_jobs_do_not_accumulate_resources`; 10 jobs, parent handles 145 before/145 after, one thread before/after |
| Driver-stalled worker exit, hard real-time response/cleanup | BLOCKED | Windows cannot guarantee cancellation/exit latency; synthetic sleeps are not provider/kernel stalls |
| Other filesystems, volume-mount fixtures, ACL denial, case-sensitive NTFS directories, mapped-file writers | BLOCKED | Not exercised; no platform-wide or hostile same-user guarantee |

## Cloud semantics: allowed classification is not validation

The policy recognizes only `IO_REPARSE_TAG_CLOUD` and its sixteen documented
family variants (`tag & ~0x0000F000 == 0x9000001A`) as potential nonredirecting
cloud entries. Name-surrogate tags, junction/symlink tags, legacy/unknown tags
fail closed. It does **not** reject every reparse attribute. Recognized cloud
tags still require the same final-handle and identity checks.

`OFFLINE` and `RECALL_ON_DATA_ACCESS` cause explicit unavailability.
`RECALL_ON_OPEN` is interpreted only in enumeration metadata: its bit overlaps
the handle-level extended-attributes bit, so treating every handle with
`0x40000` as remote would incorrectly reject ordinary files. Pin intent is
not proof of complete hydration.

There is no explicit hydration API call. `OPEN_NO_RECALL` expresses intent,
not a verified OneDrive guarantee. In particular, read/list access is requested
before the handle's tag/availability can be inspected. Metadata access, directory
enumeration, open or read may still involve provider work. Whether
`OPEN_REPARSE_POINT` handles can read all supported locally available OneDrive
variants, and whether more cloud API checks are needed, remains **BLOCKED**.
Do not silently drop this flag, follow an unvalidated cloud path, or call this
integer-policy exercise real Files On-Demand testing.

## Deadlines, cancellation and ownership

The parent uses monotonic time and waits for worker messages independently of
the worker's filesystem call. A 5-second budget starts before worker launch;
each source read's 2-second budget includes its open/read/check operations.
Enumeration/ancestor work is also contained by the whole-job budget.
The file-start event carries the worker's monotonic timestamp, so delayed IPC
does not restart the budget. The parent rejects messages after the applicable
budget, including queued successes.

On timeout it requests termination of **that exact subprocess** (Windows
`TerminateProcess`), then observes process exit and reader-thread completion
within a shared 500-ms cleanup budget. No unconditional `wait`/`join` follows.
If either is unconfirmed, it retains the process object/handle/PID, pipe and
reader ownership, returns `INTERNAL_ERROR` with prototype-local
`supervisor_state: "cleanup-pending"`, and refuses further jobs. It only clears
the latch after that same process and reader are confirmed finished. No
replacement worker, orphan-and-respawn loop or unlimited abandoned workers.
Ownership is registered immediately after process launch, before reader
construction/start; both operations are inside the cleanup-protected region.
Their resource failures produce an explicit `INTERNAL_ERROR` with prototype-local
`supervisor_state: "reader-unavailable"` when cleanup succeeds, or
`"cleanup-pending"` when it does not. Reaping permits an absent or unstarted
reader and never joins a thread that has not started.
The prototype is synchronous/single-caller; future MCP dispatch must serialize
jobs rather than concurrently call this supervisor.

Coordinator review found the original implementation registered ownership only
after `Thread.start`, allowing initialization failure to abandon a launched
worker. This was fixed before gate approval. The focused four-test lifecycle
run passed in 2.095 seconds; the complete updated run is recorded above.
The new regressions inject both constructor and start failures, verify six
actual worker exits/closed pipes across safe retries, and separately mock
unconfirmed exit to verify the no-respawn latch and eventual cleanup. Those
mocks remain distinct from real driver-stall evidence.

Final run measurements (milliseconds, not SLAs):

| Case | Failure/success decision from job start | Return including cleanup | Exit/resources confirmed |
| --- | ---: | ---: | --- |
| Ordinary one-note job | 156 | 156 | Yes |
| Synthetic file stall, first | 2,172 | 2,172 | Yes; `FILE_UNAVAILABLE` |
| Synthetic file stall, second | 2,156 | 2,156 | Yes; `FILE_UNAVAILABLE` |
| Synthetic whole-scan stall | 5,016 | 5,016 | Yes; `LIMIT_EXCEEDED` |

The file-stall numbers include approximately 156-172 ms of worker startup
before the file operation begins. The observed 5,016-ms scan decision itself
demonstrates why this is not an exact 5,000-ms response guarantee. Timer
granularity, scheduling, launch and IPC latency matter. Cancellation request,
failure decision, worker exit and resources released are separate observations.
The tests permit 1.5 seconds of host-observation tolerance; this tolerance is
not a proposed contract limit.

Microsoft explicitly states that driver support/state determine whether I/O
can be cancelled, and `TerminateProcess` cannot complete exit until pending I/O
completes or cancels. No user-mode timer or process-isolation trick proves a
hard kernel-I/O completion deadline. No real blocked provider operation was
created in this work.

### Minimal contract clarification proposed to the coordinator

No shared contract/schema/plan was edited. The coordinator accepted the
following direction for the spike, **not as production conformance**:

> Treat 2,000 ms per file and 5,000 ms per scan as monotonic work budgets.
> On observed expiry, do not publish any partial or late successful result;
> request cancellation/termination of the isolated filesystem worker. These
> budgets are not hard real-time response or kernel-I/O-completion guarantees.
> Observe cleanup for at most a further 500 ms, subject to OS scheduling. If
> worker exit or resource release remains unconfirmed, retain ownership of the
> exact worker and mark the supervisor unhealthy. Reject further filesystem
> jobs until that worker is confirmed exited and its owned resources released;
> never automatically replace an unconfirmed worker. Surface an explicit
> cleanup-pending operational fault.

Smallest error/schema change: **none required** if `INTERNAL_ERROR` and an
existing generic diagnostic message such as "Filesystem worker cleanup is
pending; new reads are disabled." represent the fault with `scan_complete:
false`. Keep PID/paths/OS exception details out of tool output; record safe local
operational evidence on stderr. Confirmed timeout cleanup can retain
`FILE_UNAVAILABLE` (file) or `LIMIT_EXCEEDED` (scan). The prototype's extra fields
are internal measurement output, not proposed additions to the frozen schema.

## Remaining implementation and user-operated gates

Full storage implementation may begin **only conditionally with synthetic data**
and the coordinator's accepted deadline clarification. Preserve the seven skips
as an unresolved release gate. The next implementation still owes configured
project/root identity management, all contract metadata/YAML handling,
project-wide error collection/precedence, sanitized envelopes, performance
evidence and MCP transport. This spike intentionally aborts immediately on
errors; it is not the complete error-collection contract.

Before OneDrive support or rollout is claimed, obtain approved test devices and
use a dedicated fictional corpus, not company knowledge:

- Rerun all seven symlink cases on an already authorized environment where
  symlink creation is permitted, without bypassing policy.
- Observe actual tags, attributes, final handles/identities and exact local
  hashes for pinned/fully local files and directories. Confirm read/list rights
  and sharing modes work with the approved OneDrive client during sync/edits.
- Exercise online-only, partially local, offline and unavailable synthetic
  files through supported OneDrive controls. Observe download/provider activity,
  response timing, cancellation request, actual worker exit and cleanup, then
  recovery. Do not equate an OS sharing error with Files On-Demand failure.
- Verify no late bytes, no repeated-job resource growth, and the cleanup-pending
  latch under any real provider stalls that can be safely produced. Unconfirmed
  cleanup is a failed/blocked pilot result, not permission to respawn endlessly.
- Record Windows/OneDrive/runtime versions, intended ACL boundary and any
  unsupported filesystem behavior. Run the separate two-device/two-client pilot
  only after the MCP implementation exists.

## Official API references

Retrieved 2026-09-26; these support API interpretation, not real-device results:

1. [CreateFileW](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew):
   access/share restrictions, directory handles, `OPEN_REPARSE_POINT` and
   `OPEN_NO_RECALL`.
2. [GetFinalPathNameByHandleW](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-getfinalpathnamebyhandlew):
   normalized final paths and volume GUID naming.
3. [GetFileInformationByHandle](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-getfileinformationbyhandle):
   volume serial/file index identity.
4. [FILE_ATTRIBUTE_TAG_INFO](https://learn.microsoft.com/en-us/windows/win32/api/winbase/ns-winbase-file_attribute_tag_info)
   and [reparse tags](https://learn.microsoft.com/en-us/windows/win32/fileio/reparse-point-tags):
   handle tag queries, name-surrogate bit and cloud tag family.
5. [File attribute constants](https://learn.microsoft.com/en-us/windows/win32/fileio/file-attribute-constants):
   offline/recall semantics and enumeration-only `RECALL_ON_OPEN`.
6. [Canceling pending I/O](https://learn.microsoft.com/en-us/windows/win32/fileio/canceling-pending-i-o-operations)
   and [TerminateProcess](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-terminateprocess):
   driver-dependent cancellation, asynchronous termination and pending-I/O exit
   constraints.
