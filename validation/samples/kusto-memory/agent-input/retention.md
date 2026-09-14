---
id: kst-005
repository: sample-telemetry
status: active
approval: approved
---

# Retention and historical data

In this synthetic project, `RequestCompletedV2` and `ApplicationTraceV3` retain
30 days in production and seven days in staging.

This corpus does not document an archive location or a historical restore
procedure. Ask the project owner about older data rather than inventing a
storage account, container, or recovery command.

For a production event 45 days old, absence from these tables is consistent
with retention. It is not proof that the event never happened, nor a guarantee
that a recoverable archive exists.
