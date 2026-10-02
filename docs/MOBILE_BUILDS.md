# Build installable phone applications

## Android

Requires Android SDK 36, JDK 17, Gradle 9.3.1 and network access to dependency
registries. The tunnel library is pinned to the published `1.0.20260102` artifact.

From `android/`:

```bash
gradle --no-daemon assembleDebug lintDebug
```

The private test APK is `app/build/outputs/apk/debug/app-debug.apk`. Install it
through Android Studio or `adb install`. The debug signing identity is for
testing, not a stable public release identity.

The included `.github/workflows/android.yml` performs the same build and uploads
that APK as an Actions artifact. Place this package's **contents** at the root
of a dedicated repository and run the workflow. It has not been run in this
environment. Download the artifact from that workflow's completed run; no APK
is included in this ZIP.

For an owner-signed release, create and protect your own signing keystore, set
`NEXUS_KEYSTORE` (absolute path), `NEXUS_STORE_PASSWORD`, `NEXUS_KEY_ALIAS`, and
`NEXUS_KEY_PASSWORD`, then run `gradle assembleRelease bundleRelease`. Keep
keystores and passwords out of the repository and source ZIP. Changing a release
key or application ID affects update compatibility.

The session supervisor uses Android's declared `specialUse` foreground type
with a persistent disconnect notification. Google reviews that declaration for
Play distribution. Validate it on current Android versions. Always-on, lockdown
and unattended reconnect are deliberately disabled; this is not a kill switch.
The app handles OS VPN revocation by stopping the session supervisor. Verify
this behavior on devices before any public release.

Compatibility: Android 8+ (API 26). Existing WireGuard full-tunnel profiles with
one peer and explicit DNS can still be imported. Importing uses the key already
in that profile; secure local generation is provided by Nexus enrollment.

## iPhone

Requires a Mac, Xcode, Go, XcodeGen and dependency-network access. In `ios/`, run:

```bash
brew install xcodegen
bash prepare.sh
open WireGuardNexus.xcodeproj
```

The preparation script checks out a fixed upstream WireGuard Apple commit.
The XcodeGen project includes a SwiftUI app, an embedded packet-tunnel extension,
shared Keychain access and the Go bridge build phase. The old upstream Go bridge
requires Go-runtime patches; the CI workflow selects Go 1.19.13 for compatibility.
Validate that dependency/toolchain on a Mac and review updates before shipping.

Set your team in Xcode and choose unique app and extension bundle identifiers.
The extension ID must be the app's ID plus `.tunnel`. Update the shared Keychain
group in `project.yml` consistently for both targets and regenerate the project.
Provision both with the packet-tunnel Network Extension and shared Keychain
entitlements. The app stores a persistent Keychain reference in VPN preferences;
it does not store the private key in those preferences.

The workflow `.github/workflows/ios.yml` attempts an unsigned device-SDK build
for compile validation. An unsigned build cannot be installed on an ordinary
iPhone. Produce an owner-signed Archive and upload it to TestFlight for testing,
then submit an App Store release after passing device tests and review.

Compatibility: iOS 16+. This beta supports Nexus enrollment, not arbitrary
WireGuard profile import. The UI shows OS tunnel state. It does not implement
an iOS kill switch, on-demand policies, traffic charts or subscriptions.

For a public VPN service, verify Apple's current organization-enrollment and
VPN disclosure rules at https://developer.apple.com/app-store/review/guidelines/#vpn-apps.
Developer account access and signing certificates are not supplied by this package.

## Required phone tests

Test both platforms with a real node: enrollment consent, private-key locality,
lost-response retry, expired invitation, connection establishment, DNS and IPv6
leaks, server failure, traffic, sleep, captive portals, cellular/Wi-Fi changes,
OS VPN revocation, device removal and app upgrades. Build success alone is not
evidence these behaviors work.
