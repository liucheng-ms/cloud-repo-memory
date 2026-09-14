# cloud-repo-memory
Cloud-backed, repository-scoped engineering memory for coding agents over MCP.

## Current direction

The first implementation will use Markdown files synchronized by company
OneDrive and a local, read-only MCP server on each device. The server will
generate a Markdown memory index from note metadata and read individual notes
by stable ID. No hosted memory account, database, or vector search is required
for this initial scope.

This repository currently contains design documents and synthetic evaluation
fixtures, not a working MCP server or OneDrive integration. OneDrive provides
file synchronization; it is not a live shared database.

## Design and evidence

- [OneDrive-backed local MVP decision](docs/adr/0002-onedrive-local-memory.md)
- [MCP contract scope and original M0 reference](docs/mcp-tools.md)
- [Synthetic Kusto memory pilot](validation/samples/kusto-memory/README.md)
- [Reported two-agent baseline results](validation/samples/kusto-memory/baseline-results.md)
- [Original M0 competitive validation](docs/competitive-validation.md)

Use synthetic data during development. Real company knowledge requires approved
storage, sharing settings, devices, and agent/model processing arrangements.
