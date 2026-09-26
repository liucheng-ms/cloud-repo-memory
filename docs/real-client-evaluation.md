# Copilot CLI + Codex synthetic evaluation kit

Status: **prepared, not launched**. The user selected these two clients.
This kit makes local-v1 inputs and twelve gated run recipes (six fresh sessions
per client). It does not invoke a coding agent, choose a model, log in, register
MCP servers, read user configuration/auth/history, or change global settings.
SDK `ClientSession` checks are protocol evidence, not real-agent runs.

Baseline: reviewed synthetic MCP commit
`2b9ee5c54d619c98fdb095d4e944a8886c1ec60f`. Keep the
[contract](local-mvp-contract.md), historical fixtures, M0, and schema unchanged.
The existing 594-ms p95 miss, OneDrive/provider behavior and second-device gates
remain open. No runtime/performance redesign is included.

## Prepare, without launching

Use the existing tested editable installation from
[stdio setup](local-stdio-adapter.md). The interpreter must have this package
installed: an absolute Python path alone does not make a checkout importable.
From the checkout, substitute an **already owned, existing, local, non-redirected**
parent and a **new direct child**. These example paths are placeholders:

```powershell
.\.venv\Scripts\python -B validation\real_clients\prepare.py `
  --owned-parent 'C:\OwnedSyntheticEvaluation' `
  --output 'C:\OwnedSyntheticEvaluation\trial-001' `
  --python 'C:\OwnedCheckout\.venv\Scripts\python.exe'
```

No current-directory or home-directory discovery, credential copying, model
calls, external data retrieval, or client subprocesses occur in preparation.
The generator rejects relative/network paths, redirected directory ancestors,
existing output directories/files and outputs outside the specified parent.
Use a new unique child for every trial. Failures are nonzero; any partial output
is retained and must not be reused. Parent checks are not a defense against a
malicious concurrent same-user filesystem replacement.

Generated layout:

| Directory | Contents and intended reader |
| --- | --- |
| `knowledge` | Exactly five local-v1 notes for the MCP server |
| `config` | Local server JSON, Copilot MCP JSON, Codex TOML override argument in JSON; operator only |
| `sessions\<client>\<case>` | One identical question/instruction file for each fresh client session |
| `recipes` | Non-executable JSON descriptions of command/argv, input and trace destinations; operator only |
| `traces\<client>\<case>` | Initially empty local capture destinations; evaluator only |
| `evaluator` | Original six-case rubric, source/body hashes, twelve `NOT_RUN`/`UNVERIFIED` records |

The five notes derive only from the named historical topic files plus
`fixture_adaptation.overlays` in `validation\local-mvp-acceptance.json`.
Frontmatter is converted to local-v1; bodies are preserved byte for byte.
The manifest hashes original bytes, adapted bytes and body bytes separately.
Neither historical `MEMORY.md` nor evaluator answers are copied into knowledge.
There is **no hand-maintained generated MEMORY index**: capture the actual
`list_memory_index` result during a run. The SDK test writes its own temporary
index snapshot as SDK evidence, not as an agent input.

Generated JSON contains the explicitly supplied interpreter/output paths.
Keep it local, outside OneDrive and version control; tracked kit sources use
no machine-specific paths. No secrets are included by the generator. Future
client traces may contain sensitive instructions or paths, so do not publish
them without review.

## Required preflight decisions: both launches BLOCKED

1. Approve an exact model for each client and the relevant reasoning/context
   settings. Recipes contain `<USER_REVIEWED_MODEL>` with no default fallback.
   Record requested and observed models separately; unavailable models stop a
   run rather than triggering an unreviewed fallback.
2. Approve the effective tools, MCP servers, hooks, plugins, instructions,
   prior-memory exposure and environment for each client. Do not inspect auth
   files or dump environment values to settle this. An operator can review
   nonsecret settings, or use a genuinely separate approved environment.
3. Establish an enforced evaluator boundary or hold all evaluation expectations
   externally, inaccessible to the client. A different directory under the
   same user is **not OS isolation**. This checkout itself contains the original
   answer rubric. Merely moving the generated evaluator folder is insufficient
   while the client can read that checkout. Editable Python installation also
   points at this checkout. Use approved filesystem/tool restrictions, or a
   separately provisioned environment with only the installed runtime and
   synthetic knowledge/individual prompt; keep the source checkout and rubric
   on the evaluator side. Re-generate absolute configuration paths there.
4. Approve the synthetic-only model launch and local content-bearing trace
   capture. Existing authentication stays with the client; do not create a fake
   HOME/CODEX_HOME, copy credentials, embed bearer data, change global config or
   perform login/installation as part of this kit.

Prompt instructions forbidding file reads are an experimental protocol, **not
access enforcement**. Mark leakage/boundary uncertainty `UNVERIFIED`, not pass.
Do not run client setup through `mcp add`, persistent toggles, or unrestricted
tool/approval/sandbox flags to bypass any blocker. The recipes are data, not a
launcher; preparation and tests cannot accidentally execute them.

## Installed-version flag evidence and recipe scope

Read-only help/version probes on 2026-09-26 observed **Copilot CLI 1.0.87-0**
and **codex-cli 0.154.0** (the installed Windows Codex command uses a PowerShell
shim). Commands verified:

```powershell
copilot --version
copilot --help
copilot help permissions
copilot help logging
copilot help config
copilot help environment
copilot help monitoring
copilot mcp --help
copilot mcp add --help
codex --version
codex --help
codex exec --help
```

Help-only probes do not validate a model launch or guarantee the effective
client environment. Public Codex documentation pages returned HTTP 403 here;
configuration keys and JSONL behavior were checked against official
[0.154.0 schema](https://github.com/openai/codex/blob/rust-v0.154.0/codex-rs/core/config.schema.json)
and [JSONL event implementation](https://github.com/openai/codex/blob/rust-v0.154.0/codex-rs/exec/src/event_processor_with_jsonl_output.rs).
The tag resolves to `36eab01061df3cde5f95ec20a526777b430091ba`.
Installed `--help` is the authority for the flags below, not examples from a
different release. Recheck help/version after any client change.

### Copilot: interactive, session-added MCP, local OTel

Each Copilot recipe describes:

- `-C <case-directory> --mode interactive --model <reviewed-model> -i <prompt>`.
  It never uses resume/continue or prompt-mode `-p`: installed help says
  noninteractive mode requires `--allow-all-tools`, which this kit does not grant.
- `--additional-mcp-config @<absolute-json>` augments existing configuration for
  this session. The JSON declares only a local `synthetic-memory` server with an
  absolute Python command, absolute `--config` argument and the two named tools.
  It **does not replace global, workspace or plugin MCP configuration**.
- `--disable-builtin-mcps` disables built-in MCP servers (currently GitHub), not
  user/plugin servers. `--no-custom-instructions` disables AGENTS.md and related
  custom instructions, not all hooks/plugins/prior memory.
  `--deny-tool shell --deny-tool write` denies shell/write tool approvals;
  `--disallow-temp-dir` removes automatic temporary-directory access.
  These are not a complete native-read or initialization-hook boundary.
- `--no-auto-update` pins the installed binary for this launch;
  `--no-remote-export` disables remote session export/control.
  `--log-dir`, `--log-level debug`, and `--usage-output-file` target per-case files.

Help also documents `--available-tools` as excluding all other model tools,
`--excluded-tools` as hiding selected tools, and repeatable
`--disable-mcp-server <name>`. Permission patterns
`<server>(<tool>)` apply to `--allow-tool`/`--deny-tool`; do not assume that syntax
also resolves tool *availability* names. Those exact effective names and unknown
server exclusions require operator review. These filters are not proven to
suppress server startup, hooks, or already-loaded instructions. No blanket
clean-profile claim is made.

Recipe environment overrides are **process-local only**, set by the approved
operator for that future child process, not written to a profile:

```text
COPILOT_OTEL_EXPORTER_TYPE=file
COPILOT_OTEL_FILE_EXPORTER_PATH=<absolute-case-trace>\otel.jsonl
OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true
```

`copilot help monitoring` documents the file exporter and content capture of
tool arguments/results, messages, model/token information and durations.
Explicit `file` avoids inheriting an OTLP exporter selection for this capture.
It does not establish that all organization-managed telemetry is disabled.
Content capture can include system instructions and private paths: enable only
after the isolation/content review. Leave the interactive terminal attached;
after the answer, exit normally to flush traces. Debug logs or a final citation
alone are not evidence of complete tool inputs/results. If the OTel file lacks
them, set exact-call/trace coverage `UNVERIFIED`.

### Codex: ephemeral exec, ignore user config, read-only sandbox, JSONL

Each Codex recipe describes:

```text
codex exec --ignore-user-config --ephemeral
  --sandbox read-only --skip-git-repo-check -C <case-directory>
  --model <reviewed-model> --json --output-last-message <case-trace>\final.txt
  -c <generated-mcp-override> -c web_search="disabled"
  -c project_doc_max_bytes=0 -
```

This is a **not-run recipe**, not a PowerShell command to paste: JSON `argv`
contains exact argument boundaries including TOML quotes. Feed `stdin_file` as
UTF-8 prompt input, capture stdout to `events.jsonl` and stderr separately.
Do not use shell-string concatenation/`Invoke-Expression`. The final `-` is the
documented stdin-prompt selector. No `--ignore-rules`, automatic approval or
sandbox-bypass option is supplied. The
[version-tagged exec implementation](https://github.com/openai/codex/blob/rust-v0.154.0/codex-rs/exec/src/lib.rs)
defaults to **never asking for approval in headless mode**: actions requiring
sandbox escalation fail rather than receiving permission. Within-sandbox actions
can execute without a prompt. The top-level interactive `--ask-for-approval`
flag does not establish on-request behavior for exec and is deliberately absent.
Review this headless behavior before launch; if human approval prompts are
required, this recipe is blocked and needs a separately reviewed interactive
capture approach. Record denied/unsupported actions and stop; do not widen
permissions or enable automatic review to make the test run.

`--ignore-user-config` specifically skips `$CODEX_HOME/config.toml`, while
authentication still uses CODEX_HOME. `--ephemeral` avoids persisting session
files; it is not a promise of zero logs/state everywhere.
`-c mcp_servers.synthetic_memory={...}` supplies command, arguments, the two
`enabled_tools`, and `required=true` (server startup failure must not be silently
optional). `web_search="disabled"` and `project_doc_max_bytes=0` are supported
configuration keys. The empty case directory has no project configuration.
Managed configuration, parent directory instructions/configuration, hooks,
environment overrides and other native tools still require review.
Read-only sandboxing restricts writes; it does **not** imply that evaluator files
elsewhere are unreadable. `--skip-git-repo-check` permits the owned non-repository
case directory, not a sandbox bypass.

`exec --json` emits JSONL events. Version-tagged code maps MCP events to server,
tool, arguments, status, result content/structured content and errors. Capture
all events, not only the final answer. Match start/update/complete events by item
ID rather than counting them as separate calls. An interrupted/incomplete stream
does not prove retrieval. Usage may default to zero if no usage event arrived;
zero without supporting evidence is `UNVERIFIED`, not measured zero tokens.

## Six-case scoring protocol

After all gates are approved, use **one new process/session per case per client**.
Do not reuse conversation IDs, resume history, show one client's answer to the
other, or add case-specific hints. Both generated prompts are byte-identical.
The rubric remains the original six questions; this kit does not auto-grade
natural-language semantics by substring or ask a model to grade itself.

| Case | Required body IDs after the actual index call |
| --- | --- |
| latency-paraphrase | kst-001, kst-002 |
| code-to-log-correlation | kst-003 |
| missing-recent-event | kst-001, kst-004 |
| historical-data | kst-005 |
| missing-scope | kst-001, kst-002 |
| unknown-topic | None; still require index discovery and explicit knowledge limits |

The evaluator fills one generated result record using local trace references:

- Record client/runtime/server versions, requested/observed model, reasoning and
  context settings, exact nonsecret recipe overrides, effective tool/boundary
  review and fresh session identity. Unknown values remain `UNVERIFIED`.
- Record ordered actual `list_memory_index`/`get_memory` requests and complete
  responses, call IDs, errors and retries. Confirm project `sample-telemetry`,
  index success/count five, required IDs, indexed `expected_version`, and matching
  returned `source_version` against the manifest. Preserve the generated index
  result as trace evidence, not a separately curated answer source.
- Score required facts and forbidden claims individually from the original
  rubric, with answer excerpts and trace references. Require final memory-ID
  citations for supported facts; citations cannot substitute for tool evidence.
  For the unknown topic require explicit limits and a request for a source,
  without fabricated policy/dashboard claims or invented memory citations.
- Record every additional body ID, its relevance rationale, and the count of
  unrelated reads. Extra reads are not silently ignored. Count tool errors,
  failed/incomplete calls and non-memory tool access separately.
- Record UTC start/end and monotonic wall duration, tool duration where actually
  observable, index UTF-8 bytes, client-reported token usage and tokenizer
  identity. Index-only token counts require an identified matching tokenizer;
  total client input usage is not index token count. Missing timing/token data
  stays null/`UNVERIFIED`, not inferred from character counts or SDK timing.

A case passes only when required retrieval, source versions, citations, all
required facts, no forbidden claims and an established non-leaking boundary
are evidenced. Report relevance/extra reads and latency/token gaps independently.
Missing evidence is `UNVERIFIED`; observed incorrect behavior is `FAIL`; no
launch is `NOT_RUN`. Do not average missing runs into a success rate.

## Disconnect observation and cleanup

Do not change host clients' termination settings or run forced-termination
experiments in this preparation task. In a later approved run, record normal
exit versus interruption, whether final trace/usage events flushed, server exit
and any generic cleanup-pending diagnostic. If exact owned process handles are
observable, record whether server and worker exit were confirmed; otherwise
mark cleanup `UNVERIFIED`. Never kill unrelated/name-matched processes.

The server retains worker ownership on graceful EOF, but clients may force-kill
the server/tree before cleanup is confirmed. SDK tests do not establish either
client's real termination policy, provider cancellation or no orphan guarantee.
Do not turn a missing final trace into a success-shaped fallback.

Generated artifacts are deliberately retained. For cleanup, first confirm
clients/server workers are stopped, inspect the exact owned child, and reject
reparse points. Remove only its known generated files and then empty directories;
stop on unexpected entries. No recursive wildcard/junction-following cleanup
or root/session-directory deletion is supplied. Tests track and remove their
own generated fixture files/directories.

## Preparation evidence

```powershell
.\.venv\Scripts\python -B -m pytest -q tests\test_real_client_kit.py
```

Observed: **8 passed**; combined kit/protocol/supervisor regression selection
**52 passed**. Checks cover body fidelity, five eligible notes, source
hashes, prompt parity, rubric separation, gated/least-privilege recipe shape,
TOML parsing, no environment-value copying, existing-output refusal,
out-of-parent refusal, simulated reparse-ancestor
rejection, LF/CRLF preservation, explicit CLI failure, and an actual MCP SDK
subprocess index/get roundtrip over all five generated notes. A successful
preparation command also produced an owned session-local kit without launching
either coding client. Generated recipe syntax/flags are grounded in the
help/schema evidence above; all 156 flag occurrences across the twelve recipes
were also checked against installed client help. **Actual client acceptance
remains unexecuted**.
No full packaging rebuild was needed: runtime/packaging files did not change.
