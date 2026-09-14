---
id: kst-001
repository: sample-telemetry
status: active
approval: approved
---

# Environment routing

All aliases below are fictional labels, not connection addresses.

| Environment | Cluster alias | Database | Environment field |
| --- | --- | --- | --- |
| Production | sample-prod-observe | TelemetryProd | prod |
| Staging | sample-stage-observe | TelemetryStage | stage |

Select the matching database before running a query. The two environments have
the same table schemas but different data. An empty staging result says nothing
about production.

The telemetry tables use `ScopeId` to distinguish workload scopes. An
environment filter is not a substitute for a scope filter. For a scope-specific
investigation, obtain the scope from the user if it is missing.

No connection URLs, authentication instructions, or credentials are documented.
