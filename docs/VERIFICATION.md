# Verification record — 2026-10-02

## Verified in this environment

`python3 -m unittest discover -s tests -v` discovered 14 tests: **13 passed and
1 was skipped because the runtime denies Unix sockets**.

Passing coverage includes:

- invitation expiry, same-device retry and concurrent single-use redemption;
- credential ownership checks and rejection of client-private-key fields;
- real loopback HTTP enrollment, device lookup and administrator revocation;
- stale acknowledgment protection and pending state when the agent is unavailable;
- reconciliation acknowledgment and node-key mismatch using a loopback HTTP fixture;
- agent key/route validation, persistent file permissions, and attempted rollback
  after an injected live-update failure, using a command fixture.

The Unix-socket test is included and should run on normal Linux/GitHub Actions.
The TCP fixture verifies the wire protocol and state changes; it does **not**
verify Unix socket permissions or a live WireGuard interface.

Also passed:

- Python bytecode compilation of server modules;
- JavaScript syntax check for the administrator page;
- shell syntax checks for Linux bootstrap and iPhone preparation;
- XML parsing for Android manifest/vector resources;
- YAML parsing for both workflows and the XcodeGen project;
- source package archive integrity verification.

## Not verified / not performed

| Item | Reason |
| --- | --- |
| Android dependency resolution, compilation and lint | No Android SDK/Gradle; Gradle network download blocked |
| APK signing or installation | No compiled APK or owner release signing identity |
| iPhone compilation/archive/TestFlight | No Mac/Xcode or Apple provisioning |
| Actual WireGuard traffic, firewall, rollback or DNS/IPv6 | No provisioned Linux VPN node or physical test phone |
| Unix-socket transport in this runtime | AF_UNIX socket creation denied by the runtime |
| GitHub workflow execution | Connected account has no project repository; only an unrelated repository was visible |
| Hosting and public launch | No authorized server, domain, store accounts or production service identity supplied |

No upstream or unrelated GitHub repository was modified. Source syntax checks
and mocked command tests are not evidence a mobile binary compiles or a real
tunnel passes packets. No connection measurements or screenshots are fabricated.

## Release gates

1. Import the package into a dedicated project repository and pass the server and
   Android build workflow; run the unsigned iOS compile workflow on its Mac runner.
2. Fix any SDK/compiler/lint issues before describing either source project as buildable.
3. Provision the single-node beta, establish HTTPS, and confirm node synchronization.
4. Test both native apps on physical devices, including leaks, lifecycle and revocation.
5. Create owner-signed APK/AAB and iPhone Archive/TestFlight builds.
6. Complete current platform disclosures and store review before public distribution.

The original roadmap's multi-node routing, passkeys, policy engine, kill switch,
QR scanner, billing and backup automation remain outside this beta's implemented scope.
