# App testing

These mechanisms and lessons apply when the stated capability is present. Original
measurements establish their recorded platform and workload; they do not establish
universal behavior on later operating systems or in a different application.

This guide sets the boundaries between an app's test layers: what belongs in headless tests,
what each layer establishes, how fixtures and parallel tests stay isolated, and how to read a
failing UI test. Mac hosting and snapshots are in
[background Mac testing](background-mac-testing.md), simulators in
[simulator testing](simulator-testing.md) and speech in [VoiceOver](voiceover.md).

## Behavior belongs in headless models

App behavior belongs in models and presentation values that run in an ordinary process. Views
render those values and forward actions.

- Put the app's models, service adapters and presentation values in a headless compilation
  target that both app targets link and that excludes views. `swift test` then exercises
  production state without launching the app or a simulator.
- New screen behavior includes headless tests in the same change. A UI journey is not a
  substitute for extracting a decision out of a view.
- New headless tests use Swift Testing. Existing XCTest model suites remain valid; both run
  under `swift test` without an app host. XCUITest uses XCTest.
- Headless tests model a presentation decision, not the presentation machinery. UIKit drops a
  sheet raised while another presentation is still leaving, and a change that passed every
  headless test dropped one that way. Run a change to when the app raises or takes down a
  sheet, popover or inspector on a simulator at its candidate revision before integrating it.

## What each layer establishes

- **Headless model and presentation tests** establish decisions, state, persistence,
  concurrency, and accessibility labels, values and states as data. They do not establish
  presentation timing, rendering, focus order or speech.
- **App compilation and source contracts** establish that each platform builds and that the
  scanned bindings, names, roles and declarations are present. They establish no runtime
  behavior.
- **App-hosted tests** run real views, frameworks, services, sandbox and entitlements in
  process; on the Mac they act through accessibility in an offscreen window. They do not reach
  the key window, scene activation, other processes' interfaces or system-drawn UI.
- **Static snapshots** establish content layout under pinned settings against reviewed
  baselines. They omit system chrome, materials and presentations, and do not show what is on
  screen.
- **UI tests** establish gestures, system presentations, windows and scene activation, and
  focus. They establish no speech, and on the Mac they take the keyboard and pointer.
- **VoiceOver lanes** establish what VoiceOver reads and where its cursor and rotor move
  ([VoiceOver](voiceover.md)).
- **Physical devices** establish hardware behavior, real services and device-only activation,
  for what the session exercised.

Each lane states the coverage it establishes. A lane that selects zero tests establishes none,
and a passing lane establishes only the platform and inputs it ran.

## Lanes and push hooks

- Push hooks run headless tests, builds and source contracts only. They never run UI
  automation, app-hosted view tests or snapshots, and never boot a simulator.
- Snapshots, galleries, framework integration and hardware measurements, UI journeys, device
  passes and release smoke tests run on demand, or before a release, as their own lanes.
- Heavy lanes run through heavy-work admission on the shared host
  (`python3 scripts/eng run LANE`).
- A Mac UI test takes over the keyboard and pointer for its whole run. It is foreground work:
  the hosted runner is the default, and an attended run on the owner's Mac needs the owner's
  explicit authorization ([background Mac testing](background-mac-testing.md)).

## Fixture launches

A fixture launch reaches a state through an explicit launch argument, so a UI test or a driver
can open the real app on synthetic data.

- Honor fixture arguments only in Debug builds. Ordinary and Release launches use the production
  stores unchanged.
- Route every store a fixture touches to a fixture-owned location: a defaults suite of its own,
  its own journals and folders. A fixture reset clears only fixture-owned state. Explicit
  locations keep their authority.
- Fixture arguments set only transient state, such as a selection or a simulated failure. The
  production layout and actions stay in use.
- Skip or stand in for effects outside the app: purchases (no local StoreKit configuration),
  notifications, history and network. Remove the fixture's data on graceful termination, and
  leave other copies of the app and the owner's data untouched.
- Pass launch arguments through `XCUIApplication.launchArguments`, or after `-XCTest` for a bare
  `xctest` run. Pass environment to test runners with xcodebuild's documented
  `TEST_RUNNER_<VAR>` prefix: the prefix is stripped and the variable reaches every test runner
  process of the test action. Unprefixed shell variables do not reach the test process. Edit a
  copied `.xctestrun`'s environment only when a value must differ per test target or travel with
  the copied manifest ([simulator testing](simulator-testing.md)).

## Tests own their files and defaults

Swift Testing runs a suite's tests concurrently in one process, and `swift test --parallel` runs
XCTest tests in many processes at once.

- A test owns every file it writes. Stage fixtures in a directory of the test's own, named with
  the process identifier and a UUID, and remove it in teardown. When concurrent tests staged
  one fixture at a shared path, each replacing it atomically, an import that refuses a source
  whose identity changes mid-read failed in 10 of 500 runs, and in none with per-test staging.
  A teardown that removes a shared file also ends another test's work.
- A named defaults suite and the test runner's standard domain are each one preferences file per
  host, shared by every process that opens them. A test that persists a preference uses
  `UserDefaults(suiteName:)` with a UUID-suffixed name and removes that domain in teardown. A
  preference read through a static rather than an injected store needs explicit isolation in
  `setUp`.
- Hold every test source to these rules with a source check, allowing only named exceptions.

## Skips and source contracts

- A test that walks the checkout from `#filePath` reads a path on the host Mac. The Mac app host
  and a simulator can read it; a physical device cannot, and the walk would silently count
  nothing. Such a test skips visibly under `os(iOS) && !targetEnvironment(simulator)`.
- An opt-in test reports a visible skip when it is not selected, never a silent pass. Selected
  tests that produce no valid result are unmeasured with their cause
  ([evidence](evidence.md)).

## Waits bound stalls

- A test wait bounds a stall, not a duration. It fails once the observed progress (traces,
  owner records, lock markers) stays unchanged for a bound, stretched by the host's one-minute
  load per core, and cancels the stalled caller. 15 s has served. A loaded host slows such tests
  without failing them, and a hung lane still fails within the bound.
- A process-timeout fixture waits until its real descendant has installed its signal handler and
  published its identity and heartbeat before starting the timeout under test.
- A fixture that simulates phases holds each phase until its cue is observed, so that scheduler
  delay cannot skip the behavior being checked. Setup waits stay bounded and clean up their
  owned processes on failure.

## XCTest failure handling

- An async journey keeps `continueAfterFailure` on. With it off, XCTest runs teardown blocks
  inside the failing assertion on the main thread, where a main-actor teardown never runs and
  the test hangs.
- XCTest's stop-on-failure exception can bypass Swift `defer`. A test that changes system state,
  such as VoiceOver, restores it from code that runs on Swift errors with
  `continueAfterFailure = true`. Transport failures and forced termination still need an
  independent check that the state was restored.

## Accessibility semantics as data

- Labels, values, headings and selected or available states that VoiceOver reads are
  presentation data. Test them headlessly, and bind the views' accessibility modifiers to those
  same values.
- A source scanner can pin required accessibility bindings and names, adaptive colors,
  reduced-motion handling and keyboard-command declarations, each sheet's Escape (cancel) and
  Return (confirm) placements, and exactly one cancel role in an alert that offers more than one
  action.
- Assert a keyboard-command table against the system's reserved Command shortcut families (Q,
  H, M, Tab and Space). Shift-Command-Q is Log Out.
- Test an app-owned color's contrast headlessly against the platforms' resolved system colors.
- These tests cannot prove the system's focus order, rotor membership, announcements, a
  framework's accessibility exposure or Voice Control addressability. Never claim full VoiceOver
  coverage or accessibility support from unit tests or snapshots. See [VoiceOver](voiceover.md)
  and [accessibility](../knowledge/apple/accessibility.md).

## Diagnosing a failing UI test

- Check the oracle before blaming the app. Sample the result bundle's screen recording near the
  failing assertion and read its UI hierarchy attachment from the moment of failure. Measure the
  app's latency, with signposts for example, before raising a timeout.
- On macOS 27.0 (26A428) with Xcode 27.0, September 2026, a SwiftUI `.accessibilityIdentifier`
  on a pane's scroll-view container reached no element of the Mac accessibility tree, while its
  children's identifiers did and the same identifier worked on iOS. Adding
  `.accessibilityElement(children: .contain)` did not change it. Wait on a child's identifier.
- On the Mac, bind identified windows through their system window identifiers before querying
  descendants: windows with matching titles and frames make indexed queries ambiguous. iOS
  windows carry no identifier.
- A hierarchy attachment can truncate values. Print a value the diagnosis needs in full to the
  log.
- Run a window-restoration test alone: a fresh install, or a fixture reset after another test's
  windows, leaves restored windows without their content.
