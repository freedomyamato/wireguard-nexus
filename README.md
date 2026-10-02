# WireGuard Nexus 0.2 — invitation-only VPN beta

[![Android and server tests](https://github.com/freedomyamato/wireguard-nexus/actions/workflows/android.yml/badge.svg)](https://github.com/freedomyamato/wireguard-nexus/actions/workflows/android.yml)
[![iOS compile](https://github.com/freedomyamato/wireguard-nexus/actions/workflows/ios.yml/badge.svg)](https://github.com/freedomyamato/wireguard-nexus/actions/workflows/ios.yml)

This extends the earlier Android import prototype into a single-node VPN
platform with a tested enrollment API, device administration, a restricted Linux
agent, and native Android/iPhone source integrations.

**Android test APK available:** compilation and lint passed on GitHub Actions;
all 14 server tests passed. Download `nexus-android-debug` from the
[successful Android build](https://github.com/freedomyamato/wireguard-nexus/actions/runs/36980297739)
and extract `app-debug.apk`. This artifact expires on October 9, 2026; rerun the
Android workflow to produce a fresh build. See [phone build instructions](docs/MOBILE_BUILDS.md).

The [unsigned iPhone compile check](https://github.com/freedomyamato/wireguard-nexus/actions/runs/36980841668)
also passed, including the packet-tunnel extension and Go bridge. No hosted VPN
service, signed iPhone release or app-store listing is included. Public use still requires
physical-device/tunnel testing, hosting, owner release signing and store review.
This is a single-node beta; it does not implement the commercial multi-node roadmap.

## What is implemented

| Component | Included behavior |
| --- | --- |
| Controller | SQLite state, expiring single-use invitations, atomic enrollment, retry handling, device authentication, desired/applied revocation, audit events |
| Linux agent | Local protected Unix socket, constrained key/address validation, real `wg syncconf` integration, persistence and attempted rollback |
| Administrator page | HTTPS reverse-proxy deployment, invite creation, device listing and revocation |
| Android source | Local key generation, HTTPS enrollment, encrypted local keys, profile import, VPN consent, WireGuard engine, session notification and traffic counters |
| iPhone source | Local key generation, HTTPS enrollment, shared Keychain, native packet-tunnel provider and VPN preference management |
| Deployment | Debian/Ubuntu bootstrap, systemd units, separate interface/firewall, Caddy site configuration |
| CI | Android APK/server-test workflow and unsigned iOS compile workflow |

## Start here

1. Read [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) to prepare a private node.
2. Read [docs/MOBILE_BUILDS.md](docs/MOBILE_BUILDS.md) to produce installable test apps.
3. Enroll one test phone, verify real tunnel traffic, then verify revocation.
4. Complete the checks in [docs/VERIFICATION.md](docs/VERIFICATION.md) before a public launch.

Run local service tests without external dependencies:

```bash
cd server
python3 -m unittest discover -s tests -v
```

The controller and agent use the Python standard library, allowing actual tests
in this environment. This changes the initial proposed Go stack for the beta;
the native WireGuard engine remains unchanged. The controller is non-root and
the colocated privileged agent accepts only peer reconciliation. Remote mTLS
node management is not implemented in this single-node version.

## Limits

No public signup, passkeys, MFA, multi-node selection, mobile QR scanner, DNS
filtering service, per-device routing policy, kill switch, payment system,
automatic update or encrypted-backup command is included. It is an invitation-only,
internet-egress beta. No connection speeds, regions or uptime are simulated.

The upstream installer inspired the compatibility path, but this package does
not modify or incorporate that third-party repository. Nexus owns its separate
`nexus0` interface. Keep dependency licenses/notices with redistributed binaries.

## Primary references

- https://github.com/hwdsl2/wireguard-install
- https://www.wireguard.com/embedding/
- https://github.com/WireGuard/wireguard-android
- https://github.com/WireGuard/wireguard-apple
- https://developer.android.com/develop/background-work/services/fgs/service-types
- https://developer.apple.com/app-store/review/guidelines/#vpn-apps

Original Nexus source is MIT licensed; see LICENSE. Treat operator credentials,
server private keys and release signing identities as owner-controlled secrets.
