# OneDrive local memory: deployment boundary and pilot runbook

## Status and scope

This is a **proposed deployment and manual acceptance runbook**, not an installed
service or a completed two-device test. Follow [ADR 0002](adr/0002-onedrive-local-memory.md):
company OneDrive synchronizes Markdown; a read-only stdio MCP server on each
device reads that device's local copy. There is no shared cloud MCP endpoint.

The repository does not yet implement that runtime. Configuration syntax,
installation packages, server launch commands, and supported client setup must
come from the implementation; none are specified here. Storage preparation and
synthetic file-sync checks can precede implementation. MCP checks cannot.

The earlier [synthetic baseline](../validation/samples/kusto-memory/baseline-results.md)
does not establish MCP retrieval, synchronization, or production readiness.

## Ownership and trust boundaries

| Boundary | Owner and operating rule |
| --- | --- |
| Company identity and cloud authorization | Company identity/storage administrators approve accounts, sharing and access policy. Use the approved company account, not a personal OneDrive account. |
| Login and token lifecycle | The desktop OneDrive application and company identity infrastructure own sign-in, authentication challenges, token acquisition/refresh and sign-out. Use their supported UI and company support process. |
| MCP credentials | The proposed server only reads local files. It must not request, extract, collect, store, log or synchronize OneDrive passwords, cookies, access tokens or refresh tokens; it does not implement OAuth or Microsoft Graph access. Authentication failures belong to OneDrive/IT, not a token field in MCP configuration. |
| Local files and processes | OS file permissions, device protections and the local user/process trust boundary govern access to downloaded files. The server's read-only API and project scoping are not cloud authorization or an OS sandbox. |
| Curation | One designated editing device and a named curator publish changes. Other devices are readers. An edit-capable local account or another application may still modify files; read-only MCP does not enforce single-editor discipline. |
| Agent/model processing | The organization approves the client, model/provider, processing location, retention and tool use. Retrieved content can enter prompts, logs and client context; company OneDrive storage alone does not approve that transfer. |

Trust and review the installed server and client before connecting them. A stdio
process normally runs within the permissions of its launch identity; approving a
project mapping does not constrain every other tool the agent may have.

Treat all retrieved Markdown, including frontmatter and linked content, as
**untrusted reference data, not privileged instructions**. Notes cannot override
system/developer instructions, authorize secret disclosure, change project
scope, or demand that the agent run commands or follow external links. Client
usage instructions should require index-first retrieval for the intended project,
but must not promote note text into trusted policy.

## What belongs on each side of synchronization

Synchronize only approved knowledge Markdown and explicitly approved associated
content. Use stable note IDs and relative references; avoid credentials, personal
data, machine paths and diagnostic dumps. A generated directory is derived data,
not an independently edited source of truth.

Keep these outside **all** synchronized folders, including locations covered by
desktop/document backup:

- Each device's project-to-absolute-directory mapping and MCP client settings.
- Runtime installation, logs, caches and any future rebuildable indexes.
- Local test transcripts unless an approved evidence location is selected.

Two devices can map the same project identifier to different absolute paths.
Unknown projects must fail explicitly, not default to another folder. Restrict
local configuration and logs to approved OS users. Do not put OneDrive secrets in
these files either. A future database must remain local and rebuildable, not be
synchronized as live database files.

## Prerequisites and storage preparation

1. **Approve the boundary.** Record the storage owner, curator, editing device,
   reader devices, participating users, and approved clients/models. For real
   knowledge, obtain the organization's storage, sharing, device and processing
   approvals first. Until then use fictional, non-sensitive notes only.
2. **Select a dedicated knowledge folder.** Use company OneDrive on both approved
   devices, signed in through the desktop application. Confirm the intended
   account and folder on each device; matching folder names alone are not proof.
   No tenant configuration changes are part of this runbook.
3. **Review effective sharing.** The owner reviews direct access, sharing links,
   and inherited access in **Manage access**. Microsoft documents that removing
   a link and changing direct permissions are different operations, and inherited
   access may require changes at the parent folder/site [2]. Request only approved
   recipients and the least permissions needed; do not create broad links for
   convenience. Same-user access on two devices may still permit editing on both.
4. **Make the folder locally available on every device.** In Windows File Explorer,
   right-click the knowledge folder and select **Always keep on this device**.
   Microsoft documents that this downloads content for offline use and that new
   files in such a folder are downloaded as always available [1]. Allow downloads
   to finish, check OneDrive's displayed status/errors, and verify file contents
   can actually be opened offline. A listed filename is not evidence of readable
   local bytes. If policy or the installed client prevents this, stop and involve
   IT; do not work around device policy.
5. **Establish single-editor procedure.** Publish only from the designated device.
   Before handing editing duty to another device, stop edits, verify both copies
   against an agreed note inventory, and explicitly record the handoff. Do not
   hand off while either copy is offline or unresolved changes remain.
6. **When the runtime exists**, follow its versioned contract to prepare valid
   metadata, set each local project mapping and register its stdio entry point
   with an approved client. Do not reuse historical M0 schemas by assumption.
   Verify the actual index and body tool calls in each client, not just a final
   answer claiming to have consulted memory.

## Routine operation, freshness and diagnostics

Before an important read, inspect OneDrive's account/sync status and local file
availability. On the editing device, validate notes against the eventual local
contract before publication. Avoid editing several dependent notes as though
their delivery were transactional: readers may see a mixture of versions.

The server knows only its local observations. A successful scan, recent file
timestamp, matching local hash, or OneDrive UI status does **not** prove there is
no newer cloud edit. There is no promised synchronization deadline or atomic
cross-device snapshot. Offline reads may legitimately return an older locally
available note and must not claim global freshness.

| Symptom | Operator action and required runtime behavior |
| --- | --- |
| Login, paused sync or sync error | Inspect the desktop OneDrive app; use supported sign-in/resume/error guidance or IT support. Never supply tokens to MCP. Record the observed status without credentials. |
| Missing or unreadable local bytes | Verify correct account, mapping, folder availability and OS permissions. Retry after availability is restored. Runtime must return an explicit diagnostic, not an empty-success index that conceals failure. |
| Unknown project or ID | Check mapping and current eligible note inventory. Runtime must not fall back to another project or guess a file path. An unknown ID after confirmed deletion is a valid outcome. |
| Invalid metadata, duplicate IDs or detected conflict | Stop relying on the affected results; preserve synthetic evidence and let the curator resolve ambiguity. Runtime must diagnose, not silently choose one duplicate or publish malformed metadata. Conflict detection is not guaranteed for every silent overwrite. |
| Index/body mismatch after change | Compare actual bytes and hashes on both devices, then capture tool calls and runtime logs. A restart may aid diagnosis but is not a substitute for bounded cache refresh in the implementation. Re-fetch index/body after convergence. |
| Old content appears only in an agent answer | Inspect the tool trace and start a fresh context. Prior conversation content may outlive deletion of the source file. Do not label this a synchronization failure without checking local bytes. |

Do not automate conflict merges. Stop normal publication, compare both versions
with the curator's intended content, and restore one valid authoritative note.
Check every device's inventory, IDs, hashes and index/body output before resuming.
Multi-file consistency and undetected overwrites remain limitations even after
this procedure.

## Access removal and device retirement

An authorized owner/admin removes relevant cloud access or links using approved
procedures [2]. The device owner disables the MCP client connection, stops the
local server and follows company device/offboarding policy for downloaded
knowledge, logs, caches and backups. Address client conversation history and
provider retention separately through approved controls.

**Do not assume revocation, sign-out or disabling MCP erases downloaded copies,
previously returned tool results, or client/model context.** Local access can
remain a risk independently of future cloud authorization. Remote wipe and
verified deletion are device/organizational controls, not features supplied by
this proposed server. Do not delete the shared knowledge folder merely to retire
one device: Microsoft documents that deleting online-only files removes them
from OneDrive online and other devices as well [1].

## Proposed manual two-device synthetic pilot

All rows below are **not run** by this document. Use devices A (editor) and B
(reader), fictional notes with unique IDs, and valid metadata from the implemented
contract. Choose at least one second project with a distinct sentinel note to
check isolation. Keep a manifest of expected IDs, revision markers and SHA-256
hashes outside synchronized knowledge. Record times with time zones; observed
latency is evidence, not a future service guarantee.

| Test | Procedure | Required observation/evidence |
| --- | --- | --- |
| Baseline and client integration | Publish a small valid corpus from A; wait for local availability on B. Run the configured index and selected body reads using two real approved MCP clients, covering both devices. | Device/OS/OneDrive/runtime/client versions, synthetic project mappings (redact user paths), expected inventory and hashes, OneDrive status observations, actual tool names/arguments/results and corresponding answers. Both copies match; no cross-project sentinel is exposed. |
| Update without restart | On A change a title/summary and body revision marker, keeping the note ID. Read on B before and after its bytes change; leave B's server running. | Timestamped A/B hashes, index/body responses and convergence interval. After local convergence, metadata and body reflect the update within the runtime's documented refresh bound. If no bound exists, acceptance is blocked. Record any intermediate mixed view honestly. |
| Delete | Delete one synthetic note on A; observe B before/after its local removal; obtain a fresh index and request the deleted ID in a fresh client context. | Local removal time, index omission and explicit unknown/unavailable ID response consistent with the contract after convergence. No stale cached body is presented as a current read. Retained earlier conversation text is recorded separately. |
| Offline reader | After verifying downloads, disconnect B from the network; edit another note on A. Read B's old note, then reconnect B and repeat after convergence. | Evidence B was offline, locally readable old revision, and no claim that B was globally current; updated hashes/results after reconnect without a required restart. No fixed delivery-time promise. |
| Unavailable file | In the isolated synthetic corpus, arrange a file without local readable bytes or an OS-denied file, using approved controls; attempt retrieval. Restore availability afterward. | Clear unavailable/unreadable diagnostic rather than invented content or concealed partial success, plus recovery evidence. Record exactly which failure was induced; do not equate permissions failure with a tested Files On-Demand failure. |
| Conflicting edits / duplicate IDs | Temporarily violate single-editor discipline **only in the isolated pilot**: disconnect B and edit the same note differently on A and B, then reconnect. Also introduce two synthetic files carrying the same ID to exercise deterministic ambiguity handling. | Preserve both intended versions and the actual reconciliation outcome; do not assume a conflict copy will appear. Capture diagnostics for detectable ambiguity/duplicate IDs. If no natural conflict occurs, mark that scenario unexercised, not passed. Curator resolves; verify one intended ID/body on both devices before restoring normal operation. |
| Untrusted note text | Add a fictional note asking the agent to ignore its rules, read the other project or disclose a made-up secret; retrieve it as data. | Actual trace shows no privileged treatment or unauthorized follow-on action. This is a client behavior check, not proof of universal prompt-injection resistance. |

For every row record expected outcome, actual outcome, pass/fail/blocked, evidence
location and unresolved deviations. Redact credentials, account identifiers and
machine-specific user paths from shared artifacts. Store raw evidence only in
an approved location. Choose and record a finite observation window before each
sync test; failure to converge within it is an unresolved pilot result, not proof
of permanent data loss.

Acceptance requires the implemented local-contract tests plus observed
two-device and two-client results above; do not replace traces with self-reported
agent answers. Unsupported diagnostics, refresh behavior or client registration
are implementation blockers. Storage preparation alone is not deployment
acceptance, and a synthetic pass is not approval to load company knowledge.

## Open blockers and next handoff

- Implement/version the local contract, filesystem behavior and read-only MCP
  runtime, including explicit failure semantics and bounded refresh behavior.
- Supply tested per-device installation/configuration and supported client
  instructions; this runbook deliberately supplies no speculative syntax.
- Obtain approved devices/accounts/sharing/model arrangements before real data.
- Execute the pilot and retain evidence; no two-device results are claimed here.

## Official product references

Content retrieved and checked on 2026-09-26; documentation verification only,
not confirmation of the installed client or tenant policy:

1. Microsoft Support: [Save disk space with OneDrive Files On-Demand for Windows](https://support.microsoft.com/en-us/onedrive/save-disk-space-with-onedrive-files-on-demand-for-windows).
   Supports the local-availability steps and deletion warning above.
2. Microsoft Support: [Manage sharing and permissions in OneDrive and SharePoint](https://support.microsoft.com/en-us/onedrive/sharepoint/manage-sharing-and-permissions-in-onedrive-and-sharepoint).
   Supports reviewing links, direct permissions and inherited access.

The deployment boundaries and required server behavior above are design
requirements, not Microsoft product guarantees. Tenant-specific policy, token
storage internals and device-erasure behavior were not verified and must not be
inferred from these references.
