# ADR 0002: OneDrive-backed local memory MVP

- Status: Accepted for the first implementation
- Date: 2026-09-14
- Relationship: Narrows the initial scope of M0; defers, rather than implements,
  ADR 0001 and the original MCP contracts.

## Context

The immediate goal is a learning project that makes curated engineering
knowledge available across a person's computers and coding agents. The user
wants company-controlled storage rather than a third-party hosted memory
account. Company OneDrive is the preferred file synchronization mechanism.

A small synthetic Markdown pilot produced acceptable core answers from two
agents, based on user-pasted responses. It did not verify retrieval traces,
cross-device synchronization, or production suitability. It supports trying a
simple index-first design, not a claim that search is unnecessary at any scale.

PostgreSQL was discussed but has not been implemented. Basic Memory's local
design demonstrates useful separation between Markdown knowledge, per-machine
configuration, local retrieval indexes, and MCP access. We will borrow that
separation without initially building its database, vector, or graph features.

## Decision

Use company OneDrive to store and synchronize Markdown knowledge files. Run a
local read-only MCP server on each device, initially over stdio. Each server
reads its own local synchronized copy; clients do not connect to a shared cloud
MCP endpoint.

```text
Company OneDrive
    |
    | file synchronization
    v
Local Markdown folder on each device
    |
    v
Local MCP server
    |-- list_memory_index: metadata -> Markdown directory
    |-- get_memory: project-scoped ID -> full note
    v
Coding agent
```

### Files are the source of knowledge

Each note carries a stable ID, title, summary, and read-when guidance in YAML
frontmatter, followed by its Markdown body. Lifecycle metadata determines
eligibility consistently for the directory and body reads. Exact required
fields, defaults, and validation rules belong in the upcoming local-MVP
contract; malformed metadata must not silently become a valid published note.

The server generates the directory from eligible note metadata. A separately
editable `MEMORY.md` is not a second source of truth. A future generated export
could be convenient, but must be clearly derived and never independently
maintained.

The pilot's static `MEMORY.md` remains a test fixture. Its topic files do not
yet contain every proposed metadata field; adapting them to the final local
schema is implementation work, not something this ADR claims is complete.

### Keep storage behind a thin interface

Business logic requests project-scoped index entries or a note by ID. The
filesystem implementation handles reading and parsing files; the business
layer renders the Markdown directory. Do not expose filesystem paths or SQL as
the business interface.

Each machine configures its own project-to-absolute-directory mapping outside
shared knowledge files. Notes use stable IDs and relative references, not
machine-specific paths. Unknown project mappings fail explicitly rather than
falling back to another directory.

Scope every lookup to the configured project. IDs are identifiers, not access
credentials or caller-controlled paths. Implementation must address traversal,
symlink/junction escapes, duplicate IDs, and accidental cross-project reads.
Local scoping is not provider identity verification or a multi-user cloud
authorization system.

### No database or search engine initially

Scan Markdown metadata to construct the directory, then let the agent select
the relevant bodies. Do not add PostgreSQL, SQLite, embeddings, vector search,
or a knowledge graph to the initial implementation.

Revisit this choice if measured scan latency, directory context size, or missed
relevant memories becomes a problem. Simple file search or a per-device
rebuildable index can be added before adopting more complex retrieval.

Any later database index lives outside OneDrive. Synchronize source Markdown,
not live database files or database data directories.

### OneDrive owns synchronization, not consistency guarantees

Keep the knowledge folder available locally (for example, with "Always keep on
this device"). Start with one editing location and readers on other devices.
OneDrive can deliver changes late or produce conflicts; updates across multiple
files are not an atomic snapshot.

Unreadable/unavailable files, invalid metadata, duplicate IDs, or detected
conflicts must produce explicit diagnostics rather than empty success results
or guessed content. Local reads cannot prove the cloud has no newer version:
report that freshness limitation instead of claiming a globally current view.
The implementation must avoid indefinitely serving stale cached metadata.

The read-only server does not automate OneDrive login, configure sharing,
merge conflicts, or synchronize files itself. It also does not establish a
human approval boundary: anyone with file-edit permissions can change status
metadata.

### Client setup remains necessary

MCP availability alone does not automatically load memory at session start.
Each supported agent needs a usage instruction to obtain the configured
project's index and read relevant bodies. End-to-end behavior must be observed,
not inferred from an answer that claims to have read a note.

Company storage is only one part of the data boundary. Real knowledge also
requires approved sharing settings, devices, and agent/model processing.
Development continues with fictional fixtures.

## Relationship to M0

| M0 area | First local MVP treatment |
| --- | --- |
| Azure DevOps remote resolution and GUID aliases | Deferred; configure project directories explicitly. |
| `search_memories` as discovery entry | Deferred; use generated Markdown index first. |
| UUID-based tool schemas and response envelopes | Retain as historical M0; define a separate versioned local contract before implementation. |
| Candidate proposal, approval, supersession, audit | Deferred; manually curated files, no human-approval guarantee. |
| Central database and shared HTTP service | Not required; local stdio servers read synchronized files. |
| Project-scoped access | Preserve as a local lookup constraint; no claim of cloud authorization or checkout attestation. |

Keep `contracts/mcp-tools.manifest.json` and
`validation/m0-acceptance-corpus.json` unchanged. Their tests and schemas are not
automatically the acceptance criteria for this smaller MVP.

## Next implementation boundary

Define the local contract, then implement project configuration, metadata
parsing, index rendering, and scoped body reads with the filesystem adapter.
Exercise missing files, malformed metadata, duplicate IDs, scope escapes,
updates, and unknown IDs as well as successful reads.

After local operation works, run the same dataset through two real MCP clients
and observe an edit arriving on a second OneDrive-connected device. No such
MCP or synchronization result is claimed by this decision.

## Alternatives and consequences

- Direct agent file reads remain the cheapest baseline, but require per-client
  instructions and expose different file access behavior.
- Basic Memory local is a viable adoption alternative, not excluded by rejecting
  its cloud service. A smaller custom implementation serves the learning goal.
- Hosted PostgreSQL plus a remote MCP service would better support centralized
  transactions and multi-user governance, but brings unnecessary initial
  deployment and authentication work for the selected scope.
- Index-first retrieval is easy to inspect but consumes context as the corpus
  grows and depends on useful metadata and agent behavior.

## References

Consulted on 2026-09-14; documentation review, not an installed-product test:

- [Basic Memory local installation](https://docs.basicmemory.com/local/local-install)
- [Local project directory configuration](https://docs.basicmemory.com/local/getting-started)
- [Markdown knowledge format](https://docs.basicmemory.com/concepts/knowledge-format)
- [MCP, indexing, and consistency commands](https://docs.basicmemory.com/reference/cli-reference)
- [Synthetic pilot evidence](../../validation/samples/kusto-memory/baseline-results.md)
