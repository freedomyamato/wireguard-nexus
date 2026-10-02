# Verification record — 2026-10-02

## GitHub Actions checks passed

Repository: [freedomyamato/wireguard-nexus](https://github.com/freedomyamato/wireguard-nexus).

| Check | Result | Evidence |
| --- | --- | --- |
| Server unit and integration suite on Linux/Python 3.12 | All 14 tests passed; no skips | [Android/server workflow](https://github.com/freedomyamato/wireguard-nexus/actions/runs/36980297739) |
| Android dependency resolution and debug compilation | Passed; test-signed APK uploaded | [Android/server workflow](https://github.com/freedomyamato/wireguard-nexus/actions/runs/36980297739) |
| Android debug lint | Passed | Same workflow runs `assembleDebug lintDebug` |
| iPhone device-SDK compilation with Xcode 16.4 | Passed, unsigned app and packet-tunnel extension with WireGuard Go bridge | [iOS workflow](https://github.com/freedomyamato/wireguard-nexus/actions/runs/36980841668) |

The Android run used commit `a58dfb5cb1ca164923335ae80cf4f7f1e00baf4e`.
The iOS run used commit `1b5b700b3073816660ce77ba3b45e3492a0a6192`.
Subsequent documentation edits do not change either compiled application.

The APK extracted from the Actions artifact has SHA-256:

```text
acb10328c96408907868795baca52521417ba6427ba522bc01ff0d6792af626c
```

Artifact archive and APK integrity were checked. The APK includes WireGuard
native libraries for arm64-v8a, armeabi-v7a, x86 and x86_64. The GitHub artifact
expires October 9, 2026; rerun the Android workflow for another test build.

## Server test coverage

- Invitation expiry, same-device retry and concurrent single-use redemption.
- Credential ownership checks and rejection of client-private-key fields.
- Real loopback HTTP enrollment, device lookup and administrator revocation.
- Stale acknowledgment protection and pending state when the agent is unavailable.
- Reconciliation acknowledgment and node-key mismatch using an HTTP fixture.
- Real Unix-socket reconciliation transport on the GitHub Linux runner.
- Agent key/route validation, persistent file permissions, and attempted rollback
  after an injected live-update failure, using a mocked WireGuard command.

These tests do not verify a live WireGuard kernel interface or public traffic.
The earlier restricted runtime passed 13 tests and skipped Unix-socket creation;
the GitHub run now verifies all 14.

## Additional source checks

Python bytecode compilation, administrator JavaScript syntax, deployment and
preparation shell syntax, Android resource XML, workflow/project YAML and source
archive integrity checks passed. The preparation script's embedded Python also
passed a syntax check.

Build fixes committed to this repository select a compatible Mac runner, avoid
Android's obsolete `tools` SDK package, and apply two small compatibility fixes
to the pinned upstream WireGuard Apple checkout: the Swift manifest API version
and an explicit `sys/types.h` import. Upstream repositories were not modified.

## Still requires deployment and device validation

| Item | Current state |
| --- | --- |
| Android phone installation and actual tunnel use | Compiled APK available; not tested on a physical phone |
| iPhone installation, Archive and TestFlight | Compile passed; Apple signing/provisioning still required |
| Live WireGuard traffic, firewall, rollback, DNS and IPv6 | No VPN server/domain or test devices supplied |
| Stable Android release signing, APK/AAB and Play publication | Owner release keystore/store account required |
| Hosting and public launch | No production VPN node or app-store listing deployed |

## Release gates

1. Provision the single-node beta, establish HTTPS, and confirm synchronization.
2. Test both native apps on physical devices, including enrollment retries,
   traffic, DNS/IPv6 leaks, lifecycle changes and server-side revocation.
3. Create owner-signed Android release and iPhone Archive/TestFlight builds.
4. Complete platform disclosures and store review before public distribution.

The original roadmap's multi-node routing, passkeys, policy engine, kill switch,
QR scanner, billing and backup automation remain outside this beta's implemented scope.
