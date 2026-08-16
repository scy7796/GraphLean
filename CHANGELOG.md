# Changelog

## 1.0.0 — first public release

- Introduced **GraphLean**, a minimal-context, host-enforced execution-graph layer for DeepSeek Harness.
- Kept graph policy and runtime state host-side: no standing GraphLean system-prompt policy block; five model-visible control tools form the bounded governance surface.
- Added a reproducible context-surface benchmark and release gate (`benchmarks/context-surface.json`).
- Shipped ten executable graph templates under one schema/runtime contract, including graph-encoded self-evolution.
- Added host-side effect classification, workspace/control-plane boundaries, session isolation, approval-bound privileged activation, admission-time call budgets, exact result reservations, hash-only receipts, and crash-ambiguity recovery.
- Added exact ordered mutation approval and review-packet binding for self-evolution.
- Added a standard DeepSeek Harness `dsh.bundle` package plus a transactional machine-wide one-click installer with preimage backup, installed-state verification, optional real DSH loader probe, and rollback.
- Added deterministic ZIP/TGZ release generation, bundle inspection, cross-platform CI, privacy scanning, security documentation, and fault-injection tests.

