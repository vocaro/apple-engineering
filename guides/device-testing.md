# Device testing

These mechanisms and lessons apply when the stated capability is present. Original
measurements establish their recorded platform and workload; they do not establish
universal behavior on later operating systems or in a different application.

This guide covers physical iPhones and iPads paired with the shared host. Simulators are in
[simulator testing](simulator-testing.md), VoiceOver on simulators and devices in
[VoiceOver](voiceover.md), and device reservations and handoff in [shared host](shared-host.md).

## When a device is needed

- Before proposing a device, say what it would show that a simulator cannot. A check said to
  need a finger usually needs a timing or an input that a UI test can make, so trace the touch
  in the app first ([simulator testing](simulator-testing.md#ui-test-input-and-observation)).
- A simulator does not establish generative results: its model is the host Mac's, and an iOS 27
  simulator on a macOS 27 host reports the model available and generates.
- Data protection does nothing on a simulator, and a simulator enforced no app-extension memory
  limit (`os_proc_available_memory` returned 0; see
  [app extensions](../knowledge/apple/app-extensions.md)). Thermal behavior, background
  scheduling and hardware rendering also need a device.
- The iOS 27.1 Duo simulator had no Files or Books app, so a test that goes through either
  needed a device.
- What simulator VoiceOver settles, and what needs a device, is in [VoiceOver](voiceover.md).
- Plan the qualification before using scarce device time: what is being qualified, acceptance
  versus diagnostic runs, a timebox and a bounded retry count ([evidence](evidence.md)).

## Owner devices and session windows

- The paired iPhone and iPad belong to the owner, and the iPhone is the owner's personal phone.
  Agree a window with the owner before any session on them. A real reservation and handoff are
  still required inside that window ([shared host](shared-host.md)).
- Approval of a run covers installing and launching there. It is not an offer to operate the
  device: do not tap it, change settings beyond those the run sets and restores, use Copy (the
  clipboard is the owner's) or remove data beyond the agreed cleanup.
- Nobody touches the device during a run. Using it mid-run made iOS refuse UI automation for the
  remaining tests, and switching apps sends a host app to the background, where iOS suspends it
  and it prints nothing until a timeout. Say so when agreeing the window, and rerun only the
  tests that did not get a fair run.
- Ask the owner for a Focus such as Do Not Disturb. Another app's notification banner stole a
  test's tap, and with VoiceOver on a notification replaces the phrase a step should record.
- Keep the owner's content out of every record: notifications, Home Screen, messages, widgets
  and authentication prompts. Crop screenshots to synthetic content and delete the full frames.
  Discard a session that picked up outside content rather than reading it.
- The owner enters passcodes and completes biometric prompts on the device. Never collect a
  passcode in logs or chat.

## Preflight

After the handoff and before installing anything:

- Identify the device by the full hardware UDID that `xcrun devicectl list devices` or
  `xcrun xcdevice list` reports, not a shortened value or CoreDevice's internal UUID.
- Check what is running on it. Another session's app or test runner there means wait: a second
  campaign changes what the first one measures.

```sh
xcrun devicectl device info processes --device DEVICE_UDID --json-output processes.json
xcrun devicectl device info voiceover --device DEVICE_UDID
```

- The device must be in Developer Mode and unlocked recently. Otherwise `devicectl` refuses with
  "The device has not been unlocked recently" (RemotePairingError 1016), and only the owner can
  unlock it.
- `devicectl device info lockState` reports whether a passcode is required, not whether the
  screen is locked: it reported `passcodeRequired: false` while the owner had the phone locked.
  Ask the owner instead of inferring it.
- Record the original state to restore: VoiceOver, installed test apps, and an inventory of the
  owner's data to preserve. Preserve a VoiceOver session that was already on rather than
  assuming it off.
- Books refused imports on a nearly full device. Check free space before a run that imports
  files.
- Freeze and hash the build you will install ([evidence](evidence.md)), and give each run its
  own DerivedData.

## devicectl states and timeouts

Observed with Xcode 27.1 and iOS and iPadOS 27 devices, October 2026:

- A device reached over the local network lists as `available (paired)` until a command connects
  to it, then briefly as `connecting` or `connected`. Commands such as `device info lockState`
  work from `available (paired)`. `unavailable` means it cannot be reached. An iPhone dropped to
  `unavailable` while its screen slept, over Wi-Fi and over USB, until it was unlocked.
- Under load, `devicectl --timeout 60` and `xcodebuild -destination-timeout 120` were useful
  starting points, not guarantees. Reinstalling an app over Wi-Fi can take more than two
  minutes: give an install its own longer limit (600 s was used) without changing any launch or
  measurement deadline.
- Count xcodebuild's start-up into a run's deadline. On a busy host it took nearly five minutes
  to begin a session whose steps then took one.
- Retry only after a confirmed transient transport failure, a bounded number of times, with a
  fresh preflight and fresh log and result paths. Read the failure before choosing a retry, and
  never weaken an assertion because a connection was slow. An Xcode cache-permission failure
  needs execution access, not more time.
- The first launch of a run can fail inside `devicectl` with CoreDeviceError 1010 before the app
  starts. That is a transport outcome, not a result.
- A timed-out install or uninstall has an unknown outcome: query the bundle's presence before
  acting again ([shared host](shared-host.md)).

## UI automation authorization

XCUITest on a device needs Settings ▸ Developer ▸ Enable UI Automation, an unlocked screen, and
the owner's authentication when XCTest enables automation mode.

- The Settings toggle only lets XCTest ask. Enabling automation mode then runs a
  LocalAuthentication device-owner evaluation on the device. An alert, "Enable UI Automation —
  Touch ID to continue with XCTest" (Face ID on a Face ID device), has Cancel as its only
  button. On iPadOS 27.2 beta (24B5099f), XCTest also asked for the device passcode. Only the
  owner can answer either.
- The authorization belongs to the boot it was made in and carries a credential timeout of
  28,800 seconds. The device asks again 8 hours after it was last given, and after a restart
  (iPadOS 27 devices, October 2026). It lapses on its own, so the problem returns periodically.
- When it has lapsed, XCTest waits 60 seconds for the answer and the session ends before its
  first step with "Timed out while enabling automation mode". Nothing read from the Mac shows
  the cause: `devicectl` reported such an iPad connected, booted, in Developer Mode, unlocked
  and needing no passcode. The device's own log, read for the test daemons alone, does:

```sh
idevicesyslog -u DEVICE_UDID -p "testmanagerd|automationmode-writer|AutomationModeUI"
```

- It shows "Writer daemon requires authentication to enable automation mode", the age of the
  last authorization and "Credential timeout: 28800.000000".
- When a session ends that way, stop. A second try raises the prompt again on a device the owner
  may be holding. Release the device, tell the owner that it is asking for authentication, and
  start one session when the owner is at it. A late approval still enables automation mode, so a
  rerun right after it succeeds without a prompt.
- The alert outlives the run that raised it by minutes and then clears, leaving a clean Settings
  pane. Check within a few minutes, without touching the device, with a
  [device screenshot](#device-screenshots).
- The same error has also cleared by itself, a session half an hour later passing with nothing
  changed from the Mac. Read the device log before deciding which case applies.
- A device in use can lose the authorization mid-run: one run lost it 18 seconds in, with
  another app in front.
- `automationmodetool` governs Mac UI tests only and has no part in this path, so do not
  diagnose the Mac for a device's automation timeout. Mac UI tests need the owner's explicit
  authorization. A status read from a restricted workspace was observed to stay stale after
  Terminal.app reported Automation Mode ready.
- Launching with `devicectl` instead of XCUITest needs no UI-automation authorization
  ([launching without XCTest](#launching-without-xctest)).

## Locked devices

- Xcode builds and installs, then stops at "Unlock … to Continue" until the owner unlocks the
  device. With Xcode 27.1 and an iPhone on iOS 27.2 beta (24B5099f), a session waiting there
  kept waiting after `lockState` reported `passcodeRequired: false`. Verify the live state,
  cancel only that owned session, and run `test-without-building` against the already-built
  product while the owner keeps the device awake.
- `xcodebuild` blocks at preflight on a locked device (`com.apple.dt.deviceprep` Code=-3), and
  SpringBoard refuses a `devicectl` launch under lock (FBSOpenApplicationErrorDomain 7).
- Nothing on the Mac locks a device: `devicectl` reads lock state but cannot set it. Methods for
  measuring under lock are in [data protection](../knowledge/apple/data-protection.md).
- Refuse to start or relaunch a measurement on a locked device. A launch refused for a lock
  produced no reading; record it as unmeasured.

## Device host apps and signing

- Package tests cannot run on a device: they have no host app, and SwiftPM cannot declare an iOS
  host app. Build a minimal host app for each device measurement that links the library, stages
  its inputs into its bundle and runs the measurement in its own process.
- The host needs the development team (an Xcode account for it, with `-allowProvisioningUpdates`
  and the team from local configuration, never committed), a device in Developer Mode, and the
  iOS scene lifecycle. A host that omitted the scene lifecycle crashed at launch.
- Give each host its own bundle ID. Installing over another app's bundle ID replaces that app
  and its data. A capability-bearing profile for a production bundle ID cannot authorize a
  separate host, and a development profile for the host must list the device's hardware UDID.
- Give each run its own generated project and DerivedData. Two runs on two devices then share
  nothing and need no lock.
- Run no SwiftPM build or package resolution in the checkout a device run builds from. A
  re-resolution in the middle of a series of runs relinked the app and coincided with a killed
  test.
- `devicectl` cannot delete a file inside an app's container. Have the app remove the files it
  staged.
- Afterwards, uninstall the host app and its test runner, exact bundles only, and query the
  installed apps again to verify that they are gone:

```sh
xcrun devicectl device uninstall app --device DEVICE_UDID BUNDLE_ID
```

## An isolated QA project

When a qualification must not disturb the production app on a device:

- Generate a separate project (for example with XcodeGen) whose app and test runner have unique
  bundle IDs and use the repository's Info.plist and entitlements. Never substitute the
  production project's launch manifest. The production app and its data stay installed.
- Copy the repository's `Package.resolved` into the generated workspace so the dependency pins
  match, and build for `generic/platform=iOS` with the project's own derived-data and package
  directories.
- Freeze the measured products before launching. Copy the app and runner, retain the exact test
  source, dependency pins and any observer patch, hash every frozen file, and restrict each
  manifest to one test with its behavior deadline. Refuse a production bundle in the frozen set.
- Run the smallest test first, under the agreed reservation, through a bounded launcher. Verify
  its terminal outcome and restoration before the larger run. Keep the window's original release
  time when reserving another run within it.
- Afterwards copy back only the QA app's container and validate it offline. Never read the
  production app's container.

```sh
xcrun devicectl device copy from --device DEVICE_UDID --domain-type appDataContainer \
  --domain-identifier BUNDLE_ID --source Documents --destination READBACK_DIR
```

## Launching without XCTest

- `xcrun devicectl device process launch` starts an app with arguments and environment variables
  and needs no UI-automation authorization. Use it for measurements that need no XCUITest input.
  A check that only needs the app sent to the background can launch Settings
  (`com.apple.Preferences`) the same way to bring it forward.

```sh
xcrun devicectl device process launch --device DEVICE_UDID \
  --environment-variables '{"RUN_TOKEN": "TOKEN"}' BUNDLE_ID
```

- The console is not a completion authority. `devicectl device process launch --console`
  reported an app that crashed, or called `exit` with a nonzero status, as exiting with 0. The
  Xcode test transport has also omitted an app's terminal line after the process completed.
- Take results from what the app writes in its container: a start marker, create-only records
  written as they happen and a completion marker written last. Copy them back with
  `devicectl device copy from` and validate them on the Mac. Fail fast when no start marker
  appears within a bound, or when the app disappears without a completion marker.
- iOS can relaunch an idle host app after a run, and that instance blocks the next install or
  launch. iOS can also start a newly installed host between a driver's process check and its
  launch, so the launch attaches to an instance without the run's arguments. Look for the host
  process again immediately before launching, and never launch into one you find. Stopping one
  on the owner's device needs the owner's agreement and an exact check that it is the idle host:
  its PID and executable, and its container unchanged since the last completed run.
- An ordinary app is suspended in the background, and framework calls can fail there for reasons
  unrelated to the measurement. Keep the host in front with the screen awake: the host can
  disable its idle timer, and the owner sets Auto-Lock. Record every move to or from the
  background, and keep a run that went to the background as evidence only, not as a result.
- An idle app's timers ran up to 7% late in the background. Allow for that in any wait timed
  against them.

## RunningBoard thermal termination of XCTest hosts

Observed on an iPad Air (M3), iPadOS 27.0 (24A435), with Xcode 27.1, October 2026:

- XCTest keeps its host app alive with testmanagerd's `Developer testing(BackgroundUI)`
  RunningBoard assertion, which carries a thermal condition. Once sustained work raised the
  device's thermal pressure to Moderate, RunningBoard terminated the host (`0x05CA1DED`) and
  refused XCTest's relaunch for the same reason, so a long XCTest-hosted workload could not
  complete. An ordinary foreground app at that thermal level was throttled, not terminated.
- Run long, hot workloads in an ordinary foreground app: a Debug-only in-app runner, started by
  `devicectl device process launch` with its settings in the environment, that runs the same
  code and writes the same records. The two hosts then differ only in the host process. Record
  thermal state changes beside the results.
- A RunningBoard termination leaves no crash or jetsam report. Take a sysdiagnose
  ([diagnosing a device](#diagnosing-a-device)).
- Compile the runner out of Release
  ([debug dylibs and signing digests](#debug-dylibs-and-signing-digests)).

## Debug dylibs and signing digests

- A Debug product keeps the app's code in `<executable>.debug.dylib` beside a small launcher, so
  the executable's hash identifies only the launcher. Record both hashes and require both to
  match the installed build.
- Every ordinary `xcodebuild` build of an app re-signs it, and can regenerate the project and
  reprocess Info.plist. The re-signed executable has a new digest even when nothing recompiled.
  Build once, then rerun with `xcodebuild test-without-building`, or reinstall the identical
  build, which keeps both the bytes and the app's data.
- Signing embeds the signing time, while two clean compiles of one revision in one checkout were
  byte-identical. Identify an executable by its unsigned compile when signed digests must be
  compared.
- Read provenance from the running process, never from its environment: bundle identifier and
  version, executable digest, platform, `kern.osversion`, hardware model, and the signature. On
  the Mac that is the running process's `SecCode`; on a device, the embedded provisioning
  profile.
- A Debug-only region must be a conjunction with a `DEBUG` term and no `||`:
  `#if DEBUG && os(iOS) || os(macOS)` compiles in a macOS Release build. Scan archived Release
  products for Debug-only symbols before distributing them ([packaging](packaging.md)).
- Freeze and hash the app, debug dylib, test binary, test source and copied launch manifest
  before a run, and verify them again after it ([evidence](evidence.md)).

## Device screenshots

```sh
xcrun devicectl device capture screenshot --device DEVICE_UDID --destination OUTPUT.png
```

- This captures what SpringBoard draws, including the Dynamic Island, Live Activities and the
  Lock Screen, without UI automation and without touching the device. Use it to look for an
  automation prompt after a failed run.
- The frames show the owner's content. Crop them to synthetic content, delete the full frames
  and never publish them.
- The device can drop to `unavailable` while its screen sleeps.

## Diagnosing a device

- After an odd failure, such as a cascade of instant failures, a locked phone or refused
  automation, read the crash logs from that time before blaming a test:

```sh
xcrun devicectl device info files --device DEVICE_UDID --domain-type systemCrashLogs
```

- A RunningBoard termination leaves no crash or jetsam report, and `log collect --device-udid`
  needs root, so take a sysdiagnose while the condition is live: default-level lines last only
  hours. `devicectl device sysdiagnose` failed on one iPhone with `DiagnoseError 0`.
- The button chord is the owner's action: both volume buttons and the top or side button
  together, briefly, then release. Apple documents about 250 ms; 0.25 to 1 second worked on one
  iPad, and a longer hold locks the device instead. Wait until the new
  `IN_PROGRESS_sysdiagnose_*` entry in `systemCrashLogs` has finished, then copy it off:

```sh
xcrun devicectl device copy from --device DEVICE_UDID --domain-type systemCrashLogs \
  --source ENTRY --destination SCRATCH_DIR
/usr/bin/log show --archive SCRATCH_DIR/ARCHIVE/system_logs.logarchive
```

- A sysdiagnose holds personal data. Keep it outside every repository, record only its name and
  SHA-256, and filter reads to your own processes. Call `/usr/bin/log` by absolute path, because
  zsh's builtin `log` shadows it.
- A `devicectl` timeout waiting for CoreDeviceService can come from a restricted workspace
  sandbox rather than the device. If `xcdevice list` reports the device available and
  CoreDeviceService logs that it has initialized, retry the read-only check outside the sandbox,
  with approval. The timeout says nothing about lock, trust, the cable or UI automation, which
  have their own checks: lock and trust appear in the device details, a data cable produces an
  `IOUSBHostDevice`, and UI-automation approval matters only once XCTest enables automation
  mode.

```sh
xcrun devicectl device info details --device DEVICE_UDID --timeout 30
```

- Unplugging and replugging the cable renegotiates the USB link-local addresses on both ends.
  That invalidates any development-server certificate or override that named the old
  `169.254.x.x` address. Verify the served address again, and expect to re-approve automation.

## Device Hub touch on a physical device

Device Hub mirrors a physical device and can deliver touch when XCTest is the wrong tool. That
is foreground control of the owner's Mac: use it only with the owner's explicit authorization,
inside an agreed device window.

- Resolve Device Hub's current PID and window frame every time. Neither survives a restart or a
  change of geometry.
- Prefer the accessibility tree (`AXPress`) to coordinates. Coordinate events are a fallback
  only after the owner explicitly authorizes them. Calibrate them by matching a `devicectl`
  screenshot to a fresh Mac screen capture, expect the first click after activation to be
  consumed, and verify every tap with another device screenshot. Never reuse coordinates.
- Touch cannot satisfy Touch ID, Face ID or a passcode challenge. That approval stays the
  owner's physical action.

## Restoration and release

- After termination, verify independently from the Mac: settings as they were found, no owned
  process still running, the installed identities, and the owner's data inventory unchanged. An
  interrupted test bypasses its own restoration code.
- A probe that failed or was stopped part way can leave VoiceOver on, on a device the owner then
  picks up. Read the state from the Mac, switch it off if it was off before the run, and read it
  back ([VoiceOver](voiceover.md)).
- Remove only the exact owned app and runner bundles, verify their absence, and release the
  device through the reservation procedure in [shared host](shared-host.md), reporting any
  restoration that could not be verified.
