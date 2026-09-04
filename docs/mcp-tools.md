# MCP tool contracts

All tools require a repository remote. The server resolves it to an internal repository ID before application logic runs. Knowing another repository's memory or candidate ID never bypasses scope checks.

The normative M0 artifact is [`contracts/mcp-tools.manifest.json`](../contracts/mcp-tools.manifest.json). This document explains its intent; implementations must conform to the frozen JSON Schemas and error codes in that manifest.

## `resolve_repository`

Input:

```json
{ "remote_url": "string" }
```

Returns the canonical provider identity, display names, and whether resolution used a stored alias or the Azure DevOps API.

## `search_memories`

Input:

```json
{
  "remote_url": "string",
  "query": "string",
  "kinds": ["decision"],
  "tags": ["kusto"],
  "limit": 5,
  "cursor": "opaque optional string"
}
```

Returns approved active candidates only: ID, kind, title, summary, matching snippet, tags, provenance summary, update time, and lexical score. It never returns the full Markdown body.

## `get_memory`

Input:

```json
{ "remote_url": "string", "memory_id": "uuid" }
```

Returns one complete Markdown memory and its lifecycle/provenance metadata after rechecking repository scope.

## `propose_memory`

Input:

```json
{
  "remote_url": "string",
  "operation": "create | supersede | archive",
  "target_memory_id": "optional uuid",
  "kind": "decision | pitfall | convention | procedure",
  "title": "string",
  "summary": "string",
  "body_markdown": "string",
  "tags": ["string"],
  "source_commit": "optional string",
  "source_branch": "optional string",
  "source_paths": ["string"],
  "source_url": "optional URL",
  "reason": "optional string"
}
```

Returns an unpublished candidate with an exact normalized preview, revision, and possible duplicates.

## `list_memory_candidates`

Input:

```json
{ "remote_url": "string", "status": "pending | approved | rejected | expired" }
```

Returns candidate summaries and exact review previews.

## `decide_memory_candidate`

Input:

```json
{
  "remote_url": "string",
  "candidate_id": "uuid",
  "expected_revision": 1,
  "decision": "approve | reject",
  "comment": "optional string"
}
```

The final decision cannot alter candidate content. Approval atomically creates, supersedes, or archives memory and writes an audit event.

This tool must advertise mutating/destructive annotations. MCP cannot prove a human clicked approval, so target clients must not auto-approve it.

## Error codes

Application errors use stable names in tool content:

- `INVALID_REMOTE`
- `UNSUPPORTED_REMOTE`
- `REPOSITORY_RESOLUTION_REQUIRED`
- `REPOSITORY_RESOLUTION_FAILED`
- `UNAUTHENTICATED`
- `FORBIDDEN`
- `NOT_FOUND`
- `REVISION_CONFLICT`
- `INVALID_CANDIDATE_STATE`
- `VALIDATION_ERROR`
- `DEPENDENCY_UNAVAILABLE`
- `INTERNAL_ERROR`
