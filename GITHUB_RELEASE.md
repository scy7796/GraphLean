# GraphLean v1.0.1

v1.0.1 is a release-engineering and compatibility-precision patch for **GraphLean**, the minimal-context host-enforced execution-graph layer for DeepSeek Harness.

The host governance model remains fail-closed. This patch does not weaken shell/Code Mode/dynamic-execution denial or approval boundaries to make CI pass.

## What changed

- separated source-checkout privacy validation from strict staged-release validation;
- stopped committing generated `dist/`, root `MANIFEST.json`, and root `CHECKSUMS.sha256`;
- normalized repository text through `.gitattributes` with LF source bytes;
- fixed cross-platform physical-path assertions for Windows 8.3 aliases and macOS `/var` → `/private/var` canonicalization;
- corrected the context benchmark to the actual DSH native wire schema: five controls / **1,587 bytes**;
- instrumented the **0-byte** system-prompt injection claim rather than hard-coding it;
- clarified that fork/join dependencies are deterministically scheduled, not simultaneous branch execution;
- clarified that `max_total_latency_ms` is an admission/advance deadline, not forced interruption of an already-running tool;
- documented the DSH presentation boundary: `native` supported/recommended, `both` supported with `run_code` denied, pure `code` unsupported by the hard-governance profile;
- made the tag workflow rerun the complete Windows/macOS/Linux × Python 3.9/3.12 matrix before release;
- made GitHub Releases draft-first, then re-download and byte-verify uploaded assets before publishing.

## Install

Native DSH bundle:

```bash
dsh plugin --profile web add ./graphlean-1.0.1.tgz
dsh --profile web --dump-config
```

Or use the transactional one-click installers in the source ZIP.

## Release boundary

The GitHub tag workflow is the authority for hosted-release status. A local release build proves the staged artifact only; it is not represented as evidence for a later GitHub-hosted tag. A real DSH boot is claimed only when `dsh --profile <profile> --dump-config` is actually executed successfully on the target environment.

See `README.md`, `SECURITY.md`, and `docs/RELEASE_VALIDATION.md` for the exact scope and limitations.
