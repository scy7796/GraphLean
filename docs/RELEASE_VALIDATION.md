# Release Validation — v1.0.1

This file records what the release gate proves and where the evidence stops. v1.0.1 separates source-checkout validation from staged-release validation; a normal `.git` checkout is not itself treated as a release payload.

## P0 gates

The release is blocked unless all of the following pass:

- the Windows/macOS/Linux × Python 3.9/3.12 tag matrix;
- all ten executable graphs against the runtime contract and Draft 2020-12 JSON Schema;
- every legal optional-branch activation with exactly one root, one sink and a complete deterministic schedule;
- all six quality-pattern descriptors;
- the instrumented GraphLean context-surface benchmark;
- Node syntax and behavioral host-gate tests at the declared DSH minimum Node 22.19.0;
- the root `dsh.bundle` manifest and exact bundle patch;
- source-tree privacy scanning that ignores only development substrate (`.git`, generated `dist`, build/cache directories);
- strict staged-release privacy scanning that rejects those same paths, symlinks, bytecode, secret-bearing filenames, high-confidence credential patterns and leaked user-home paths;
- the transactional installer install → validate → uninstall exact-preimage smoke, including fault injection;
- `MANIFEST.json` and `CHECKSUMS.sha256` exactly covering the staged payload;
- two independent npm packs and two deterministic source ZIP builds producing identical bytes;
- GitHub Release assets being downloaded after upload and matching the locally staged asset hashes before the draft is published.

Generated `dist/`, `MANIFEST.json`, and `CHECKSUMS.sha256` are release outputs. They are not source-of-truth files committed to the repository.

## Context-surface evidence

`node benchmarks/measure-context-surface.mjs` loads the actual plugin, captures definitions registered through `ctx.tools.register`, projects only the fields in DSH `ToolSchema` (`name`, `description`, `parameters`), and instruments GraphLean `systemPrompt.section` registrations.

The v1.0.1 checked-in result is:

- GraphLean system-prompt policy injection: **0 bytes**, observed from **0 registered GraphLean prompt sections**;
- model-visible GraphLean control tools: **5**;
- native DSH model-visible control-tool schema: **1,587 bytes**;
- host-side executable graph templates: **10**;
- bundled host-side graph JSON: **49,380 bytes**.

These are serialized byte counts, not tokenizer counts, and do not include DeepSeek Harness base tools, conversation history or provider framing.

## Scheduling and deadline semantics

GraphLean enforces fork/join dependency structure, but the current runtime advances one deterministic `currentNode` at a time. `multi-artifact` therefore has fork/join graph semantics with deterministic branch scheduling; it is not a claim of simultaneous branch execution.

`max_total_latency_ms` is checked at governed call admission and graph advance. It does not forcibly cancel a tool that was already executing when the deadline elapsed.

## DSH presentation compatibility

The hard-governance profile targets DSH native tool presentation. `both` mode can be used, but `run_code` remains hard-denied. Pure `code` mode is not supported because its reserved `run_code` transport is intentionally outside GraphLean's allowed bounded native execution surface.

## Local release evidence

A release build must record the exact test totals and artifact hashes from `RELEASE.py`. The repository does not treat a historical local run as proof that a later GitHub tag or hosted asset passed. GitHub-hosted evidence is established only by the tag workflow for that exact commit.

## Real DSH loader boundary

A source/bundle test is not the same as booting a particular DeepSeek Harness binary.

When `dsh` is available on the target machine, the one-click installer executes:

```bash
dsh --profile <profile> --dump-config
```

and rolls back if the loader probe fails. The same check is available explicitly:

```bash
python SELFTEST.py --target <DSH_HOME> --probe-dsh --profile web
```

If the release build environment has no compatible `dsh` binary, this document does not claim a real DSH boot occurred there.

## Not proven

The test suite does not prove model reasoning is correct, provide an OS sandbox, protect against a malicious kernel/filesystem provider/DSH core/administrator, provide exactly-once semantics across a crash after an external side effect, or guarantee confidentiality for data independently logged by DSH, providers or external tools.
