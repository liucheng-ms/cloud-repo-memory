---
id: kst-003
repository: sample-telemetry
status: active
approval: approved
---

# Request trace correlation

In this fictional codebase, `src\telemetry\RequestCompletionEmitter.cs` writes
completion records into `RequestCompletedV2`. Application diagnostic messages
from `src\telemetry\DiagnosticWriter.cs` go to `ApplicationTraceV3`.
These source paths are illustrative and are not files in CloudRepo Memory.

`ApplicationTraceV3` contains `Timestamp` (UTC datetime), `Environment`,
`ScopeId`, `RequestId`, `Severity`, and `Message` (all strings).

Use `RequestId` to correlate completion records and diagnostic messages.
Also constrain environment, scope, and time; a correlation ID alone is not
enough to safely narrow this investigation.

Example for production request `req-demo-42` in `scope-demo`:

```kusto
ApplicationTraceV3
| where Timestamp > ago(30m)
| where Environment == "prod" and ScopeId == "scope-demo"
| where RequestId == "req-demo-42"
| project Timestamp, Severity, Message
| order by Timestamp asc
```

A missing diagnostic message is not proof that the request never ran.
