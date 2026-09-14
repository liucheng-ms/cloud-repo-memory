# Synthetic Kusto memory pilot

These fictional fixtures exercise index-first retrieval, not a real company's
infrastructure. Names, schemas, paths, and operational rules are invented.
There is no live cluster, credential, or dataset. Do not execute the queries
against a real environment without adapting and reviewing them.

This pilot supplements, rather than changes, `validation/m0-acceptance-corpus.json`.
It is not an implementation of the frozen MCP contracts.

See [reported baseline results](baseline-results.md) for the user-run two-agent
answer assessment and its limitations. The selected implementation direction is
the [OneDrive-backed local MVP](../../../docs/adr/0002-onedrive-local-memory.md).

## Layout

- `agent-input\MEMORY.md`: the agent-visible Markdown index.
- `agent-input\*.md`: individual approved, active memories for `sample-telemetry`.
- `evaluation-cases.json`: evaluator-only questions, required memories, answer
  facts, and forbidden claims. Do not import it into a memory service or expose
  it to the agent being evaluated.
- `baseline-results.md`: evaluator-side summary; do not expose it to the tested
  agent either.

Each topic file has a stable ID in its metadata. A file-based baseline follows
the index links; an MCP adapter would map these IDs to `get_memory` calls.
No adapter or MCP server is implemented here.

## Running a comparable pilot

1. Import or expose only `agent-input` to each candidate solution, preserving
   IDs and content. Map it to the same `sample-telemetry` project.
2. Start a fresh conversation for each case. Give the agent the instruction
   below and only that case's `question`, not the answer criteria. Expose a copy
   of `agent-input` alone for a stronger separation than a do-not-read instruction.
3. Record the client/model, configuration, setup effort, tools called, memory
   IDs read, and final answer. If retrieval traces are unavailable, record that
   as unknown rather than assuming the agent read a cited memory.
4. Score with `evaluation-cases.json`. Every required ID must be read; all
   required facts must be present; no forbidden claim may be made. Reading
   unrelated memories is an efficiency observation, not an automatic failure.
5. Compare the same cases and instruction across the Markdown baseline and an
   existing memory platform. Do not give one solution the evaluator answers.

Suggested agent instruction:

> You are working on sample-telemetry. Before answering a project-knowledge
> question, obtain its memory index and read relevant topic bodies. Treat index
> summaries as navigation, not sufficient evidence. Cite the IDs you used.
> Do not read evaluator files. Distinguish documented facts from assumptions.
> If the memory does not contain an answer, say so. Do not connect to any cluster
> or execute queries; all infrastructure in this exercise is fictional.

## Limits

The expected facts deliberately depend on invented project details rather than
generic Kusto expertise. The SQL-like examples are KQL illustrations, not
runtime-tested queries.

This small corpus can expose retrieval and answer-grounding mistakes. It cannot
establish production accuracy, permission enforcement, Git remote identity
resolution, human approval, concurrent updates, stale-cache handling, or cloud
reliability. The static index is a fixture, not proof of automatic index updates.
Fresh-session runs test portability, not synchronization.

If evaluating a cloud product, import only these synthetic fixtures; no real
project knowledge is needed. Provisioning accounts and uploading remain
separate actions.
