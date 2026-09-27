# cloud-repo-memory
Cloud-backed, repository-scoped engineering memory for coding agents over MCP.

## Current direction

The implementation uses Markdown files synchronized by the OneDrive desktop
client and a local, read-only MCP server on each device. The server generates
a Markdown memory index from note metadata and reads individual notes
by stable ID. No hosted memory account, database, or vector search is required
for this initial scope.

This repository contains an **experimental Windows fixed-NTFS storage core
and local stdio MCP adapter** exposing `list_memory_index` and `get_memory`.
Development and trials use synthetic knowledge only. OneDrive owns Microsoft
authentication and synchronization; the MCP server does not handle Microsoft
tokens, write notes, or provide a live shared database.

## Weekly delivery: 2026-09-27

- Implemented strict note metadata, project-scoped index/body retrieval, source
  versions, explicit errors, supervised filesystem workers, and the stdio adapter.
- Observed one successful Copilot CLI synthetic retrieval with index-first calls
  and matching citations. The one Codex attempt was blocked by timeout/HTTP 401;
  it is not a successful integration or a formal client comparison.
- Completed a bounded personal-OneDrive-directory CRUD/version pilot and observed
  a user-confirmed web edit through local MCP. These are limited observations,
  not general provider or company-tenant certification.

Cloud synchronization is delegated to OneDrive and is **not an additional gate
for this delivery**, per the user's scope decision. Local unavailable-file
handling remains our responsibility; responses report cloud freshness as unknown.
Second-device and Files On-Demand behavior remain unverified, not implied passes.
The provisional 100-note scan p95 is still 594 ms against a 500-ms target.
Routine client registration, broader retrieval evaluation, tokenizer measurements,
and blocked Windows platform cases remain follow-up work. This is not a
production-ready release.

## Start here

1. Follow [installation, configuration and stdio launch](docs/local-stdio-adapter.md).
   Configuration explicitly maps a project to an owned local directory; keep it
   outside synchronized knowledge. No automatic client registration is performed.
2. Use the [local-v1 note contract](docs/local-mvp-contract.md) for metadata and
   versioned reads. Historical M0 samples need the documented fixture adaptation;
   do not copy them unchanged into a local-v1 knowledge root.
3. See the [client evaluation kit](docs/real-client-evaluation.md) for synthetic
   fixture preparation and gated client recipes. Preparation does not launch
   models; new runs require separate approval.

See [storage setup and measured limits](docs/synthetic-storage-core.md) for the
callable API. The live OneDrive pilot is opt-in, not an installation step:
do not rerun it against an existing folder.

## Design and evidence

- [Delivery plan and acceptance gates](docs/delivery-plan.md)
- [Local MVP v1 contract and retrieval targets](docs/local-mvp-contract.md)
- [OneDrive deployment boundary and pilot runbook](docs/onedrive-deployment.md)
- [Windows filesystem prototype and evidence limits](docs/windows-filesystem-feasibility.md)
- [Personal OneDrive directory pilot and web visibility](docs/personal-onedrive-pilot.md)
- [Synthetic storage core and repeatable measurements](docs/synthetic-storage-core.md)
- [Local stdio adapter, packaging and protocol evidence](docs/local-stdio-adapter.md)
- [Copilot CLI + Codex evaluation kit and bounded smoke outcomes](docs/real-client-evaluation.md)
- [OneDrive-backed local MVP decision](docs/adr/0002-onedrive-local-memory.md)
- [MCP contract scope and original M0 reference](docs/mcp-tools.md)
- [Synthetic Kusto memory pilot](validation/samples/kusto-memory/README.md)
- [Reported two-agent baseline results](validation/samples/kusto-memory/baseline-results.md)
- [Original M0 competitive validation](docs/competitive-validation.md)

Use synthetic data during development. Real company knowledge requires approved
storage, sharing settings, devices, and agent/model processing arrangements.
