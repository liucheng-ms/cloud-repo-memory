# Competitive validation

Validated on 2026-09-04 against the current public documentation and source of Basic Memory and LongMemory. The checks below inspect the shipped MCP surfaces and server-side enforcement points; they are not marketing-feature comparisons.

## Decision

Continue with a narrow repository control plane. Do not build a general memory engine.

Neither project simultaneously provides:

1. Azure DevOps HTTPS and SSH remote normalization to the same repository GUID.
2. A remote server that binds every query and write to that resolved repository.
3. A persisted unpublished candidate followed by an exact-payload approval step.

Both projects already solve large parts of generic memory storage and retrieval. CloudRepo Memory must therefore remain focused on repository identity, isolation, engineering-memory lifecycle, and cross-client consistency.

## Basic Memory

| Check | Result | Evidence |
| --- | --- | --- |
| Azure DevOps HTTPS/SSH to stable GUID | Fail | Coding setup asks the Agent to determine a repository string; the project model's `external_id` is a Basic Memory project UUID, not a remote-derived Git repository identity. See [`bm-setup/SKILL.md`](https://github.com/basicmachines-co/basic-memory/blob/main/plugins/codex/skills/bm-setup/SKILL.md), [`project.py`](https://github.com/basicmachines-co/basic-memory/blob/main/src/basic_memory/models/project.py). No Azure DevOps remote resolver is present in the documented integration surface. |
| Server-enforced repository scope | Fail | MCP writes accept caller-selected `project`, `project_id`, and `workspace`; resolution prioritizes an environment constraint when configured but otherwise accepts explicit project selection. This is workspace authorization, not binding to the current checkout remote. See [`write_note.py`](https://github.com/basicmachines-co/basic-memory/blob/main/src/basic_memory/mcp/tools/write_note.py), [`project_resolver.py`](https://github.com/basicmachines-co/basic-memory/blob/main/src/basic_memory/project_resolver.py). |
| Engineering kinds, commit provenance, supersession | Partial | The packaged decision schema supports status and supersession, and coding-session notes can carry repository/branch/SHA. Custom schemas can represent pitfall/convention/procedure, but this is not one enforced lifecycle attached to every engineering memory. See [`decision.md`](https://github.com/basicmachines-co/basic-memory/blob/main/plugins/claude-code/schemas/decision.md), [`coding-session.md`](https://github.com/basicmachines-co/basic-memory/blob/main/plugins/claude-code/schemas/coding-session.md). |
| Persisted unpublished candidate then human publication | Fail | Cloud comments/suggestions are review markup on notes; OSS `write_note` mutates immediately. The accepted-note journal records accepted mutations but is not a separately unpublished candidate store. Client MCP approval remains a client policy. See [comments and suggestions](https://docs.basicmemory.com/cloud/comments-and-suggestions), [`accepted_note_repositories.py`](https://github.com/basicmachines-co/basic-memory/blob/main/src/basic_memory/repository/accepted_note_repositories.py), [MCP tools reference](https://docs.basicmemory.com/reference/mcp-tools-reference). |
| One remote instance shared by target clients | Pass | Basic Memory Cloud documents a shared remote MCP endpoint and integrations for major MCP clients. See [Basic Memory README](https://github.com/basicmachines-co/basic-memory#basic-memory-cloud). |

A plugin could add schemas and URL parsing, but repository binding and publication approval require trusted server-side behavior.

## LongMemory

| Check | Result | Evidence |
| --- | --- | --- |
| Azure DevOps HTTPS/SSH to stable GUID | Fail | Azure DevOps is represented through a configurable REST connector, while the specialized GitHub connector identifies repositories as `owner/repo`. There is no Azure Git remote parser/GUID resolver. See [`service_catalog.ts`](https://github.com/CaviraOSS/LongMemory/blob/main/src/connectors/service_catalog.ts), [`configurable_connector.ts`](https://github.com/CaviraOSS/LongMemory/blob/main/src/connectors/configurable_connector.ts), [`github_connector.ts`](https://github.com/CaviraOSS/LongMemory/blob/main/src/connectors/github/github_connector.ts). |
| Server-enforced repository scope | Partial/fail for stock HTTP | Permission code can reject a project different from a server-bound project, but the stock HTTP app creates the MCP runtime without such a fixed project. See [`permissions.ts`](https://github.com/CaviraOSS/LongMemory/blob/main/src/mcp/security/permissions.ts), [`runtime.ts`](https://github.com/CaviraOSS/LongMemory/blob/main/src/mcp/runtime.ts), [`app.ts`](https://github.com/CaviraOSS/LongMemory/blob/main/src/server/app.ts). |
| Engineering kinds, commit provenance, supersession | Pass/partial naming | Project events include decisions, failures/bugs, conventions and code facts; provenance includes repo/branch/commit/path, and selected kinds supersede old facts. A procedure can be modeled as a claim/skill rather than the exact requested event kind. See [`project_state.ts`](https://github.com/CaviraOSS/LongMemory/blob/main/src/core/project/project_state.ts), [`project_ingest.ts`](https://github.com/CaviraOSS/LongMemory/blob/main/src/core/project/project_ingest.ts). |
| Persisted unpublished candidate then human publication | Partial | Governed assets have draft/candidate/approved states and non-approved assets are excluded from loadout, but the MCP management input may register approved status and does not prove a distinct human approver. See [`project_assets.ts`](https://github.com/CaviraOSS/LongMemory/blob/main/src/core/project/project_assets.ts), [`manage_asset.ts`](https://github.com/CaviraOSS/LongMemory/blob/main/src/mcp/tools/manage_asset.ts). |
| One remote instance shared by target clients | Protocol pass, packaged matrix unproven | The server exposes authenticated Streamable HTTP. Cursor and Claude integrations exist, while the reviewed material does not provide a verified Copilot CLI + Claude Code + Cursor remote acceptance matrix. See [`docs/mcp.md`](https://github.com/CaviraOSS/LongMemory/blob/main/docs/mcp.md), [`integrations/README.md`](https://github.com/CaviraOSS/LongMemory/blob/main/integrations/README.md). |

A plugin could add aliases and client configuration. Stable identity, server-bound scope, and approval provenance require core changes or a trusted gateway.

## Continue/stop conclusion

**Continue, but only as a narrow control-plane experiment.**

- Basic Memory already solves generic personal memory and cross-device MCP access.
- LongMemory already solves rich memory semantics and much of governed lifecycle.
- The remaining independent hypothesis is the combination of stable Git-provider identity, server-derived repository scope, and exact candidate publication.

This is a conditional go decision, not proof that a new general memory product is needed. Re-run this gate before M1 because both upstream projects are moving quickly.

## Stop conditions retained

Stop or pivot to an upstream contribution if:

- an existing project adds all three differentiators without a core fork;
- the remaining solution is only a thin client plugin; or
- target MCP clients cannot reliably present approval for the final decision tool.

## Validation limitation

No source can prove a human clicked a client approval prompt: MCP tool annotations are advisory. M0 therefore freezes this as a product risk. A later client acceptance test must either demonstrate reliable confirmation in the selected clients or move human approval out of band; otherwise the project must stop or change its claim.
