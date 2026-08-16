# GraphLean v1.0.0

**GraphLean v1.0.0** is the first public release. It provides minimal-context execution graphs with host-enforced constraints for DeepSeek Harness.

The graph, policy checks, budgets, approvals and runtime state remain in the host. In v1.0.0, the model-visible control surface is five tools with 1,702 bytes of serialized tool metadata; the ten executable graph templates occupy 49,380 bytes on the host side. These are byte counts, not token counts.

At the host boundary, the release enforces graph progression, tool effect classes, workspace/control-plane boundaries, session isolation, privileged activation, admission-time parallel/total call budgets, result binding and approval-bound self-evolution.

### Install

Native DSH bundle:

```bash
dsh plugin --profile web add ./graphlean-1.0.0.tgz
dsh --profile web --dump-config
```

Transactional machine-wide install:

```bash
./INSTALL_UNIX.sh
# Windows: INSTALL_WINDOWS.cmd
```

### Release boundary

The release pipeline passes 37/37 behavior/security/context/graph/privacy/installer tests. It also passes 10/10 executable graph validations and 6/6 quality-pattern validations; bundle inspection, deterministic packaging and transactional rollback passed as well. If the build machine has no real `dsh` executable, this release does not claim a real Harness boot. Run `SELFTEST.py --target <DSH_HOME> --probe-dsh --profile web` on the target machine for that check.

For scope and limitations, see `README.md`, `SECURITY.md`, and `docs/RELEASE_VALIDATION.md`.

