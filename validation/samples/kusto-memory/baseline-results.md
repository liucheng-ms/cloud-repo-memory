# Reported Markdown baseline results

- Evaluation date: 2026-09-13
- Report recorded: 2026-09-14
- Corpus: five fictional notes plus a static Markdown directory
- Method: user ran questions in external agent sessions and pasted answers into
  the project conversation for manual assessment
- Evidence retained here: summarized observations, not raw tool traces or a
  reproducible benchmark transcript

## Scope of the result

Both agents' six supplied answers satisfied the cases' core factual criteria
and avoided the listed unsupported project claims. This is an answer-content
result, not full passage of the pilot protocol: required note reads cannot be
verified from citations or self-reported reads alone.

Agent A is the first client used by the user; Copilot CLI was suggested, but
the actual client and model/version were not independently established.
Agent B was identified by the user as Codex; its exact version and model are
unknown. Fresh conversations were requested for each case, but session
isolation was not verified. Questions were supplied in Chinese paraphrases of
the English evaluator cases, not necessarily as byte-identical prompts.

## Per-case observations

| Case ID | Agent A core answer | Codex core answer | Important behavior |
| --- | --- | --- | --- |
| `latency-paraphrase` | Pass | Pass | Correct environment, table, time/scope filters, p95 grouping, and millisecond units. |
| `code-to-log-correlation` | Pass | Pass | Correct emitter/table mapping and request/environment/scope/time correlation. |
| `missing-recent-event` | Pass | Pass | Two-minute visibility is an expectation, not a guarantee; lag query covers arrived rows only. |
| `historical-data` | Pass | Pass | Thirty-day production retention; no invented archive location or recovery guarantee. |
| `missing-scope` | Pass | Pass | Correct staging selection; requested the real ScopeId rather than reusing scope-demo. |
| `unknown-topic` | Pass | Pass | No invented Redis eviction policy or cache dashboard. |

The questions were run in the order latency, recent-event absence, unknown
topic, missing scope, historical data, and code/log correlation.

## Qualifications and quality notes

- Agent A omitted memory IDs in the latency answer. Its core facts passed,
  but the requested citation instruction was not fully followed.
- Agent A's pasted ingestion query contained `ingestion\_time()` and
  `datetime\_diff()`. If literal in the original code block, these are invalid
  KQL function spellings. A copy/rendering artifact could not be ruled out.
  Queries were not executed.
- Agent A called RequestId a "primary key" in the correlation answer. The
  corpus establishes a correlation identifier, not a uniqueness constraint;
  this terminology should be corrected.
- Agent A used wording suggesting further investigation should happen only
  after the usual visibility window. That window is guidance, not a rule
  prohibiting earlier investigation.
- For the unknown Redis question, Agent A reported no relevant memory reads;
  Codex reported checking all five bodies. This is a possible efficiency
  difference, not measured tool usage or proof of superior reliability.
- Codex initially repeated `cua_repl.js_reset` calls. A diagnostic instruction
  prohibiting JavaScript then blocked its reported file-tool entry point.
  The restriction was withdrawn before successful answers were supplied.
  The reset-loop cause and whether the first successful answer used a fresh
  conversation remain unknown.
- Codex's missing-scope answer referred to a "previous" production example.
  That could refer to the supplied memory itself; it is not proof of session
  contamination, nor proof of independent sessions.
- Neither answer set independently establishes that evaluator files were not
  read. Instructions prohibited such reads, but were not a filesystem boundary.

## What this supports

A small, explicit Markdown index plus topic bodies can support grounded answers
in two observed agent workflows. The responses do not establish an immediate
need for semantic retrieval in this five-note corpus.

## What this does not establish

- Verified retrieval order, tool calls, actual memory IDs read, or token/latency
  measurements.
- Automatic memory discovery without an explicit user instruction.
- General retrieval quality at larger scale, repeated-run reliability, or
  superiority to keyword/vector search.
- A running MCP implementation, OneDrive synchronization, multi-device freshness,
  concurrent editing, access control, or human approval.
- A runtime comparison with Basic Memory, LongMemory, or any hosted product.

For a repeatable run, isolate evaluator files from the tested workspace, record
client/model versions and fresh-session setup, and capture tool traces. A later
shared-storage pilot should prevent fallback to the old local fixture and
observe a controlled update becoming available on the second device.
