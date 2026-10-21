# Background Assets

These mechanisms and lessons apply when the stated capability is present. Original
measurements establish their recorded platform and workload; they do not establish
universal behavior on later operating systems or in a different application.

## Managed asset packs need an app group, a downloader extension and a guard

- Put `BAAppGroupID` in the app's Info.plist. Without it `AssetPackManager.shared` calls
  `fatalError`: it traps rather than throws, so check the precondition before the first touch of
  the manager, through one guard every caller shares.
- Embed a downloader extension whatever the packs' download policy, and declare it as an
  `extensionkit-extension` so it lands in `Extensions/`; installd rejects the `PlugIns/` shape.
  For Apple-hosted packs it conforms to StoreKit's `StoreDownloaderExtension`, the Apple-hosted
  specialization of `ManagedDownloaderExtension`. Its `shouldDownload(_:)` runs in the
  extension's process, so it reads the app's selection from the shared App Group.
- On macOS, `containerURL(forSecurityApplicationGroupIdentifier:)` returns a URL of the expected
  form even when the group is invalid. Before touching the manager, prove the container is
  writable (create it, then write and remove a probe file), retry briefly, and fail with a
  recoverable error.
- That probe does not catch every trap. On macOS 27.0 seed 26A5421a (August 2026) the manager
  trapped with "The app group … is inaccessible" for a team-prefixed group whose container
  existed and was writable. The trap did not reproduce on the next seed (26A5425a) and recurred
  once in September 2026 on a heavily loaded development Mac. Apple DTS attributed it to Launch
  Services resolving the wrong installed copy of the app or its downloader extension, a common
  state on a Mac holding several builds. No API pre-checks it; retest with a single copy in
  `/Applications`.
- Spell the App Group identically across the Info.plist, entitlements and code on each platform;
  see [app extensions](app-extensions.md).

Evidence: [studywright measurements/audits/os27-mac-assetpackmanager-appgroup.md](https://github.com/vocaro/studywright/blob/f1d1178e03949b2a6fb20dc6d85618988c0d01b2/measurements/audits/os27-mac-assetpackmanager-appgroup.md).

## A local pack and an openable pack are separate facts

- Background Assets reporting a pack as locally available does not mean its contents open.
  Validate the pack's content identity against the selection before loading it. If a pack that
  was already local fails to validate or open, remove it and download it again once, without
  looping. Leave a failed first download for Background Assets to resume, and never discard a
  pack on cancellation.
- An ordinary launch reads the system manifest without forcing a refresh. A retry for a missing
  pack calls `checkForUpdates()` before looking it up. A refresh error escapes without a
  download attempt, and a pack still absent after a successful refresh is reported as missing
  from the manifest. Coalesce duplicate retries into one refresh.
- Replace a pack by opening the new one first, then calling `remove(assetPackWithID:)` on the
  old. On failure, restore the previous selection and keep the partial transfer for resume.
- Managed packs take no priority (iOS 27 headers and swiftinterface): the managed surface is
  `ensureLocalAvailability(of:requireLatestVersion:)`, `BADownload.priority` is read-only, and
  only `BAURLDownload`, the self-hosted path, sets one. The one lever is handing
  `AssetPack.download(for:)` to `BADownloadManager.startForegroundDownload(_:)`. It starts at
  once regardless of battery or network, requires a foreground-active caller, and by its header
  stays in foreground mode until the manager disconnects. Urgency cannot be raised from the
  background.
- A pack can carry compiled Core ML models (`.mlmodelc`), so no first launch pays a compile;
  loading still specializes for the device.

## Development builds need a mock server and device-side overrides

A development build cannot receive Apple-hosted packs. Test through TestFlight, or serve packs
with `ba-serve` and point the device at it. Observed with `ba-serve` 2.0 betas and Xcode 27 in
2026:

- The device's override is set on the device, under Settings → Developer → Development
  Overrides, with the server's base URL including host and port. `ba-serve url-override` reads
  and writes only the Mac's own override. No command sets the device field:
  `backgroundassets-debug` only simulates extension events, and `devicectl device settings` does
  not cover it. A missing override looks like the app never becoming ready, not like an error.
- Pin the port with `-p`; without it `ba-serve` picks a random one. Pass
  `--choose-identity-automatically` when serving headless, or `ba-serve` posts a Choose An
  Identity dialog and blocks. It selects the keychain identity by the `--host` value, and a host
  the certificate does not name fails as "The specified item could not be found in the
  keychain".
- An unverified report says iOS may drop the override's port and fall back to 443.

```sh
xcrun ba-serve serve PACK.aar --host HOST -p PORT --choose-identity-automatically
```

Certificates:

- `ba-serve` presents a self-signed certificate. Safari lets a person accept it, but the
  downloader has no UI and fails. Install the profile on the device (Settings → General → VPN &
  Device Management), then enable full trust under Settings → General → About → Certificate
  Trust Settings; an installed but untrusted root behaves like none. The passcode and the trust
  toggle need the owner's own touch.
- The certificate must name the served host in `subjectAltName`, matching `--host` exactly (iOS
  ignores a bare CN, so an IP host needs the IP in the SAN). It must be a CA
  (`basicConstraints=critical,CA:TRUE`), or iOS never lists it under Certificate Trust Settings.
  The Mac must trust it too, or `security find-identity -p ssl-server -v` counts it invalid and
  the identity chooser skips it. macOS `openssl` is LibreSSL: `-addext` works, and
  `x509 -noout -text` shows the result.
- Device Hub's profile panel does not install a `.cer` and rejects a `.mobileconfig` as a
  provisioning profile. Wrap the DER certificate in an unsigned `.mobileconfig` with a
  `com.apple.security.root` payload, serve it over plain HTTP with the content type
  `application/x-apple-aspen-config`, and open it in the device's Safari
  (`devicectl device process launch --payload-url`); the owner allows the download and installs
  the profile. Before trusting it, compare its SHA-256 fingerprint with the certificate the live
  server presents.
- The first TLS handshake with a key imported from a `.p12` posts a keychain authorization
  dialog on the Mac that only the owner can answer, so a backgrounded server waiting on it looks
  hung. `curl -sk https://127.0.0.1:PORT/` succeeding while the real interface times out
  separates a route or dialog problem from a broken key or trust.

```sh
openssl req -x509 -newkey rsa:2048 -sha256 -days 800 -nodes -keyout dev.key -out dev.crt \
  -subj "/CN=HOST" -addext "subjectAltName=DNS:HOST,IP:LAN_IP" \
  -addext "extendedKeyUsage=serverAuth" -addext "basicConstraints=critical,CA:TRUE"
openssl x509 -in dev.crt -outform DER -out dev.cer
echo | openssl s_client -connect HOST:PORT -servername HOST 2>/dev/null \
  | openssl x509 -noout -subject -issuer -dates
```

Diagnosis:

- `ba-serve` logs nothing even for requests it serves, `lsof` samples one instant, and
  `log stream --device` no longer exists on macOS 27, so none of them shows the absence of
  traffic. The certificate check above is the cheap decisive test. The unified log redacts
  dynamic strings and objects not marked public: log pack identifiers as public and keep paths
  private.
- Addresses rot. Unplugging and replugging the device renegotiates the Mac's link-local address,
  and a Wi-Fi address can vanish, silently invalidating a certificate SAN and the device
  override that named it. A Safari check on the device proves route and trust only for the exact
  URL it opened. Prefer a stable wired address or the Mac's local host name, and read the
  override field back: it can name another Mac.
- When route, trust, override and server all verify and the daemon still opens no connection,
  restart the device before rebuilding certificates; the daemon's override state was observed to
  wedge across setting changes.
- Keep one trusted development profile on the device and delete superseded identities on the Mac
  once nothing serves them.

Xcode and packaging:

- Xcode 27's Run-scheme Background Asset Packs folder is a `LaunchAction`-only scheme element.
  XcodeGen 2.46.0 cannot express it, regenerating the project drops a hand patch, and an
  `xcodebuild build` plus `devicectl` flow never consumes a launch action.
- `ba-package` can fail with a false path-extension error on its own JSON template inside a
  restricted agent workspace while the same invocation works outside it. Stable `ba-package` 2.0
  on macOS 27.0 (26A428) with Xcode 27.0 (27A266a) accepted the template. Diagnose the tool by
  its exact invocation.

## Delivery is qualified only through Apple's distribution

Localized packs were testable through Xcode and TestFlight on iOS 27 in 2026, and App Store
Connect's documentation then said App Store distribution of localized packs would arrive later
in 2026. A deterministic pack-provider fake tests transactions and presentation only: it makes
no request to Background Assets and establishes no delivery behavior, and a Simulator is not a
clean-device distribution artifact. Test uploaded packs through TestFlight before relying on
them.
