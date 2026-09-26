# Local memory MVP contract v1

Status: specified; synthetic-only storage and stdio transport are implemented
and exercised as documented in [storage-core evidence](synthetic-storage-core.md)
and [protocol-client evidence](local-stdio-adapter.md). Actual coding-agent
integrations, OneDrive and full platform conformance remain unverified.
This contract implements
the design boundary in [ADR 0002](adr/0002-onedrive-local-memory.md), not the
historical M0 interface in [mcp-tools.md](mcp-tools.md). The M0 manifest, corpus,
and existing Kusto fixtures remain unchanged.

## Normative artifacts and scope

- [JSON Schema](../contracts/local-mvp-v1.schema.json): Draft 2020-12; select
  named `$defs` below. The root accepts the supported document shapes.
- [Acceptance specification](../validation/local-mvp-acceptance.json):
  synthetic examples and runtime/evaluation specifications, not executed results.
  Separate storage-core evidence records the executed subset without changing
  this specification or its limits.
- This document supplies filesystem, rendering, and cross-field rules that JSON
  Schema cannot express. Both artifacts are required for conformance.

Only `list_memory_index` and `get_memory` exist, over a per-device stdio MCP
server. No search, mutation, database, embeddings, Graph access, HTTP service,
automatic repository resolution, or cloud synchronization operation is implied.
Both tools advertise `readOnlyHint: true`, `destructiveHint: false`,
`idempotentHint: true`, and `openWorldHint: false`. Repeated reads can observe
different local files; idempotence is not repeatability.

## Local configuration and identity

Use `$defs/configuration`, stored outside the synchronized knowledge root:

```json
{
  "schema_version": 1,
  "projects": [
    {
      "project": "sample-telemetry",
      "root": "C:\\Users\\Example\\OneDrive - Example\\Memory\\sample-telemetry"
    }
  ]
}
```

Project keys and memory IDs are case-sensitive lowercase ASCII slugs, 1–64
characters: letters/digits separated by single hyphens. Identity is the tuple
`(project, id)`, not a filename. Preserve IDs across renames and body edits;
curators must not reuse retired IDs for unrelated topics. No registry proves
this discipline. Different projects may use the same ID.

Roots must be absolute local filesystem directories (Windows drive-qualified
paths or platform-native absolute paths), with no expansion of environment
variables, shell expressions, URL schemes, UNC/network or device paths. Reject
relative roots, duplicate project keys, equal roots, and ancestor/descendant
overlap after filesystem identity/case normalization. Invalid configuration
prevents server startup with a local stderr diagnostic; do not expose a partly
loaded mapping. A configured but temporarily missing root does not invalidate
other mappings; its calls fail `PROJECT_UNAVAILABLE`. Recheck root identity and
containment per call. Configuration changes require restart in v1.

Mappings are operator choices, not verified Git identity or authorization.
Unknown projects fail without accessing another project's directory. Tool
inputs never accept filesystem paths or remote URLs.

## Markdown source format

Each candidate is a strict UTF-8 Markdown file, optionally with one UTF-8 BOM,
starting with a line containing exactly `---`, followed by a YAML 1.2 mapping
and another `---` line. LF and CRLF are accepted. The closing delimiter's line
ending separates metadata from the body. Return all text following it as
`body_markdown` without trimming or normalizing line endings. An empty body is
valid. Source hashing includes original bytes, BOM, delimiters and line endings.

Validate the parsed mapping against `$defs/frontmatter`:

```yaml
---
schema_version: 1
id: kst-001
project: sample-telemetry
title: Environment routing
summary: Fictional production and staging query destinations and scope rules.
read_when: Choosing a cluster alias and database for an investigation.
status: active
approval: approved
---
# Environment routing
```

All nine fields are required, without defaults or string coercion.
`schema_version` is integer 1; all others are strings. Title is 1–120 Unicode
code points; summary/read_when are 1–280 each. Text must contain non-whitespace
content, have no leading/trailing whitespace, and contain no C0/DEL controls,
CR/LF, or Unicode line/paragraph separators. Leading/trailing whitespace rules require
semantic validation beyond the schema. Quote YAML scalars when needed.
Reject duplicate keys, nested structures, aliases, anchors, merge keys, custom
tags, extra fields, invalid UTF-8, missing delimiters, and unsupported versions.
No implicit dates or other scalar conversions are allowed.

`status` is `draft | active | archived | superseded`; `approval` is
`pending | approved | rejected`. Only **active AND approved** is eligible for
either tool. Other valid combinations are excluded from the index and cannot
be read through `get_memory`. Unknown values or missing fields are errors, not
ineligible defaults. `project` must equal the configured project even for
ineligible notes. These editable fields do not attest to human approval.

Enumerate recursively, including hidden directories/files, all regular files
whose extension equals `.md` case-insensitively. Ignore non-Markdown regular
files and the root-level `MEMORY.md` (case-insensitive), which is a reserved
derived-index filename, never authoritative. Nested `MEMORY.md` is a candidate.
The only index exclusion besides that reserved file is valid lifecycle
ineligibility, counted in `excluded_count`.

Validate all candidates before publishing any success, including ineligible
notes. Duplicate IDs anywhere in one project, including ineligible notes and
OneDrive conflict copies, fail the entire call. Never pick a winner by filename,
mtime, directory order, approval or apparent recency.

## Filesystem boundary and bounded scans

Every call performs a fresh, bounded local scan. V1 has no persistent metadata
cache; listing hashes source bytes but extracts index content only from
frontmatter, never inferred headings or body summaries. `get_memory` scans the
same candidate set so duplicate/invalid files cannot bypass validation by ID.
An unrelated broken note therefore blocks the entire project: intentional
fail-closed simplicity, not a resilient large-corpus design.

Check the root and ancestors, every enumerated entry, and opened handles.
Reject redirecting symlinks, junctions and mount/reparse redirects, even when
they currently resolve inside the root; never traverse them or use
string-prefix-only containment checks. Reject detected hard-linked candidate
files with multiple links. Unknown reparse semantics fail closed. OneDrive
cloud-placeholder tags that do not redirect paths may be supported only with
verified final-handle containment and a locally available file. Do not blanket
reject every reparse tag, which would reject normal OneDrive files. Do not
explicitly request downloads/hydration. If an OS provider still initiates
hydration on open, enforce the read deadline and report unavailability rather
than waiting indefinitely.

Implement handle-based no-follow/identity checks around reads and enumeration;
recheck opened target containment and file identity. An unsafe replacement
detected during opening fails before returning bytes. Platforms where these
checks cannot be implemented must not claim conformance. This is a local
scope boundary against accidental escapes, not a sandbox against an
administrator or a malicious same-user process able to rewrite configuration.

Normative v1 ceilings (not performance achievements):

| Resource per call | Limit | Failure |
| --- | ---: | --- |
| Enumerated child entries, including ignored files/directories | 2,000 | `LIMIT_EXCEEDED` |
| Directory depth below root (root = 0) | 16 | `LIMIT_EXCEEDED` |
| Markdown candidates including ineligible | 200 | `LIMIT_EXCEEDED` |
| Bytes per source file | 262,144 | `LIMIT_EXCEEDED` |
| Frontmatter bytes including delimiter lines/BOM | 8,192 | `LIMIT_EXCEEDED` |
| Aggregate source bytes read | 16,777,216 | `LIMIT_EXCEEDED` |
| Rendered index UTF-8 bytes | 131,072 | `LIMIT_EXCEEDED` |
| One file open/read work budget | 2,000 ms | `FILE_UNAVAILABLE` |
| Entire scan work budget | 5,000 ms | `LIMIT_EXCEEDED` |
| Returned diagnostics | 20 | See explicit truncation below |

Bounds apply while reading/enumerating, not just after allocation. Equality is
allowed. Never skip an oversized, unreadable, or out-of-scope candidate, truncate
the directory, silently return a prefix, or turn an incomplete scan into empty
success. No pagination, caller limits, or server retries in v1.

### Work expiry and worker ownership

The time limits above are monotonic work budgets, not hard real-time response
or kernel-I/O-completion guarantees. Start the scan budget before launching
the filesystem worker; include open/read/validation in each file budget.
Delayed IPC must not restart a budget. On observed expiry, discard partial or
late successful results and request cancellation/termination of that exact
worker. OS scheduling, process launch, and message delivery can delay observation
and the caller's response.

Observe worker exit and owned-resource cleanup for at most a further 500 ms,
subject to OS scheduling. Confirmed cleanup preserves the timeout error above.
If cleanup is unconfirmed, retain ownership of the exact process and its
resources, mark the supervisor unhealthy, and return `INTERNAL_ERROR` with
`scan_complete: false` and a generic cleanup-pending diagnostic. Do not expose
PIDs, paths, raw exceptions, or prototype measurement fields in tool output.
Do not publish a successful response while cleanup remains unconfirmed.

Reject further filesystem jobs until that worker has exited and its owned
resources have been released. Never launch a replacement for an unconfirmed
worker. Register ownership immediately after launch, before reader-thread or
IPC setup; setup failures also require cleanup or the unhealthy latch.
Serialize jobs through a shared supervisor. An unhealthy shared supervisor can
temporarily block every project; this explicit operational fault is distinct
from a malformed note, which only invalidates its own project's scan.

The [Windows feasibility findings](windows-filesystem-feasibility.md) explain
the API limitation and synthetic evidence. Real provider cancellation, cleanup
and no-hydration behavior remain unverified; these requirements do not assert
that stage 2A established OneDrive conformance.

## Tools and envelopes

| Tool | Input schema | Output schema |
| --- | --- | --- |
| `list_memory_index` | `$defs/listMemoryIndexInput` | `$defs/listMemoryIndexOutput` |
| `get_memory` | `$defs/getMemoryInput` | `$defs/getMemoryOutput` |

Reject extra input properties. MCP `tools/call` returns the output object in
`structuredContent` and one `content` text block containing its JSON encoding
for clients without structured-content support. Set `isError` to `!ok`.
Consumers use one representation, not both. Malformed MCP protocol envelopes
remain protocol errors; schema-invalid tool arguments return `INVALID_ARGUMENT`
when dispatch reaches the tool. Stdout contains only MCP traffic; local
operational logs go to stderr. Tool outputs contain no absolute or relative
filesystem paths, raw exception text, credentials, or echoed invalid values.

### `list_memory_index`

Input: `{"project":"sample-telemetry"}`. On success, return the project, Markdown
directory, eligible `entry_count`, valid ineligible `excluded_count`, byte
length, index version, contract version, and observation envelope.

Sort entries by ID ascending using ASCII ordinal order. Render UTF-8 with LF
line endings and a final LF, using exactly:

```text
# Memory index: {project}

Read relevant bodies with get_memory; summaries are navigation only.

- **{id}** — {title}
  Summary: {summary}
  Read when: {read_when}
  Version: {source_version}
```

Repeat the four entry lines without blank separators. For zero entries replace
the entry lines with `No eligible memories.\n`. Render metadata text literally:
first replace `&`, `<`, `>` with `&amp;`, `&lt;`, `&gt;`, then backslash-escape
each original Markdown punctuation character in the set
`` \ ` * _ { } [ ] ( ) # + - . ! | ``. Do not escape newly inserted entity
characters. Never create links from metadata. IDs, project and versions need
no escaping. Metadata and bodies remain untrusted data, not agent instructions.

`source_version = "sha256:" + lowercase SHA-256 hex of exact source bytes`.
The entry version covers body-only edits too, without exposing the body.
`index_version` uses the same hash convention over exact rendered index bytes;
timestamps are outside that hash. An excluded-note-only edit can leave this
version unchanged: it identifies the rendered directory, not all project state.
Unchanged input bytes/eligibility produce identical index bytes/version,
regardless of scan enumeration order or local timestamps.

### `get_memory`

Input: `{"project":"sample-telemetry","memory_id":"kst-001"}`. The optional
`expected_version` is the source version copied from the directory or a prior
body read. After a successful full scan, locate the unique ID and recheck
eligibility. Missing IDs return `MEMORY_NOT_FOUND`; ineligible IDs return
`MEMORY_INELIGIBLE`, with no body.

If supplied, a different expected source version returns `MEMORY_CHANGED`,
with no new or stale body. The caller must relist and reconsider. Without a
precondition, return the currently observed body/version, which may differ from
the earlier index. A successful response's `metadata.id` and `metadata.project`
must equal `memory_id` and `project`; metadata, body, byte count and hash must
come from the same read buffer. No second independent read after validation.

The full note is represented by parsed `metadata` plus `body_markdown`, not a
second raw-file copy. The raw-byte version is a correlation marker, not a
globally ordered revision, lock, durable audit record or freshness proof.

## Errors and diagnostics

All failures have `ok: false`, `contract_version: "local-mvp-v1"`, `observation`
and `error`; never a partial directory/body. Error messages are bounded generic
operator guidance. Diagnostics optionally include only a validated memory ID
and known field name. More detailed safe local paths may be logged to stderr.

| Code | Meaning/recovery |
| --- | --- |
| `INVALID_ARGUMENT` | Wrong type, unsupported field, malformed project/ID/hash; fix arguments. |
| `UNKNOWN_PROJECT` | Valid key absent from configuration; configure explicitly. |
| `PROJECT_UNAVAILABLE` | Configured root missing, not a directory or inaccessible; restore locally. |
| `INVALID_METADATA` | Invalid encoding/frontmatter, schema failure or project mismatch; fix source. |
| `DUPLICATE_ID` | Multiple candidates with same valid ID; reconcile files manually. |
| `FILE_UNAVAILABLE` | Enumerated file cannot be opened/read, offline or timed out; make available. |
| `SCOPE_VIOLATION` | Redirect/link/handle containment violation; correct layout safely. |
| `LIMIT_EXCEEDED` | A hard ceiling would be exceeded; reduce corpus or revise contract. |
| `LOCAL_CHANGE_DETECTED` | Identity, stat or directory inventory changed during the scan; retry later. |
| `MEMORY_NOT_FOUND` | Completed valid scan lacks ID; relist, never fall back across projects. |
| `MEMORY_INELIGIBLE` | Unique note exists but lifecycle disallows serving; no body. |
| `MEMORY_CHANGED` | Eligible current note differs from expected version; relist. |
| `INTERNAL_ERROR` | Unexpected failure or unconfirmed worker cleanup; sanitized diagnostic, no partial data. Cleanup-pending blocks new jobs until owned resources are released. |

Precedence: validate arguments, resolve mapping, check root, scan, then perform
ID lookup/eligibility/version checks. During a scan, hard limits, scope failure
or detected change abort immediately with `scan_complete: false`; first observed
abort wins. Otherwise collect metadata, duplicate and availability diagnostics
and fail after the attempted traversal. `scan_complete` means all candidates
were validated and inventories checked; it is false if any file was unreadable
or unparseable, not merely when traversal stopped.

For collected errors choose the first code in this order: `FILE_UNAVAILABLE`,
`INVALID_METADATA`, `DUPLICATE_ID`. Order diagnostics by code, valid memory ID
(missing first), then field (missing first), then message using ordinal order.
Keep identical occurrences, return at most 20, and set `diagnostics_omitted` to
the number of *observed* diagnostics left out. An aborted scan may have
unobserved problems; zero omitted never asserts a clean remainder.
Lookup/precondition failures have `scan_complete: true`; errors before a scan
have false. Successful responses imply a complete scan and have no diagnostics.

## Concurrent edits and observable freshness

Record UTC RFC 3339 `started_at`/`finished_at` and nonnegative monotonic
`elapsed_ms` for every call, successful or not. Always report
`consistency: "local-best-effort"` and `cloud_freshness: "unknown"`.
Wall-clock corrections may reverse the timestamp order; elapsed time does not
derive from subtracting those timestamps.

Compare per-file identity, length and high-resolution local modification
metadata before/after reading, and recheck candidate inventory/identities at
the end of the scan. A detected concurrent edit/delete/add/rename invalidates
the call with `LOCAL_CHANGE_DETECTED`. If a file is enumerated but fails to open
and disappearance cannot be confirmed, use `FILE_UNAVAILABLE`. An already
deleted note absent before the next scan yields `MEMORY_NOT_FOUND`. Changing
lifecycle between calls yields `MEMORY_INELIGIBLE`, even with expected_version.
The same ID after renaming the file without changing its ID still resolves.

These checks are not atomic snapshots and cannot detect every race or
same-stat rewrite. Changes immediately after validation remain possible.
Never claim cross-file consistency, cross-device ordering, cloud completeness,
or absence of a newer OneDrive version. No fallback to last-good cache on errors.

## Acceptance and provisional measurement gates

Adapt fixtures only in a separate synthetic runtime test workspace: copy the
five Kusto topic bodies unchanged, preserve IDs, replace `repository` with
`project`, add `schema_version`, `title`, `summary`, `read_when` using the
acceptance overlay. Do not modify historical fixture files or ingest evaluator
files. Do not copy the hand-maintained index as a source note.

Run every contract case in the acceptance artifact. Its `schema_examples` are
machine-checkable now; scenario expectations require a future implementation
and filesystem test harness. Schema validation alone cannot test YAML safety,
hashes, byte limits, filesystem containment, races or actual MCP transport.

Run the existing six Kusto evaluation cases in fresh sessions for each of two
MCP clients, same model/settings where possible. Record index call, selected
IDs, successful body reads with matching versions, errors/retries, and final
answer citations. All required IDs must be successfully read after discovery;
all required facts must appear; no forbidden claim may appear. An answer alone
is not evidence of retrieval. Missing trace evidence is **unverified**, not pass.
For unknown topics require index discovery and explicit absence/clarification,
never invented project facts; irrelevant body reads are measured separately.

Provisional targets, **not achieved or calibrated**:

- All six retrieval cases pass per client (including all required-ID reads);
  zero fabricated project facts; unknown-topic case invents no Redis details.
- At five notes: directory <= 2,048 UTF-8 bytes; at 100 notes with 60-character
  titles and 120-character summary/read_when: directory <= 48 KiB and <= 12,000
  tokens using the recorded client's tokenizer. Record actual bytes and tokens;
  unavailable tokenizer results are unknown, not estimated passes.
- Fully local 100-note/1 MiB corpus: cold first index <= 1,000 ms; 30 subsequent
  scans p95 <= 500 ms on the recorded device. No runtime cache assumption.
  Measure server monotonic elapsed and client round-trip time separately.
  Also record 5- and 200-note results and the limit-exceeding failure.

Failure of a performance/context target triggers a scope review; it does not
authorize silent truncation or adding search/database features. Fail-closed
project scans, body-byte hashing and repeated full scans deliberately trade
availability/latency for a small inspectable v1. Platform-specific safe handles
and OneDrive placeholder behavior are implementation blockers until tested.
