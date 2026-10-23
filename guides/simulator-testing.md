# Simulator testing

These mechanisms and lessons apply when the stated capability is present. Original
measurements establish their recorded platform and workload; they do not establish
universal behavior on later operating systems or in a different application.

Physical iPhone and iPad work is in [device testing](device-testing.md), simulator and device
VoiceOver in [VoiceOver](voiceover.md), and reservations, handoff and process supervision in
[shared host](shared-host.md).

## Simulator lifecycle

- Address every simulator by the canonical uppercase UDID of a device this session owns
  (simulator-disposable) or has reserved (simulator-pool). Never select a device by name or
  `booted`: `booted` is whichever simulator booted first, which may be another session's. The
  project's configured capability decides which model applies; the two are exclusive.
- Never boot, shut down, erase, delete or reconfigure a simulator another session owns, or one
  whose owner is unclear.
- Drive simulators headlessly. Use `simctl` to create, boot, install, launch and capture,
  `xcodebuild -destination "platform=iOS Simulator,id=UDID"` to test, and `devicectl`, which
  also addresses simulators, to read audio, VoiceOver and display state. A device is usable only
  once `simctl bootstatus UDID -b` has returned.
- Do not open a live view of a simulator, or any tool that takes control of a simulator's screen
  (such as a desktop app's simulator panel), unless the owner has asked to watch. Such a tool
  asks the owner to approve each simulator and remembers the approval by UDID.
- On the shared host, run the lifecycle, build and tests as one admitted lane
  (`python3 scripts/eng run LANE`). Booting a fresh simulator is heavy work in its own right.
- Bound every command and follow the owned process to a terminal result. An expired output wait
  does not end the command.

`vocaro_engineering.simulators.lifecycle` provides both adapters. `disposable()` creates a
uniquely named device, recovers an interrupted creation and deletes the device by exact UDID.
`reserved()` wraps a device that project policy has already reserved and never changes its
lifecycle. Both canonicalize the UDID and refuse `booted`.

## Disposable simulators

1. Create the device with a unique name and record the UDID that `simctl create` prints before
   doing anything else with it.
2. Truncate that device's boot and test logs, so a failed boot cannot show an earlier run's
   output.
3. Boot it and wait in `bootstatus -b` under a time limit kept on the process itself.
4. Run the tests with `id=UDID`.
5. Shut it down and delete it by that UDID in an exit trap, however the run ends.

```sh
name="PROJECT-iPhone-$(uuidgen)"
udid=$(xcrun simctl create "$name" com.apple.CoreSimulator.SimDeviceType.iPhone-17-Pro \
  com.apple.CoreSimulator.SimRuntime.iOS-27-0)
trap 'xcrun simctl shutdown "$udid" 2>/dev/null; xcrun simctl delete "$udid"' EXIT
xcrun simctl boot "$udid"
perl -e 'alarm shift; exec @ARGV' 600 xcrun simctl bootstatus "$udid" -b
xcodebuild test -scheme SCHEME -destination "platform=iOS Simulator,id=$udid" \
  -destination-timeout 600 -parallel-testing-enabled NO -collect-test-diagnostics never
```

Run such a script as one admitted lane. In a shell lane:

- Start each child in the background and `wait` for it, so a TERM or INT trap runs while
  `bootstatus` or `xcodebuild` is still waiting.
- Stop only the descendants of the command you started: TERM first, then KILL after a short
  grace period, so a tool that ignores TERM cannot hold the exit trap.
- Bound `bootstatus` with `perl -e 'alarm SECONDS; exec @ARGV'`. `exec` keeps the alarm on
  `bootstatus` itself, so no watchdog child survives a stalled boot.
- CoreSimulator can store a device after `simctl create` is interrupted and before it prints the
  UDID. Recover only by the run's exact unique name; if more than one device has that name, stop
  and inspect instead of deleting.

A first boot can stall in data migration even at low CPU load, while other simulators boot or a
host authorization is pending. Report a boot timeout as unmeasured, with its cause, separately
from test failures, and continue with the next device. Never retry a failed test. Report each
device's outcome and exit nonzero when any device failed.

## Reserved simulator pool

- Use only the project's approved pool; its device names and runtimes stay with the project.
  Reserve a device through the [shared-host](shared-host.md) procedure before using it.
- Take a shut-down device. A booted pool device belongs to another session even when it looks
  idle. If `simctl boot` reports that it is already booted, another session took it first:
  choose another. When every device of the kind you need is booted, coordinate with their
  sessions instead of creating one.
- Erase only the device you claimed, then boot it to completion. Erasing keeps the UDID, and
  with it the simulator tool's approval, so a pool interrupts the owner far less than a new
  device per run. An erased pool device counts as fresh synthetic state for a qualification
  record.
- Pass the UDID to `xcodebuild` as `id=` and to any simulator tool as its device.
- Copy evidence off the device before shutting it down: the next session erases it. Shutting it
  down returns it to the pool; then release the reservation.
- Do not create, rename or delete pool simulators without the owner's authorization. When the
  owner asks for a new one, create it once under the pool's naming scheme and let its first boot
  finish (`bootstatus -b`) before shutting it down or asking the owner to approve it. A shutdown
  right after a first boot kills daemons that are still starting and leaves crash reports.

```sh
xcrun simctl erase UDID
xcrun simctl boot UDID
xcrun simctl bootstatus UDID -b
# Tests use -destination "platform=iOS Simulator,id=UDID"; copy evidence off, then:
xcrun simctl shutdown UDID
```

## CoreSimulator restarts

Installing or first launching another Xcode replaces the shared simulator frameworks in
`/Library/Developer/PrivateFrameworks`. CoreSimulatorService then restarts and shuts down every
simulator on the host. Runs in progress fail with "Loaded CoreSimulatorService is no longer
valid" or cannot boot their device (observed with Xcode 27 installs, October 2026).

Discard those runs: they establish nothing about the code. A pool device now reads Shutdown, so
confirm with its sessions before taking it again, then erase, boot and rerun. A disposable lane
recreates its device. An Xcode install also quits Device Hub, which changes simulator keyboards
([Device Hub](#device-hub)).

Build and run a test product with the same Xcode, named by path in `DEVELOPER_DIR`
([shared host](shared-host.md) covers toolchain selection).

## Device Hub

In Xcode 27, Device Hub replaces Simulator.app. It is at
`/Applications/Xcode.app/Contents/Applications/DeviceHub.app` and in Xcode's Open Developer Tool
menu. SimulatorKit.framework moved from `Contents/Developer/Library/PrivateFrameworks` to
`Contents/SharedFrameworks`. Observed with Xcode 27.1 (27A9269):

- The missing Simulator.app is expected, not a broken Xcode install, and a check for a running
  `Simulator` process finds nothing. `SimulatorTrampoline.xpc` surviving in CoreSimulator does
  not mean Simulator.app should still exist.
- A running Device Hub's process is `DeviceHub` (Xcode 27.1, 27A9275), although its bundle's
  `CFBundleExecutable` is `DevicesTrampoline`. `pgrep -x DeviceHub` finds it without starting
  it; `vocaro_engineering.simulators.speech.simulator_app()` checks for either app.
- Tooling that hardcodes the old SimulatorKit path still attaches, takes screenshots and
  launches, but its taps and swipes silently do nothing and still report success. An editor's
  bundled simulator panel had this defect. `simctl` has no input command. XCUITest does not use
  that path and works, so drive the UI with UI tests.
- Device Hub has no command-line interface or scripting dictionary. Operating it with the
  pointer is foreground input on the owner's Mac, which needs the owner's explicit
  authorization. Set fold poses by automation ([setting a pose](#setting-a-pose)).

Device Hub also changes simulator keyboards (observed on iOS 27.2 simulators, October 2026):

- An iOS 27.2 simulator boots with a hardware keyboard and pointer connected. While Device Hub
  runs, it removes them, once per boot, from every simulator it is not showing. Without Device
  Hub running, as after it quits for an Xcode install, every simulator keeps them.
- With a hardware keyboard, an iPad window has a focus system and draws selection differently: a
  sidebar's selected row drew focused, in the accent color, instead of gray. A test that needs
  the software keyboard fails while a hardware keyboard is connected.
- For the usual keyboardless state, have Device Hub running, not showing the device under test,
  before the run. Open it without bringing it forward, and confirm the removal in its log:

```sh
open -g /Applications/Xcode.app/Contents/Applications/DeviceHub.app
/usr/bin/log show --last 1h \
  --predicate 'process == "DeviceHub" AND eventMessage CONTAINS "removing default services"'
```

- Measure the keyboard and focus-system state in the app process (a two-second wait for
  GameController's keyboard was long enough) and record both in any render profile or receipt. A
  run in the other state is a different device, not a regression.
- A new simulator shows the software keyboard's first-run card once. Dismiss it before typing.

## Rotation

- Rotate an iPhone or iPad simulator from a UI test that launches nothing and only sets
  `XCUIDevice.shared.orientation`. Unit tests cannot rotate the device, and iPadOS refused an
  app's own orientation request in its windowing mode (iOS 27.2 simulators, October 2026).
- Record the scene size the test measured and fail on a mismatch, rather than capturing the
  wrong orientation.
- A simulator keeps its orientation between sessions. Start each scenario upright and leave the
  device upright.
- Neither `XCUIDevice` nor `devicectl device orientation set|rotate` rotates the Duo simulator,
  although `devicectl` prints the new orientation. Use the pose helper
  ([setting a pose](#setting-a-pose)).
- On the Duo, Device Hub's rotation can differ from `XCUIDevice`'s sensor orientation. Record
  each display's actual orientation from `simctl io UDID enumerate` and reject an axis mismatch.
- A rotated iPad logs "Support for all orientations will soon be required". That warning counts
  as a test issue and starts xcodebuild's diagnostics collection
  ([diagnostics collection](#diagnostics-collection)).

## Multiple displays and fold poses

The iPhone Duo simulator has an outer and an inner integrated display and a hinge. These
observations are from the iOS 27.1 runtime (24A94401) with Xcode 27.1 (27A9269), October 2026.
That runtime offered the Duo as its only device type; iPhone and iPad simulators ran iOS 27.0.

### Setting a pose

Set poses by automation and confirm each from the observed display, never by hand in Device Hub.
Never run `xcrun simctl io UDID screenConfig` on the Duo simulator: it crash-loops SpringBoard.

- Device Hub's pose controls post a vendor-defined HID device-state event. The event is private,
  undocumented simulator API. A small helper posts the same event inside the simulator. Build it
  against the iOS Simulator SDK, sign it ad hoc and run it with `simctl spawn` on an owned or
  reserved Duo, by exact UDID. It is development tooling only, never linked into an app, package
  or gate, and any Xcode or runtime can break it. Keep the MIT attribution of an adapted helper.
- No supported command sets a pose. `simctl` has no fold or rotation command,
  `devicectl device motion hinge-angle` only reads the hinge, and `devicectl` orientation
  commands and `XCUIDevice` do not rotate the Duo.
- Dispatching an event does not prove a pose. After each change, confirm the active display and
  the app's geometry. The simulator can drop an event, often the first after boot, so send a
  pose up to three times and fail the step when it is still unconfirmed.

```sh
xcrun --sdk iphonesimulator clang -arch arm64 -mios-simulator-version-min=27.1 -O2 \
  -framework CoreFoundation -framework IOKit pose-helper.c -o "$TMPDIR/pose-helper"
codesign -f -s - "$TMPDIR/pose-helper"
xcrun simctl spawn UDID "$TMPDIR/pose-helper" hinge 120
xcrun simctl spawn UDID "$TMPDIR/pose-helper" orientation portrait
xcrun devicectl device info displays -d UDID --timeout 20
xcrun simctl io UDID enumerate
```

| Pose | Hinge | Orientation | Active display |
| --- | --- | --- | --- |
| Closed | 0 | `portrait` | Outer |
| Book | 120 | `portrait` | Inner |
| Laptop | 120 | `landscape-left` | Inner |
| Open (flat) | 180 | `portrait` | Inner |

- The orientation names the device as held for the outer display. The inner display sits a
  quarter turn from it, so a landscape inner window takes `portrait` and a portrait inner window
  takes `landscape-left`.
- The outer display turns only while an app is in front. On it, the reported device orientation
  read `portrait` in either orientation, so judge orientation from the window size.
- Changing between the outer and inner displays can reset the orientation. Verify the resulting
  scene dimensions instead of assuming the pose change preserved it.
- A harness that classifies hinge angles states its own thresholds (for example 15° or less
  closed, 165° or more flat, partially folded between). They are not Apple's.

### Capturing the active display

- A newly created Duo boots with its outer display active. `simctl io UDID screenshot` without
  `--display` captures its default display, which is black while that display is off.
  `XCUIApplication.screenshot()` captured the black, inactive outer surface while the app
  occupied the inner display. Label default captures unvalidated.
- Take display IDs from `simctl io UDID enumerate` (its Screen ID), never from port order or a
  constant, and capture with `simctl io UDID screenshot --display=ID OUTPUT.png`.
- `vocaro_engineering.simulators.capture` implements a synchronized capture. The UI test freezes
  a named phase and writes its window viewport and requested orientation. The host enumerates
  the displays and selects exactly one integrated display whose oriented pixel size matches the
  viewport times its scale (within 2 pixels). It checks the requested orientation and the
  confirmed pose (open is the largest integrated display, closed the smallest), captures that
  display, and requires the image's size and at least 0.1% non-black pixels. It enumerates again
  to reject a change during capture, and returns a receipt bound to the build receipt's hash.
- Any failure yields `unavailable` with its reason. An opted-in capture that is unavailable
  fails its test; a passing interaction does not override it.
- Nest the time limits: each capture command inside the runner's wait for a capture, inside the
  test's allowance, inside the host's limit for the whole run (60, 180, 420 and 660 seconds in
  one collector). Run the narrowed manifest with parallel testing off and follow it to
  termination.
- In-process window images avoid the inactive surface, but they do not show system toolbars or
  hardware rendering. Pixel checks do not prove visible content: review each image against its
  accessibility tree.

### Driving pose transitions

- The UI test prints a ready marker naming its step and pose, then waits for a signal file. A
  host driver captures the active display, sets the pose, confirms that the expected display
  became active, captures again and writes the signal. An unconfirmed pose leaves the signal
  unwritten, and the test fails at its own deadline.
- Record each step's display, orientation, attempts and image hashes, and review the images
  before retaining any: they show the whole display.
- Compare captures before and after a change by the band that holds the subject, not the whole
  image ([background Mac testing](background-mac-testing.md)).

### Duo simulator observations

- Lay out from size class and the scene's reserved division regions
  (`reservedRegions(kind: .division, …)`), never from device idiom, orientation or screen. A
  test reads UIKit's physical reserved region independently of SwiftUI's. Its expected pose is
  an assertion, never an injected region, and the suite skips visibly unless explicitly enabled.
- `supportsMultipleWindows` stayed true on the outer display; combine it with live hinge state
  ([scenes and recovery](../knowledge/apple/scenes-and-recovery.md)).
- In laptop pose, `XCUIDevice.shared.press(.home)` did not send the app to the background. Its
  scenes stayed in the foreground until it was terminated, which skipped the save a scene makes
  on leaving the foreground. To end an app as the system would, check that it left the
  foreground and otherwise activate another app (Settings, `com.apple.Preferences`).
- On the inner display in landscape, repeated `swipeUp()` calls left a `List` in place, while
  `press(forDuration:thenDragTo:withVelocity:thenHoldForDuration:)` between two window
  coordinates scrolled it.
- A visible Dismiss button reported `isHittable` false.
- After a Device Hub relaunch, `bootstatus -b` can print "Data Migration Failed" while the
  device boots and runs normally.
- `ExternalNonInteractiveAccessory`, documented for displays connected by cable or AirPlay,
  reported unavailable on the fully open Duo. The simulator presented a `CameraCaptureAccessory`
  without a capture session, which Apple documents as presented only during capture; a device's
  behavior is unverified. The `Reserved` and `Highlight` scene accessories are private API.

## Emulating a slow app

- To reproduce an app that handles an event late, stop only that app's own process on the owned
  simulator: send SIGSTOP just before the event (for example the hinge command) and SIGCONT a
  measured interval after it. The pose helper posts its event about 0.1 s before it returns, so
  the app falls that much further behind.
- To emulate a loaded host without loading it, duty-cycle the app's process (for example stopped
  for 120 ms and running for 80 ms) for the length of a test run. Find the process again each
  second, since every test launch starts a new one. Match it by its executable path inside that
  simulator's device directory (`…/CoreSimulator/Devices/UDID/…`), never by name alone. Always
  resume it on exit, including after an interruption.
- Nothing else on the simulator slows down, so the run isolates the app's own timing
  assumptions. Count a `simctl` or `devicectl` call that times out during such a run as a failed
  attempt of that step.

## Package test hosts

- `swift test` runs on the Mac only. An iOS test bundle needs a host app to run on a device, and
  SwiftPM cannot declare one. Run a package's scheme with `xcodebuild` on a simulator for iOS
  coverage, and build a host app for devices
  ([device testing](device-testing.md#device-host-apps-and-signing)).
- With Xcode 27, the iOS package XCTest host did not complete generic UIKit modal presentations,
  even of a plain view controller. A package test can verify routing, content and activation
  order; the presentation, attachment and dismissal need an app-hosted lane. What in-process
  tests cannot see is in [accessibility](../knowledge/apple/accessibility.md).
- Context menus, swipe actions and toolbar menus need a UI-test lane that performs the real
  gesture ([background Mac testing](background-mac-testing.md)).

[EPUBLib #257 reproduction](https://github.com/vocaro/EPUBLib/issues/257#issuecomment-6174234834)

## UI test input and observation

Observed on iOS 27.0 iPhone simulators, October 2026, unless stated otherwise.

- Write exploratory probes as one step per line (tap a named element, type, rotate, dump the
  tree). Log the accessibility tree and a screenshot after each step, and let the probe assert
  nothing: read its result from the logs, trees and images. Host-side actions the test process
  cannot perform, such as changing text size, capturing a display or folding the Duo, run from
  the Mac between steps.
- A tree and a screenshot show where things stand after a touch, not what became of it. To learn
  that, trace touches inside the app: the view a touch went down on, when it had moved 10
  points, when each scroll view began to drag, the state as it lifted and a second later, and
  any foreground departure or main-thread stall, either of which makes a touch go nowhere.
- A drag that requests a 0.1 s rest measured 0.15–0.17 s in the app. That is about the time a
  scroll view delays touches to the control under it, so a drag that starts on a control is
  taken by either from one run to the next. Give the rest, velocity and final hold explicitly.
- A touch that is over in 0.02 s is too short for a scroll view to take: a 30-point drag at
  1,500 points a second moved nothing, and the same drag at 300 scrolled. A touch resting 0.3 s
  or more on a menu opens it, and every later touch of the run goes to the menu, so make that
  the last step.
- A `swipe` starts where XCTest places it, which with the keyboard up was on the keyboard. On a
  landscape iPhone simulator, a quick downward drag starting 18 to 50 points from the top made
  the app inactive in 11 of 11 tries and sent it to the background in 10; none of three starting
  at 54 points did.
- Typing a Return as `\n` can leave the keyboard up under a field that keeps focus; press the
  keyboard's own key instead. Log whether the keyboard is on screen and which element has focus.
- Set the process's text size with a launch argument such as
  `-UIPreferredContentSizeCategoryName UICTContentSizeCategoryAccessibilityXXXL`, without
  changing the simulator's settings. The other names are `UICTContentSizeCategoryXL`, `…XXL`,
  `…XXXL` and `…AccessibilityM` through `…AccessibilityXXL`.
- Xcode's right-to-left pseudolanguage exercises right-to-left layout without a localization.
- XCTest's accessibility audit names only the controls it flags. Log the frames of the controls
  you rely on beside it.
- A stopped run leaves its changes behind: VoiceOver on, or a large text size, persists into the
  next run, and with VoiceOver on a tap only moves its cursor. Restore both before the next run.
- Diagnosing a failing UI test, binding Mac windows and reading hierarchy attachments are in
  [app testing](app-testing.md).
- `xcrun simctl get_app_container UDID BUNDLE_ID data` gives an app's data container on a
  simulator, for copying out what the app recorded.

Observing content that scrolls:

- Off-screen rows may not exist yet, so an element's absence proves nothing until every viewport
  has been looked at. Scroll with a bounded number of short, overlapping drags, and at each
  viewport check both for the required element and for the absence of a forbidden one.
- Accept combined accessibility labels: a navigation link can merge its text into one label.
- Give each observation its own bounded step that ends on the terminal state, instead of one
  long combined deadline. Wait out any earlier simulated work before starting a step that
  depends on its timing.

## XCTest execution discipline

On the shared host, run builds and tests through heavy-work admission: a configured lane
(`python3 scripts/eng run LANE`) or `python3 scripts/eng admit -- COMMAND`, as below. Public
project docs may show plain commands for contributors on their own machines.

Build once, then run the built products against explicit destinations:

```sh
python3 scripts/eng admit -- \
  xcodebuild build-for-testing -scheme SCHEME -destination 'generic/platform=iOS Simulator' \
  -derivedDataPath DERIVED
TEST_RUNNER_EXAMPLE_FLAG=1 python3 scripts/eng admit -- \
  xcodebuild test-without-building -xctestrun DERIVED/Build/Products/MANIFEST.xctestrun \
  -destination "platform=iOS Simulator,id=UDID" -only-testing:TARGET/CLASS/testMethod \
  -parallel-testing-enabled NO -collect-test-diagnostics never -resultBundlePath FRESH.xcresult
```

- Give each concurrent run its own derived-data path, and each attempt a new result-bundle path.
- `-destination-timeout` defaults to 30 seconds. Under load, 120 to 600 seconds has been needed.
- `-parallel-testing-enabled NO` keeps one test process per destination. With several
  destinations that must not overlap, add `-maximum-concurrent-test-simulator-destinations 1`.

### Test environment

Shell variables do not reach the test process. Pass them with xcodebuild's documented
`TEST_RUNNER_<VAR>` prefix: xcodebuild strips the prefix and sets the variable in every test
runner process of the test action (`man xcodebuild`). `TEST_RUNNER_FOO=__CURRENT_VALUE__:BAR`
appends to an existing value. This works for `test` and `test-without-building`.

Edit `EnvironmentVariables` in a copied `.xctestrun` only when a value must differ per test
target or must travel with the copied manifest.

### Copied manifests

Copy a generated `.xctestrun` to narrow, freeze or edit it:

- Product paths are relative to `__TESTROOT__`, the manifest's own directory. Keep an edited
  copy beside the original, or replace `__TESTROOT__` with the original directory before moving
  it.
- Handle both formats: format 1 keeps the test targets at the top level beside
  `__xctestrun_metadata__`; format 2 lists them under `TestConfigurations` → `TestTargets`.
  `capture.py`'s `relocate` and `test_targets` implement both points.
- Change only the target you mean to change, restrict the copy to the intended test IDs, point
  it at the frozen app and refuse to overwrite existing output. Record the hashes of the app,
  test bundle and manifest ([evidence](evidence.md)).

### Selecting tests and counting them

- Select XCTest cases as `-only-testing:TARGET/CLASS/testMethod`. A Swift Testing function needs
  its trailing parentheses (`-only-testing:TARGET/SUITE/function()`); a suite alone needs none.
  A selector that matches nothing still ends in success with 0 tests (observed with Xcode 27.1).
- In zsh, test names held in one scalar variable pass as one argument, which matches nothing.
  Hold them in an array.
- For every filtered run, read the executed count (`Executed N tests` for XCTest,
  `Test run with N tests … passed` for Swift Testing) and check the expected test identities and
  per-case results, not only the summary. `vocaro_engineering.evidence.require_tests` fails a
  log without a positive count. A run that selected no tests is unmeasured, never green.

### Diagnostics collection

- By default, after a test that recorded any issue, a warning included, xcodebuild runs
  `simctl diagnose --timeout=600` and waits for it, for up to ten minutes. Pass
  `-collect-test-diagnostics never`. With it, the same run ended within a second of its test
  (Xcode 27, October 2026).
- Before stopping an xcodebuild that will not end, read its staged output
  (`RESULT.xcresult/Staging/*/Diagnostics/**/StandardOutputAndStandardError.txt`): stopping
  folds it into the bundle. `speech.staged` reads it. Stop the diagnostics collector too: it
  runs in its own process group and outlives xcodebuild. Stop only the one for your own device
  (its `--udid=UDID`).

### Results and restoration

- xcodebuild's console output lost 3 of one run's 160 event lines that the result bundle's
  attachment kept. Check an apparent gap against the attachment before attributing it to the
  code, and export result bundles sequentially ([evidence](evidence.md)).
- XCTest fails a UI test when a process it treats as critical crashes during the test. One test
  failed with "Critical process xctest crashed" while other sessions loaded the host, with its
  own record complete. Keep XCTest's reason in the record and rerun under controlled load before
  reading it as a product failure.
- A probe that changes simulator or device state restores it on failure, as
  [app testing](app-testing.md) describes for XCTest failure handling, and the state is queried
  independently after forced termination or a transport failure.
- Launch Services protects a launched Mac UI-test runner's executable from the incremental
  linker. Rebuild the generated runner before a Mac UI-test run.

## Hung and buffered test runs

- Written to a file or a pipe, `swift test` output arrives in 16 KB blocks. A hung run's log
  stops short of the hang, or is empty (macOS 27.0, October 2026). Set `NSUnbufferedIO=YES`, or
  run under `script -q LOG`. The last `Test Case … started.` line with nothing after it names
  the hung test.
- A stack sample of the test process your run started has every thread's frames, including the
  test's own file and line, and needs no `sudo`. `swift test` runs XCTest tests in `xctest` and
  Swift Testing tests in `swiftpm-testing-helper`, each a child of `swift-test` (Swift 6.4, Xcode
  27.1, macOS 27.0, October 2026). Find it by name among all of the run's descendants: the
  supervisor polls with `ps`, so following the newest child reached a `ps` in 4 of 40 tries.
  Sample only your own processes:

```sh
NSUnbufferedIO=YES python3 scripts/eng admit -- swift test --filter SUITE > run.log 2>&1 &
run=$!
# Once run.log stops growing, sample this run's test process.
descendants() { for child in $(pgrep -P "$1"); do echo "$child"; descendants "$child"; done; }
for pid in $(descendants "$run"); do
  case $(ps -o comm= -p "$pid") in
    */xctest|*/swiftpm-testing-helper) sample "$pid" 2 -file "hang-$pid.txt" ;;
  esac
done
```

- Do not stop a process because it printed `Test Suite 'Selected tests' passed`; wait for its
  exit status. An unbuffered summary shows that the test bodies finished, not that the process
  ended. On macOS, AppKit run-loop blocks can keep native text views and their layouts alive
  after each was made inside an autorelease pool, until the run loop turns
  ([framework lifetimes](../knowledge/apple/framework-lifetimes.md)). One 100-book layout run
  went on for 1.8 to 32 minutes after its last test passed (macOS 27, October 2026). Those
  durations are observations, not time limits.

[EPUBLib #589 investigation](https://github.com/vocaro/EPUBLib/issues/589#issuecomment-6283724393)

## Debug and optimized Swift test runs

- Run the debug and optimized configurations one after another, each in its own scratch
  directory.
- Run the optimized build with testability, `swift test -c release -Xswiftc -enable-testing`. A
  test that passes in a debug build can fail optimized, or end the test process: references are
  released sooner, and the stack is used differently.
- A debug build uses far more stack per recursion level, so a depth limit qualified in one
  configuration does not hold in the other. Worker-stack methods are in
  [stack and work bounds](../knowledge/apple/stack-and-work-bounds.md).

```sh
python3 scripts/eng admit -- \
  swift test --scratch-path .build/debug-tests
python3 scripts/eng admit -- \
  swift test -c release -Xswiftc -enable-testing --scratch-path .build/release-tests
```

## Builds in a sandboxed agent environment

Observed with Swift 6.4, Xcode 27.1 (27A9269) and macOS 27.0 (26A428) inside a restricted agent
sandbox, 2026-10-13:

- Give each build its own scratch directory and a temporary module cache, and pass
  `--disable-sandbox` to SwiftPM.
- `-Xswiftc -debug-info-format none` avoided a `dsymutil` output restriction without disabling
  optimization or test assertions.
- An Xcode cache-permission failure needs the right execution access; a longer timeout does not
  fix it. A `devicectl` timeout can also come from the sandbox
  ([device testing](device-testing.md#diagnosing-a-device)).

## Invalid connectionUUID before tests launch

An iOS simulator test attempt failed before any test launched with
`Invalid connectionUUID specified` (Xcode 27.1 27A9269, iOS 27.0 simulator, macOS 27.0,
2026-10-13). A fresh dedicated simulator, booted to completion with `simctl bootstatus UDID -b`,
then passed the unchanged test build.

Treat the error as a simulator connection failure, not a test result. Record the attempt as
unmeasured, boot a fresh owned device (or erase and boot a reserved one) to completion, and
rerun the same build.

[MathMLLayout 0.3.1 release verification](https://github.com/vocaro/MathMLLayout/blob/542a370edfca7549732ce82b2b93561aedec067d/doc/testing.md#031-release-verification)

## Destination identity spelling

Use the canonical uppercase UUID when passing a simulator identifier to xcodebuild. In the
2026-10-20 StudyWright adapter check, simctl accepted the lowercase UUID while xcodebuild
refused that destination despite listing the same device in uppercase. The shared lifecycle
helper validates and emits the canonical UUID. This is a destination lookup observation, not a
failure of the tests or simulator runtime.

The rule covers simulator identifiers passed to `simctl`, `xcodebuild` and `devicectl`. Run IDs
and other UUIDs that a measuring harness generates for its own records are a different scope and
may be lowercase.

The [private shared-tooling qualification](https://github.com/vocaro/apple-engineering-evidence/issues/1)
retains the original test results and source identities for this lifecycle helper. The public
regressions in tests/test_lifecycle.py reproduce the destination-spelling and ownership checks
with injected simctl calls; they require no private evidence or live simulator.
