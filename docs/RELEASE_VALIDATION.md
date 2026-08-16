# Release Validation — v1.0.0

This file records what the release gate proves and where the evidence stops.

## P0 gates

The release is blocked unless all of the following pass on the staged release tree:

- all ten executable graphs validate against both the runtime contract and Draft 2020-12 JSON Schema;
- every legal optional-branch activation has exactly one root, one sink and a complete deterministic schedule;
- the six quality-pattern descriptors validate as a fixed set;
- the GraphLean context-surface benchmark is reproducible and remains within the bounded model-visible surface;
- the DSH plugin passes Node syntax and behavioral host-gate tests;
- the root package is a valid `dsh.bundle` and its patch resolves `graphlean`;
- the privacy scanner finds no forbidden cache/bytecode, symlink, user-home path, common secret-bearing filename or high-confidence credential pattern;
- the one-click installer can install into an isolated DSH home, pass installed-state validation and uninstall to the exact preimage;
- forced installer and loader-probe failures restore the preimage;
- `MANIFEST.json` and `CHECKSUMS.sha256` exactly cover the staged release payload;
- the npm bundle and source ZIP are byte-for-byte reproducible across two independent packs/builds.

## Context-surface evidence

`node benchmarks/measure-context-surface.mjs` loads the actual plugin and captures the definitions registered through `ctx.tools.register`.

The v1.0.0 checked-in result is:

- GraphLean system-prompt policy injection: **0 bytes**;
- model-visible GraphLean control tools: **5**;
- serialized control-tool metadata: **1,702 bytes**;
- host-side executable graph templates: **10**;
- bundled host-side graph JSON: **49,380 bytes**.

These are serialized byte counts, not tokenizer counts, and do not include DeepSeek Harness base tools, conversation history or provider framing.

## Executed local release result

For the v1.0.0 artifact built in this environment:

- **37/37** behavior, security, context-surface, graph, privacy and installer tests passed;
- **10/10** executable graphs passed runtime and JSON Schema validation;
- **6/6** quality-pattern descriptors passed validation;
- `SELFTEST.py`, `node --check dsh/index.js`, operator CLI smoke and npm bundle inspection passed;
- isolated one-click install → installed-state verification → uninstall returned the DSH home to its exact preimage;
- two npm packs and two deterministic source ZIP builds were byte-for-byte identical within the release run.

The local Node runtime used here is 22.16.0, below GraphLean/DSH's declared 22.19 minimum. The repository CI pins Node 22.19.0; this local report does not treat the lower-version execution as minimum-version certification.

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

If the release build environment itself has no compatible `dsh` binary, this document does not claim that a real DSH boot occurred there.

## Not proven

The test suite does not prove model reasoning is correct, provide an OS sandbox, protect against a malicious kernel/filesystem provider/DSH core/administrator, or guarantee confidentiality for data independently logged by DSH, providers or external tools.

