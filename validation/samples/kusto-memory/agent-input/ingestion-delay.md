---
id: kst-004
repository: sample-telemetry
status: active
approval: approved
---

# Missing recent events

This synthetic project enables the Kusto ingestion-time policy on
`RequestCompletedV2`. Its pipeline normally makes events queryable within two
minutes. That is an observed expectation, not a guarantee.

For ingested rows, compare event time with approximate ingestion time:

```kusto
RequestCompletedV2
| where Timestamp > ago(30m)
| where Environment == "prod" and ScopeId == "scope-demo"
| extend IngestedAt = ingestion_time()
| where isnotnull(IngestedAt)
| extend LagSeconds = datetime_diff("second", IngestedAt, Timestamp)
| summarize P95LagSeconds = percentile(LagSeconds, 95), Samples = count()
```

This measures only rows that have arrived. It cannot measure the delay of a
missing row, and an empty result cannot prove ingestion is healthy. Event-clock
skew can also distort the measurement.

For an event emitted 30 seconds ago, first verify the environment and scope,
then check again after the usual two-minute window. Persistent absence requires
checking the emitting service and ingestion pipeline; this memory does not
document their dashboards or a definitive diagnosis.
