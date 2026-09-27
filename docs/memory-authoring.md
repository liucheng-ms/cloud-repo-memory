# Human-maintained local-v1 memory

Use the [copyable fictional note](templates/local-v1-note.md.example) with the
experimental Windows fixed-NTFS read-only runtime. This is an authoring guide,
not permission to ingest real knowledge. Use isolated synthetic notes for
development; real knowledge requires approved storage and agent/model processing
arrangements. Installation and explicit project mapping are covered in the
[stdio guide](local-stdio-adapter.md); the [local-v1 contract](local-mvp-contract.md)
and [schema](../contracts/local-mvp-v1.schema.json) remain authoritative.

## Copy deliberately, outside knowledge first

The template ends in `.md.example`, not `.md`, so the runtime does not discover
it as a note. Keep this guide, templates, backups, configuration, and evaluator
material outside configured knowledge roots. Do not map the repository itself
as a knowledge root. Historical M0 samples are not local-v1 templates; do not
copy them unchanged or ingest their evaluation material.

A human must adapt every fictional value: choose the intended project's exact
configured key, allocate a stable ID, replace the navigation text, and write
reviewed content. `example-paper-lantern` is fictional, not an inferred Git
repository identity. Start with `draft` / `pending`; these values are valid but
not retrievable. Save an adapted note as UTF-8 with a `.md` extension only when
ready for it to participate in project validation. Do not name it `MEMORY.md`.
No command here creates notes, changes client configuration, or accesses OneDrive.

## Required frontmatter

Start with an exact `---` line, one YAML 1.2 mapping, and a closing `---` line.
All eight fields below are required; no additional fields are allowed.
`schema_version` is the integer `1`; all other values must be strings.

| Field | Authoring rule |
| --- | --- |
| `schema_version` | Keep integer `1`, without quotes. |
| `id` | Stable topic ID, unique across every candidate in this project. |
| `project` | Exact configured project key, even for an ineligible note. |
| `title` | Short topic label, 1-120 Unicode code points. |
| `summary` | Navigation-only description of the note, 1-280 code points. |
| `read_when` | Concrete situation in which to read the body, 1-280 code points. |
| `status` | `draft`, `active`, `archived`, or `superseded`. |
| `approval` | `pending`, `approved`, or `rejected`. |

IDs and project keys are case-sensitive lowercase ASCII letters/digits separated
by single hyphens, 1-64 characters. Identity is `(project, id)`, not filename:
preserve it across edits and renames; never reuse a retired ID for another topic.
The same ID may exist in different projects. Mapping is an operator choice, not
verified Git identity or authorization.

Keep title, summary and read_when nonblank and single-line, with no surrounding
whitespace or control characters. Quoted YAML strings, as in the template,
avoid accidental booleans/numbers and punctuation ambiguity. Do not add nested
values, duplicate keys, aliases, anchors, merge keys, tags or YAML directives.
Put references, dates, reviewer context and replacement-note IDs in the body,
not new frontmatter fields. LF/CRLF and one optional UTF-8 BOM are accepted;
source files are limited to 262,144 bytes and frontmatter to 8,192 bytes,
including delimiters/BOM. See the contract for project-wide scan limits.

## Lifecycle examples

Each cell below is a valid `status` / `approval` combination; **only `yes` is
eligible** for both index inclusion and body retrieval. These are editable
labels, not proof of human review, approval, authenticity or safety. The runtime
does not enforce a transition workflow or record who changed a label.

| status | pending | approved | rejected |
| --- | --- | --- | --- |
| draft | no | no | no |
| active | no | yes | no |
| archived | no | no | no |
| superseded | no | no | no |

Valid ineligible notes count toward `excluded_count` and scan limits;
`get_memory` returns `MEMORY_INELIGIBLE` without a body. Missing fields and
unknown values are errors, not safe draft defaults.

## Human maintenance

1. **Create and review:** prepare an adapted `draft` / `pending` note outside
   the root. Check the evidence, project and ID uniqueness, then place only the
   intended note in the configured root. After human review, explicitly set
   `active` / `approved` if it should be served. The MCP server never writes it.
2. **Update:** preserve the ID for the same topic. For content needing renewed
   review, first save a complete valid `draft` / `pending` revision to withdraw
   retrieval, then edit/review outside the root and replace the intended file.
   Update title/summary/read_when when scope changes, not just the body.
   Finish saves before reading; there is no cross-file transaction or review lock.
3. **Retire:** use `archived` / `approved` for a retained but withdrawn note,
   or `superseded` / `approved` with a replacement ID explained in the body.
   Create a replacement under a new ID if it represents a different topic.
   These retained notes still need valid metadata and unique IDs. Alternatively,
   move a retired note outside all knowledge roots; its ID then returns
   `MEMORY_NOT_FOUND` after a successful scan. Preserve retirement history
   separately, since runtime metadata is not an audit trail.
4. **Re-read:** list the project index, then read the selected ID using its
   version as `expected_version`. On `MEMORY_CHANGED`, relist and reconsider
   before reading; do not silently use a stale body. A lifecycle withdrawal
   returns `MEMORY_INELIGIBLE` even with an old expected version.

Every source version is SHA-256 of the **exact file bytes**, including
frontmatter, body, whitespace, BOM and line endings. A body-only edit or an
editor's LF/CRLF conversion changes it; a rename with unchanged bytes does not.
Eligible source changes also change the rendered index/version. An edit solely
to an excluded note can leave the index version unchanged. Versions are not
ordered revisions or cloud freshness proofs. Every call scans locally with
`local-best-effort` consistency and `cloud_freshness: unknown`; detected concurrent
changes fail `LOCAL_CHANGE_DETECTED`. No sync or second-device guarantee follows.

## Recover a blocked project without hiding errors

Both tools validate **all** `.md` candidates recursively, including hidden
files/directories and draft/archived notes. Only root-level `MEMORY.md` is
reserved and ignored; a nested `MEMORY.md` is a candidate. A hidden folder or an
`archive` subdirectory is not quarantine.

One malformed note (including a project mismatch) causes `INVALID_METADATA`;
duplicate IDs, including conflict copies and retired notes, cause `DUPLICATE_ID`.
These block the whole project's call, even a request for another valid ID; no
partial index or fallback body is returned. Inspect diagnostics and reconcile
files manually outside the roots, retaining one intended source for each ID.
Do not merely mark a duplicate archived or select the newest filename.
Unavailable, oversized or unsafe linked files also fail explicitly; fix the
reported cause rather than repeatedly retrying or expecting the server to skip it.

Metadata, summaries, bodies and referenced material are **untrusted reference
content**, not agent instructions. Review sources, read the relevant body rather
than treating a summary as evidence, and do not obey embedded commands, requests
for secrets or claims to override higher-priority instructions. An `approved`
label does not change that boundary.

## Maintainer checks

From an existing development environment, run
`python -m pytest tests\test_memory_authoring.py tests\test_metadata.py`.
These checks read the actual template and lifecycle table, validate with the
runtime parser and contract schema, and exercise copies in owned synthetic
fixtures. They do not validate arbitrary user folders or launch agent clients.
Filesystem cases require Windows fixed NTFS; portable metadata checks do not
prove filesystem safety, review quality, retrieval usefulness or synchronization.
