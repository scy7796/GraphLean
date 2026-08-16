# Security Policy

GraphLean is a DeepSeek Harness host-governance plugin, not an operating-system sandbox.

## Reporting

For a suspected security vulnerability, prefer GitHub private vulnerability reporting / a private security advisory if enabled for the repository. Do not publish a working exploit, credentials, private prompts, proprietary source, or local GraphLean/DSH state in a public issue before a fix is available.

Include the GraphLean version, DSH version, operating system, minimal reproduction, expected host decision, observed host decision, and whether the issue crosses the documented trusted-computing boundary.

## Default hard-deny surfaces

The hard-governance profile denies unbounded/composite surfaces such as `run_code`, shell/terminal execution, dynamic Cordis execution/introspection, workflow, Ralph, and DSH Skill execution. Built-in protected classifications cannot be downgraded through normal GraphLean configuration.

## Trusted computing base

GraphLean relies on DeepSeek Harness core and ToolExecution semantics, Node.js, the operating system, the configured filesystem/tool providers, local state integrity, and administrator-installed plugins/configuration. A compromise below this boundary is outside the plugin's guarantee.

## Release hygiene

The release pipeline rejects common credential files and high-confidence secret patterns, symlinks, path traversal, cache/bytecode artifacts, and leaked user-home paths. Runtime receipts are designed to persist hashes and governance metadata rather than raw prompts, arguments, results, or source bodies.

