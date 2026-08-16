# GraphLean Release Gates

A higher-level benchmark never waives a lower-level failure.

## P0 — artifact blockers

All must pass before an artifact is published:

1. clean release integrity and privacy scan;
2. 10/10 graph runtime + JSON Schema validation;
3. reproducible minimal-context surface measurement with no GraphLean prompt-policy injection;
4. Node host-gate behavior tests with no skipped core tests;
5. privileged activation cannot bypass the host approval + monotonic guard chain;
6. workspace/control-plane escape attempts are denied for governed built-in file tools;
7. fork/join and optional-branch scheduling remain valid;
8. session state, approval, receipts and pending reservations do not cross sessions;
9. parallel/total tool budgets do not oversubscribe under tested admission races;
10. self-evolution mutation must match the approved ordered action sequence exactly;
11. installer or loader-probe failure restores the exact preimage;
12. official `dsh.bundle` package/patch contract validates;
13. final staged artifact passes `SELFTEST.py`, Node syntax, bundle inspection and checksum verification.

Any P0 failure means **DO NOT RELEASE**.

## P1 — target compatibility acceptance

These checks depend on the deployment machine / selected DSH release train and are not faked by a source-only build environment:

- GitHub CI green on Windows, macOS and Linux;
- Python 3.9 and 3.12 matrix green;
- Node 22.19+ contract green;
- real target `dsh --dump-config` loader probe green;
- one real governed DSH session exercises begin → tool → result → advance → close;
- one real install/uninstall round trip on the target OS.

The one-click installer performs the real loader probe when `dsh` is available and rolls back on failure.

## P2 — comparative benchmarks

Useful for performance/comparison claims, but never a substitute for P0/P1 evidence:

- vanilla DSH vs GraphLean admission overhead (median/p95/p99);
- larger adversarial mutation/privilege suites;
- concurrent admission stress;
- cross-session stress;
- extended self-evolution tamper/replay suites.

README superiority or performance claims must come from executed evidence, not source inspection.

