# ADR 0001: Azure DevOps repository identity

- Status: Accepted
- Date: 2026-09-04

## Context

The same Azure DevOps repository can be cloned with HTTPS, legacy Visual Studio, SCP-like SSH, or URI-form SSH remotes. Names may later change. Using a normalized URL as the durable key would create duplicate memory or lose continuity after a rename.

## Decision

Use a two-stage identity model:

1. Parse a supported remote into an Azure DevOps locator containing organization, project, and repository names.
2. Resolve that locator through the Azure DevOps Git Repositories API and use the returned repository GUID as the durable identity.

The canonical external identity is:

```text
azure-devops:{repository-guid}
```

The database stores project GUID, current display names, and sanitized locator aliases. Unknown locators must resolve online before registration. If the Azure DevOps API is unavailable, only an existing alias may be used.

## Supported remote forms

```text
https://dev.azure.com/{organization}/{project}/_git/{repository}
https://{organization}@dev.azure.com/{organization}/{project}/_git/{repository}
https://{organization}.visualstudio.com/{project}/_git/{repository}
git@ssh.dev.azure.com:v3/{organization}/{project}/{repository}
ssh://git@ssh.dev.azure.com/v3/{organization}/{project}/{repository}
```

## Security rules

- Reject unknown hosts and path grammars.
- Strip credentials, query, fragment, default ports, trailing slash, and optional `.git`.
- Decode each path segment once and reject empty, dot, or invalid encoded segments.
- Never store the original credential-bearing URL.
- Treat organization comparison as case-insensitive while retaining display casing.
- Fail when the API response does not match the requested locator.

## Consequences

- HTTPS and SSH aliases converge after one verified API lookup.
- Repository renames preserve memory because the GUID remains the key.
- First use requires an Azure DevOps credential; known aliases continue to work without an API call.
- Supporting another Git provider requires a new parser/resolver adapter, not changes to memory storage.
