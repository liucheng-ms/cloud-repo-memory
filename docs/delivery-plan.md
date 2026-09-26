# OneDrive memory delivery plan

## Confirmed scope

The user selected the local-first MVP on 2026-09-26: company OneDrive
synchronizes Markdown; each device runs a local, read-only stdio MCP server.
ADR 0002 remains the architecture baseline. The repository currently contains
design, synthetic fixtures, a callable synthetic storage core and a stdio MCP
adapter with synthetic protocol-client evidence, not a verified OneDrive or
coding-agent integration.

The coordinator owns scope, shared contracts, integration, and acceptance.
Use synthetic data until storage, devices, sharing, and agent/model processing
are approved. No tenant administration or credential collection is part of
development.

## Workstreams and dependencies

| Stage | Owner | Deliverable | Exit gate |
| --- | --- | --- | --- |
| 1A: Deployment boundary | Credential/deployment delegate | `onedrive-deployment.md`: credential ownership, local data boundary, setup and two-device pilot | Responsibilities and limitations are explicit; no invented setup commands or completed-test claims |
| 1B: Contract and retrieval | Contract/retrieval delegate | Versioned local schemas, contract explanation, synthetic acceptance cases | Tool behavior, metadata, errors, eligibility and retrieval evidence agree |
| 2: Design integration | Coordinator | Review both deliverables and settle shared assumptions | Contract frozen for implementation; no unresolved blocking design decisions |
| 2A: Windows filesystem feasibility | Bounded technical spike, assigned next | Demonstrate safe local reads, redirect rejection and bounded unavailable-file handling; identify runtime/library choice | No silent hydration or unbounded reads; redirect fixtures pass; actual OneDrive placeholder behavior is separately evidenced or explicitly blocked |
| 3: Local implementation | Implementation session, assigned after stage 2 | Configuration, filesystem adapter, parser, index renderer and stdio MCP tools | Automated success and failure cases pass; no scope escapes or silent partial success |
| 4: Client and sync pilot | Coordinator with user-operated clients/devices | Reproducible client traces and cross-device observations | Two MCP clients retrieve appropriate notes; a controlled update and deletion are observed on a second device |

Stages 1A and 1B run in parallel. Full runtime implementation depends on
stages 2 and 2A; feasibility findings may require revising the design baseline.
Client integration follows a working local server. Do not treat a plausible
answer, a citation, or a self-reported note read as evidence of an MCP call.

## Initial decisions

- OneDrive desktop software owns Microsoft authentication. The MCP server
  does not acquire, store, refresh, or synchronize Microsoft tokens.
- Source Markdown is synchronized; machine-specific configuration and any
  future rebuildable local indexes are not shared knowledge files.
- Start with metadata-derived index discovery followed by project-scoped
  stable-ID body reads. Do not add a database, embeddings, or vector search.
- Keep one editing location and multiple readers. Do not promise atomic
  multi-file updates, immediate cloud freshness, or automatic conflict merges.
- Lifecycle metadata controls visibility, not verified human approval.
  Local project scoping is not a multi-user cloud authorization service.
- Treat memory content as untrusted reference material, not privileged agent
  instructions.

## Acceptance and escalation

The contract workstream must define reproducible local cases for unknown
projects and IDs, malformed metadata, duplicate IDs, unavailable files,
updates and deletion, lifecycle eligibility, and path/symlink/junction escapes.
Conflicts and incomplete reads must not turn into guessed content or an empty
successful result.

Retrieval evaluation records client/model versions, isolated conversations,
tool inputs and results, relevant IDs retrieved, unsupported assertions,
index size, context consumption and latency. Use the existing fictional Kusto
pilot as a starting dataset, not as proof of production readiness.

Proposed performance and quality thresholds require coordinator review before
implementation. If measured metadata scan time, index context size, or missed
relevant notes exceed the agreed budget, evaluate filtering or a rebuildable
local lexical index first. Vector retrieval requires evidence that simpler
retrieval is insufficient and a separate data-processing decision.

Cross-device synchronization has no asserted latency SLA. Record observed
arrival times and separate OneDrive delivery from the server's recognition
of locally available changes. Deletion or revocation cannot be claimed to
erase copies or context already consumed by clients.

## User participation

The coordinator handles repository design, implementation delegation,
integration and automated local checks. User participation is needed for
company policy approval, an already authorized OneDrive environment, selecting
available real MCP clients, and a controlled second-device synchronization
test. Never request passwords or tokens in chat.

Report only verified progress, next actions, blockers/risks, and decisions
requiring user authority. Do not label implementation complete before the
required local checks, or the multi-device solution complete before the pilot.

## Execution status

On 2026-09-26, creation of two isolated child workspaces failed because GitHub
could not be reached during fetch. No work started in those workspaces.
Two bounded delegates delivered disjoint files in the existing worktree.
This is a workspace provisioning limitation, not a OneDrive integration result.

Both design deliverables have now been reviewed and linked from the README.
The credential/deployment document and local contract agree on local-only
freshness, no Microsoft credential handling, explicit failures, and synthetic
validation before real knowledge. Schema/example checks are design evidence
only; no server, real-client or cross-device result has been established.

Coordinator decisions for the v1 design baseline:

- Accept a bounded full scan per call and exact-source version markers, rather
  than introducing cache invalidation or an indexing service prematurely.
- Accept project-wide failure for invalid, duplicate or unavailable candidate
  notes. This sacrifices availability to avoid presenting an incomplete index
  as complete; a failure in one project must not disable other valid projects.
- Keep the specified 200-note ceiling as an explicit initial scope limit.
  Performance/context targets remain provisional, not demonstrated capacity.
- Do not declare the filesystem design implementation-ready until stage 2A.
  OneDrive uses reparse-point mechanisms: rejecting all reparse points can
  reject legitimate notes, while following them blindly can escape scope.
  This is the highest-risk implementation dependency.

The next assignment is a small Windows filesystem feasibility spike, not
parallel implementation of an unproven storage adapter and its consumers.
It must recommend the simplest suitable runtime/library, distinguish mocked
filesystem cases from actual OneDrive observations, and report any need for a
user-operated test without requesting credentials. After this gate, assign
storage/MCP implementation and client/evaluation integration against the same
contract. No real-data rollout is authorized by design completion.

### Stage 2A integration review

The isolated Windows prototype session was provisioned successfully after
network recovery. Its initial deliverable is integrated in this branch; the
coordinator reproduced 36 tests: 29 passed, seven symlink cases were blocked
by privilege error 1314, and none failed. See the
[feasibility findings](windows-filesystem-feasibility.md) for the exact scope.
No real OneDrive files were accessed.

Targeted code review found a worker-ownership gap if reader setup fails after
process launch. The correction is now integrated: ownership is registered before
reader setup, and absent/unstarted readers still undergo bounded cleanup or
retain the unhealthy latch. Constructor/start failure regressions cover real
worker cleanup and repeated-submission refusal under injected unconfirmed exit.
The coordinator reran the corrected suite: 38 tests, 31 passed, seven blocked,
zero failures/errors. The initial passing suite alone did not waive the finding.

The coordinator accepted a contract clarification: 2-second file and 5-second
scan limits are work budgets, not guarantees of kernel-I/O completion. Expired
work cannot publish content. Unconfirmed cleanup after a bounded observation
period latches the supervisor unhealthy without launching replacement workers.
This shared operational fault can block multiple projects; malformed-note
failures remain scoped to the affected project.

Python with standard-library Win32 bindings is the provisional choice for the
synthetic storage step, not a final production runtime/support commitment.
Real OneDrive placeholder/hydration behavior, provider cleanup and the seven
symlink cases remain release gates even after the local corrective work.

### Next delivery: synthetic storage core

The coordinator approves the bounded synthetic-only implementation gate.
Implement project configuration, strict metadata parsing, generated indexes,
version-conditional body reads, sanitized result envelopes and the filesystem
worker integration against the current local v1 contract. Keep the interface
independent of MCP transport so it can be exercised without a real client.
Promote or share proven primitives rather than keeping divergent copies.

The next delivery must include automated contract cases and measured synthetic
corpus results, and preserve the worker-ownership regressions. It must not use
real OneDrive folders, claim full platform conformance, add search/vector
storage, or register clients. Packaging/runtime support and actual stdio MCP
integration follow coordinator review of the storage core. Windows-only NTFS
support and the current sharing-mode restrictions must remain explicit.

### Synthetic storage-core delivery

The bounded callable storage implementation is now available for review; see
[setup, evidence and remaining gates](synthetic-storage-core.md). It is not an
MCP server. Shared Win32 and supervisor primitives replace runtime/prototype
copies, with race/stall injection confined to the validation harness.

The final callable suite reports 223 passed and seven declared platform/pilot
skips. The inherited Windows harness separately retains 31 passing tests and
seven actual symlink-privilege blocks. Stage 2A remains CONDITIONAL GO.
At 100 notes / 1 MiB, the generated index is 43,004 bytes; first scan 594 ms
passes the provisional 1,000-ms target, but 30 subsequent scans have p95
594 ms, missing 500 ms after one bounded parsing optimization (before: 688 ms).
No limit/cache/filesystem policy was weakened to meet the target.
This miss requires coordinator review, not an implicit scope expansion.

Python 3.10.6 remains an experimental development environment. Basic editable/
wheel packaging does not settle production runtime support. Actual MCP clients,
tokenizer results, OneDrive behavior and two-device pilots remain blocked.

Coordinator review subsequently required strict YAML 1.2 Core scalar resolution
and normalization of out-of-range Unicode escape overflow to collected metadata
errors. The corrective delivery records 296 passing contract/parser/fault tests,
the same seven declared skips and the unchanged 31-pass/seven-symlink-block
Windows harness. Separate refreshed parser-source measurement evidence keeps
the 100-note p95 at 594 ms: still a miss, not a changed gate or tuning waiver.

### Storage acceptance and MCP adapter assignment

The coordinator integrated and reviewed both parser corrections, then reproduced
296 passing storage/parser/fault cases with seven declared evidence skips, plus
31 passing Windows cases and seven actual symlink-privilege blocks. The two
reported correctness findings are resolved for the synthetic scope.

Approve a bounded local stdio MCP adapter against this callable core. The
594-ms p95 miss remains open against the unchanged provisional 500-ms target;
it does not block protocol development, but must not be reported as passed.
No additional performance redesign is authorized in the adapter workstream.

The adapter must publish exactly the two read-only tools with the versioned
input/output schemas, validate wire arguments before callable conversion
(including rejecting explicit null where disallowed), and return matching
structured and JSON-text content with correct error flags. Use a maintained MCP
SDK, not a bespoke JSON-RPC stack. Package schemas so installed-wheel operation
does not depend on a repository checkout. Keep stdout protocol-only and
configuration failures explicit on stderr with nonzero exit.

Acceptance for this step requires a real subprocess stdio session through an
MCP protocol client: initialization, discovery, schema checks, successful reads,
argument and domain errors, version/update/deletion behavior, disconnect and
worker ownership/cleanup. Preserve serialized storage access without blocking
protocol shutdown indefinitely. Synthetic protocol-client evidence is not two
real coding-agent integrations or answer-quality evidence.

Do not alter installed client settings or register the server automatically.
Provide reproducible launch/setup instructions with placeholder synthetic paths.
Real-client configuration, tokenizer evaluation, OneDrive files, and the
second-device pilot remain separate, unapproved deployment activities.

### Local stdio adapter delivery

The bounded adapter is implemented and verified for synthetic fixed-NTFS data;
see [setup and exact protocol/packaging evidence](local-stdio-adapter.md).
The maintained official Python MCP SDK 1.30.0 supplies transport, initialization,
typed routing and cancellation. Only the two frozen read-only tools are exposed.
Schema-invalid arguments, including explicit null versions, retain contract
errors; malformed protocol requests and unknown tools remain protocol errors.

Real subprocess SDK ClientSession checks cover discovery, schemas/annotations,
both result representations, failures, edits/deletions, cancellation/EOF and
owned cleanup/recovery. Full suite: 312 passed, seven declared evidence skips.
The retained Windows harness: 31 passed, seven actual symlink privilege blocks.
Direct wheels and wheels rebuilt from sdist pass resource-byte parity and both
launchers in isolated virtual environments and unrelated working directories.
The single normative schema is packaged directly, not manually duplicated.

No performance redesign or new latency claim: the previously measured 100-note
p95 remains 594 ms against the unchanged provisional 500-ms target.
No two coding-agent integrations, tokenizer/answer scoring, real OneDrive,
real-provider cleanup or second-device pilot evidence is implied.

Coordinator protocol review found that the initial adapter terminated on a
malformed transport frame. The separate correction uses nonfatal SDK transport
handling and sanitizes unexpected exceptions at every registered handler,
including discovery and ping. Malformed frames receive SDK protocol diagnostics,
not local-memory envelopes; subsequent ping/tool requests continue. Known-tool
unexpected failures retain the generic contract error envelope. Deliberate
unknown-tool errors and cancellation/EOF ownership behavior are preserved.
Corrected verification: **317 passed, seven declared evidence skips**; Windows
**31 passed, seven actual symlink blocks**. Both external installed-wheel
variants pass again. This is corrective evidence pending coordinator review,
not acceptance of real-client or OneDrive deployment.

### Coordinator acceptance: synthetic local MCP

The coordinator integrated the correction, reviewed the exception boundaries
and nonfatal SDK transport mode, and reran all 44 protocol/supervisor cases
successfully. The initial full suites and both installed-wheel build paths had
also been independently reproduced in the coordinator worktree; the correction
includes the child session's refreshed full-suite and packaging evidence above.

Accept the local synthetic-data storage and stdio prototype for the next
client-evaluation stage, not production or OneDrive conformance. All reviewed
correctness findings have targeted fixes and regression coverage. The unchanged
594-ms latency miss and missing real-device/platform evidence remain open.

Next obtain the user's choice of two coding clients, then prepare isolated
synthetic configuration and a six-case retrieval protocol with actual tool
traces, model/client versions and answer scoring. Do not alter user/global
client settings without approval. Keep evaluator answers out of the clients'
accessible corpus. Tokenizer availability and client force-kill behavior must
be recorded, not inferred from SDK protocol tests.

Only after that stage should an approved dedicated synthetic OneDrive folder
be selected for provider and second-device observations. Never discover or
ingest existing company knowledge to bypass a missing test environment.
