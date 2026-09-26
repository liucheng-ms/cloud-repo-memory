# cloud-repo-memory
Cloud-backed, repository-scoped engineering memory for coding agents over MCP.

## Current direction

The first implementation will use Markdown files synchronized by company
OneDrive and a local, read-only MCP server on each device. The server will
generate a Markdown memory index from note metadata and read individual notes
by stable ID. No hosted memory account, database, or vector search is required
for this initial scope.

This repository now contains a **synthetic-only Windows fixed-NTFS storage
core and local stdio MCP adapter** exposing `list_memory_index` and `get_memory`.
Real subprocess MCP SDK protocol-client checks pass; this is **not a verified
coding-agent or OneDrive integration**. OneDrive provides
file synchronization; it is not a live shared database.

See [stdio setup and protocol evidence](docs/local-stdio-adapter.md) and
[storage-core setup, API and measured limits](docs/synthetic-storage-core.md).
The provisional 100-note subsequent-scan p95 target remains missed (594 ms
versus 500 ms). Real OneDrive, actual MCP clients, tokenizer measurements and
the blocked Windows platform cases are still release gates.

## Design and evidence

- [Delivery plan and acceptance gates](docs/delivery-plan.md)
- [Local MVP v1 contract and retrieval targets](docs/local-mvp-contract.md)
- [OneDrive deployment boundary and pilot runbook](docs/onedrive-deployment.md)
- [Windows filesystem prototype and evidence limits](docs/windows-filesystem-feasibility.md)
- [Synthetic storage core and repeatable measurements](docs/synthetic-storage-core.md)
- [Local stdio adapter, packaging and protocol evidence](docs/local-stdio-adapter.md)
- [Copilot CLI + Codex evaluation kit and blocked launch gates](docs/real-client-evaluation.md)
- [OneDrive-backed local MVP decision](docs/adr/0002-onedrive-local-memory.md)
- [MCP contract scope and original M0 reference](docs/mcp-tools.md)
- [Synthetic Kusto memory pilot](validation/samples/kusto-memory/README.md)
- [Reported two-agent baseline results](validation/samples/kusto-memory/baseline-results.md)
- [Original M0 competitive validation](docs/competitive-validation.md)

Use synthetic data during development. Real company knowledge requires approved
storage, sharing settings, devices, and agent/model processing arrangements.
