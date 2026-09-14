---
id: kst-002
repository: sample-telemetry
status: active
approval: approved
---

# Request latency

Use `RequestCompletedV2` for current request latency investigations. The old
`RequestLatency` table was retired in this fictional project and must not be
used for current metrics.

`RequestCompletedV2` has one row per completed request:

| Column | Type | Meaning |
| --- | --- | --- |
| Timestamp | datetime | UTC completion time |
| Environment | string | prod or stage |
| ScopeId | string | Workload scope |
| OperationName | string | Operation label |
| RequestId | string | Correlation identifier |
| DurationMs | real | Request duration in milliseconds |
| ResultCode | int | Result code |

Example: production scope `scope-demo`, p95 over the last 30 minutes:

```kusto
RequestCompletedV2
| where Timestamp > ago(30m)
| where Environment == "prod" and ScopeId == "scope-demo"
| summarize P95Ms = percentile(DurationMs, 95), Requests = count()
    by OperationName, bin(Timestamp, 5m)
```

`DurationMs` is already milliseconds; do not multiply by 1000. The example
measures completed requests only, not requests still in flight, and does not
establish a root cause. Use the environment-routing memory to choose a database.
