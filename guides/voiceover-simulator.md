# Simulator VoiceOver

These mechanisms and lessons apply when the stated capability is present. Original
measurements establish their recorded platform and workload; they do not establish
universal behavior on later operating systems or in a different application.

A simulator's VoiceOver reads the app under test with no device, no Simulator window and no
sound. Its transcripts are acceptance evidence for what VoiceOver reads on iPhone and iPad
under the [acceptance rule](voiceover.md#acceptance-rule); stock simulator VoiceOver activates
nothing. The shared mechanisms are `vocaro_engineering.simulators.speech` (bounded commands,
`devicectl` state reads, the mute watch, process-group stops, staged-output recovery, the
transcript and its outcome) and `vocaro_engineering.voiceover.activation` with
`src/objc/VoiceOver/probe-simulator-voiceover-activation.m` (guarded cursor activation). A
project keeps its probe, fixture, build and device defaults in its own runner.

## Runner contract

- Create one simulator per device type on an explicit runtime, as the
  [simulator-disposable](../agents/capabilities/simulator-disposable.md) capability requires.
  Pass its canonical uppercase UDID to every command; never select by name or `booted`.
- Boot with `simctl` alone and wait for `xcrun simctl bootstatus UDID -b`. Never open a live
  simulator view (Device Hub) or a tool that controls a simulator's screen unless the owner
  asked to watch: such a tool asks the owner to approve each device, and a disposable device is
  new on every run.
- Mute each simulator before anything runs ([below](#muted-speech-capture)).
- Build the probe once for the simulator; a simulator build needs no signing team. Then run one
  `xcodebuild test-without-building` per simulator at the same time, each with its own result
  bundle and derived-data folder, `-collect-test-diagnostics never` and an `-only-testing:`
  filter naming the one probe test. On the shared host the build and the runs go through
  heavy-work admission: define them as a lane and run `python3 scripts/eng run LANE`.
- Pass settings to the probe as `TEST_RUNNER_`-prefixed variables. xcodebuild strips the prefix
  and gives the variable to every test runner process (`man xcodebuild`); an unprefixed shell
  variable does not reach the test.
- Put the run under a deadline and stop only the process groups it started.
- Delete the simulators however the run ends, also when it is terminated: turn SIGTERM and
  SIGHUP into an ordinary exit so cleanup runs. Never boot, change or delete a simulator the run
  did not create. A failed deletion fails the run.
- Write one transcript per simulator, merged by time: the device, build revision and steps, the
  probe's phrases (`VOICEOVER_EVENT` lines), every mute event, and the result with VoiceOver's
  state and the volume as `devicectl` reads them after the run. `speech.report` writes it.
- Exit 0 only when every probe ran all its steps (its last phrase line says it finished) and
  passed, the filtered run executed exactly one test, VoiceOver is off again and no simulator
  lost its mute. `speech.report` returns 125 for a probe that never started and 124 for one
  stopped at the deadline before its test ended. Its test-end pattern defaults to a probe
  method named `testCaptureNavigation`; pass `test_ended` for another name.
- After the run `report` switches off a VoiceOver left on and records it. A simulator that
  was heard, or could have been, is not a clean run.

Record the probe's build revision when it is built: `git describe --always --dirty` before
the build, saved in the derived-data folder only after the build succeeds. A run that skips
the build reads that record, so later edits do not change it; a build the runner did not
record is `unknown`, and a separate line gives the checkout's current revision. A failed or
interrupted rebuild deletes the old record. `-dirty` says tracked files were edited; it does
not identify the edits. See [evidence](evidence.md).

## Muted speech capture

A simulator's VoiceOver speaks through the Mac's own output device, at volume 60 unless set.
Set each simulator's volume to 0 and run nothing until it reads 0:

```sh
xcrun devicectl device settings audio --device UDID --volume 0
xcrun devicectl device info audio --device UDID --quiet --json-output -
```

- Read every simulator's volume again each second, including one whose probe has ended
  (VoiceOver stays on after a crash), and at the end (`speech.keep_muted`). A simulator whose
  `backboardd` restarts comes back at its default volume within about 6 s with VoiceOver still
  on; on iOS 27.0 this happened once in about thirty rotations, an abort in Metal. The watch
  mutes it again and records an `UNMUTED` line, and the run is not clean.
- Bound each read to 5 s so that one slow answer does not hold up the watch on the others. A
  read with no answer is a `VOLUME gave no reading` line. A few appear in most runs, while
  xcodebuild starts its test, and two thirds of those seen came on a saturated Mac.
- This reads a setting. Nothing listens to the Mac.
- The probe polls `XCUIVoiceOverService.currentSpeech()` and prints each new phrase with its
  time as a `VOICEOVER_EVENT` line. The transcript sorts by time alone, so phrases of one
  instant keep the order they were spoken in.

## Readiness and silent start

- On a newly booted simulator VoiceOver's first start took 40 to 60 s, by its own log waiting
  for its voice database, while XCTest's `enable()` returned in a few seconds. On a Mac that
  other sessions had saturated it took 170 s, and on another day 75 to 292 s (iOS 27.0,
  October 2026).
- Until VoiceOver speaks, touches reach the app as plain touches and every move fails with
  "Failed to send moveForward command". Wait for VoiceOver's first phrase under a start limit
  (3 min by default) and record how long it was silent. Under saturation a 600 s start limit
  inside a 1,200 s deadline carried five sessions in a row through.
- Switching VoiceOver off and on again did not help: one session stayed silent through three
  starts. VoiceOver's log stops for minutes after its assets are fetched while it is silent.
- A session stopped silent at its start limit is unmeasured, caused by host pressure. It says
  nothing about the app.

## The xcodebuild diagnostics hang

- xcodebuild's diagnostics collection after any recorded issue holds a run for up to ten
  minutes; pass `-collect-test-diagnostics never`
  ([simulator testing](simulator-testing.md#diagnostics-collection)). A rotated iPad logs an
  orientation-support warning in a probe that passes, which is enough to start the collector:
  xcodebuild then ran on for anywhere from 22 s to the full ten minutes.
- If xcodebuild still has not ended a grace period after the probe's test ended, stop it, after
  reading the speech from the unfinished result bundle. Take whichever of the console and the
  staged output holds more phrases (`speech.staged`) and record a `STOPPED` line naming the
  source.
- Stop xcodebuild by its process group, INT, then TERM, then KILL, with bounded waits
  (`speech.stop`), and stop the diagnostics collector by its exact UDID argument.
- XCTest fails a UI test when a process it calls critical crashes during the test. "Critical
  process xctest crashed" failed a probe while other sessions' unit tests ran on the Mac; the
  probe's own transcript was complete. Report XCTest's reasons as `FAILURE` lines.

## What stock simulator VoiceOver cannot do

Observed on stock iOS 27.0 simulators (Xcode 27.0, iPhone 17 Pro and iPad Air 13-inch (M4)),
October 2026, and compared with physical devices on 27.2, which performed every one of these:

- A double tap under VoiceOver does not perform the cursor item's action. The app receives one
  plain touch where the double tap landed, about 0.25 s later. With the cursor on one control
  and the double tap on another item, the touch arrives on that item.
- An `activate=` step on a control therefore works upright only because the touch lands on the
  control it names. What follows is real, and so is VoiceOver's reading of it; that VoiceOver
  activated the control is not shown.
- In landscape the touch arrives a quarter turn away, at (height − y, x) for a double tap at
  (x, y), and lands on nothing or on another control.
- The rotor offers an item's actions and speaks them, and a double tap performs none: neither
  the action nor `accessibilityActivate` is called. Turning the rotor and moving by its setting
  need no activation and work, for example moving from heading to heading.
- XCTest's Control-Option-Space reaches VoiceOver, whose log names it Activate, and nothing
  reaches the app. Control-Option with an arrow moves the cursor, in about 0.4 s.
- VoiceOver does not know that anything was activated, so it does nothing it does after its own
  double tap. It does not ask again for the items round its cursor, and it stays on a link whose
  target the app showed. An item read after `activate=` that dates from before the step is not
  evidence of one on a device.
- With VoiceOver off the same touches work in both orientations, so the difference is the
  simulator's, not the probe's or the app's.
- A simulator keeps the orientation a session left it in. End a session that rotates upright,
  or the next one starts on its side and its double taps land elsewhere. To read a later
  landscape spread, turn pages upright and then rotate.

The tap gate described under [guarded cursor activation](#guarded-cursor-activation) was traced
in the iOS 27.2 runtime (build 24B5110a); stock 27.2 is that hook's negative control. The iOS
27.1 runtime of Xcode 27.1 offered only the iPhone Duo simulator and was not compared.

A simulator's VoiceOver takes XCTest's Read All key, Control-Option-A (`Read All From Current
Item` in its log), where XCTest has no two-finger swipe; on a physical iPad XCTest's VoiceOver
keys did not reach VoiceOver, so a device Read All step is not known to do anything.

## Reading the rotor without activation

Whether the rotor kept its place across a change can be read with no activation. Choose an
action with one flick down, make the change by a plain touch (a double tap that lands on the
control) or by an app timer, `listen` for what VoiceOver says by itself, and flick down again.
The action after the chosen one says the rotor kept its place; the chosen one again says it
started anew. That a double tap then performs the action is still a device's to show.

## Timings and simulator geometry

- A move cost about 0.5 s and a touch about 5.5 s, most of it XCTest waiting for an event
  VoiceOver keeps from the app. Confirming the end of a read cost 3.3 s, and an activate or a
  rotation a little over 1 s after the gesture. Count earlier steps into the delay of any app
  timer used for a change VoiceOver did not make.
- Simulator geometry is not the device's. An iPhone 17 Pro simulator shows 402 × 874 points and
  holds fewer lines than an iPhone 17 Pro Max, so page boundaries differ. A constrained iPad is
  still an iPad and does not establish iPhone behavior.
- In an iPad simulator a session that starts from the first item put VoiceOver on the window's
  resize control. Touch an item of the app first.
- XCTest's two-finger rotor turn moved a simulator's rotor one setting in some sessions and
  three in others. Turn in several sizes and stop at the wanted label, or use VoiceOver's
  keyboard rotor command (Control-Option-Command-Right Arrow) where turns do not register.
  Repeated synthetic rotor keys on an iPad can be interrupted by UIKit's "Keyboard visible"
  announcement.

## VoiceOver's vot log

VoiceOver keeps a log of its own in a simulator. It says what VoiceOver did where a transcript
says only what it read. Stream it for the length of a session, from the mute until the probe
ends:

```sh
xcrun simctl spawn UDID log stream --level debug --style compact --predicate 'process == "vot"'
```

On the iOS 27.0 simulator runtime, October 2026:

- `VOTElement` has each move: the command and the item it started from (`ElementMovement
  decision`), the items held each side of the cursor (`Cache:`), which it tried
  (`Checking element`, `Found element`), what it asked the app for and was given
  (`fetch count: N -- startFromBehind:` and `retrieved:` with `AHEAD` and `BEHIND`), and when it
  discarded what it held (`Forced update, so removing all from cache`).
- `VOTNotifications` has each notification as it arrived (`VoiceOver Received note: Layout
  Changed`), and `VOTCommon` VoiceOver's answer to a move: `DidFocusOnElement`,
  `DidWrapBackwards`, `BoundaryEncountered`.
- A `<null>` in the cache is an end of the list as VoiceOver has it: it asked for one more item
  there and got none. A move to that side ends in `Found element: (null)` and
  `BoundaryEncountered`, and the transcript repeats the phrase.
- VoiceOver asked for 50 items each way at a move made while it held nothing, which is how a
  screen change leaves it, a menu's closing among them; for 2 each side of a touched item; and
  for 1 at each move after that. A touch straight after a menu left it holding 4 items, a move
  straight after it 61. A logging build on a physical iPad Air 13-inch (M3), iPadOS 27.2, saw
  50 after a menu in one session and two requests for 10 in another, so do not treat the count
  as fixed.
- A layout change was acted on about 0.8 s after it arrived, and only if VoiceOver had stayed
  where it was: `Forced update`, then `fetch count: 2` each way from its cursor. Five layout
  changes that arrived while it moved every half second were followed by no forced update.
- At a forced update VoiceOver looks again at the item under its cursor (`Proposing current
  element`). `Will set element` straight after says the item listed there is another object
  than the one it held: it set its cursor on it without speaking, and its rotor is back at its
  default. With no `Will set element` the rotor choice stands.
- An item VoiceOver holds is asked about again at a move only if its cursor has not been on it.
  An item its cursor has visited is taken as it was, `Checking element` and `Found element` in
  the same millisecond, and read from what VoiceOver kept. It is found stale only at the next
  move (`currentValid=0`, `found sonar element`).

What these mean for an app's elements and notifications is in
[iOS VoiceOver](../knowledge/apple/voiceover-ios.md).

Neither the transcript nor the `vot` log names the voice: XCTest gives a phrase's words alone,
and `vot` enqueues each phrase with `voice: <nil>` and its words redacted. Add the speech
extension to the predicate, `process == "vot" OR process == "MauiAUSP"`: each phrase then has
`Processing markup for voice locale: LOCALE` and the first phrase in a voice `Setting voice:
VOICE`. A move cuts off what is left of the phrase before it, so where the voice of each part
matters let VoiceOver finish (`listen=`) before the next move: a line of English with French in
it was three syntheses, and a move half a second in left only the first. See
[text layout and Unicode](../knowledge/apple/text-layout-and-unicode.md) for spoken
localization.

To see what VoiceOver asks of UIKit directly, use a throwaway build that replaces UIKit's
private `_accessibilityElementsInDirectionWithCount:options:` to log the count asked and what
came back. It works in the simulator and on a device; keep it out of the change and keep its
patch with the issue. UIKit's hit test of a text view and XCTest's snapshot read every listed
element, twice at each move, so count those reads when measuring an element list's cost. To
find which element supplies an action VoiceOver offers (UIKit offers the actions of every
containing element), prefix each action's name with its supplier in such a build and step
through the rotor.

## Guarded cursor activation

VoiceOver's simulator code, read statically in iOS 27.2 build 24B5110a, shows why a double
tap is a plain touch. Its `_handleSimpleTap:` asks `VOTElementManager`'s
`_shouldSendTapStraightToSystem` before it looks at the cursor or the chosen rotor action; when
that returns true it sends a plain touch at the gesture's point and returns. A keyboard
activation has no touch point. The gate reads an internal testing flag. The hook makes that one
method return false, so VoiceOver itself dispatches the cursor item's default action or the
rotor action. It changes no installed runtime file and no app code. It is a diagnostic: device
acceptance for activation is unchanged.

The hook also repairs one ordering fault. With the gate alone, a link reached its target and
VoiceOver could keep the source link as its latest speech, where a physical iPhone announced
the target at once. The cause was a pending targeted Layout Changed notification whose item has
the cursor item's accessibility identity but a new label: a generic screen-change update
consumed that target (`nextElementToFocus`) before the layout handler built its announcement.
The hook wraps `_handleScreenChangeImpl:`. Only when the pending target equals the current item
and both non-nil labels differ does it first call VoiceOver's own `_handleLayoutChange:` with
speech requested, then the original screen handler. Requesting speech avoids the timer's speech
flag, which notification handling can clear for a reused identity. VoiceOver still chooses the
target, cursor, rotor behavior and announcement text. A repair logs
`EPUB495: processed renamed target before screen update v3`. An earlier repair that ran the
layout timer first passed an iPhone 17 Pro and iPad matrix and left a silent case on an
iPhone 17 Pro Max, so qualify on all three.

The guards:

- `activation.default_mode(runtime)` gives `cursor` only for
  `com.apple.CoreSimulator.SimRuntime.iOS-27-2` and `stock` for any other runtime. An explicit
  stock mode always records an unmodified control.
- `activation.prepare()` runs before any simulator is created. It requires that runtime
  identifier with build `24B5110a` from `xcrun simctl list runtimes --json`, and the pinned
  SHA-256 of the runtime's entire `VoiceOverTouch.app/vot` executable, and refuses otherwise.
  There is no silent fallback: cursor mode on another runtime, or a changed build or binary
  under the pinned name, fails.
- It builds a library with a unique name for each run, so it never replaces one mapped by a
  concurrent run, with `xcrun --sdk iphonesimulator clang -dynamiclib -target
  arm64-apple-ios27.0-simulator`, and signs it ad hoc. Select the Xcode with `DEVELOPER_DIR`
  for both the build and the run.
- The library compiles only for an arm64 simulator, acts only in a process named `vot`, and
  checks the Objective-C type encodings and the leading instruction bytes of the gate, the
  screen handler and the called layout entry before installing either override. On a mismatch
  it logs `EPUB495: refused unknown activation/layout handler v3` and installs nothing.
- The runner injects it only inside its own disposable simulators, after boot, with
  `xcrun simctl spawn UDID launchctl setenv DYLD_INSERT_LIBRARIES LIBRARY`. Nothing sets the
  Mac's injection environment or modifies an installed runtime.
- `activation.evidence_failures(log, vot)` fails a run unless the `vot` log has
  `EPUB495: cursor activation v3 enabled build 24B5110a` from every `vot` process it shows (a
  VoiceOver restart is a new process that must confirm again), has no refusal line, and the
  probe log has `VOICEOVER_ACTIVATION_CHECK passed:`. Run the `vot` log stream for every cursor
  run.
- A startup canary runs in a separate verification view before the app's steps. It focuses a
  counter button, activates it with Control-Option-Space, then double-taps away from it; each
  must add exactly one. It then chooses a named custom action from the Actions rotor and
  activates it with an off-target double tap; that action adds ten, so a missing or duplicate
  custom activation fails on its own. A failure ends the test before the app's steps. The app
  then launches in a new VoiceOver session without the canary.
- The transcript names the mode, the runtime build and the binary fingerprint.
- Stock mode with the activation check runs the canary as a negative control. A pass there
  needs investigation.

Another runtime needs its own guards and qualification before adoption: fingerprints,
instruction checks, the canary and stock negative controls. Keep regression tests showing that
unknown builds, altered binaries, missing markers and missing canary results cannot pass.

## Investigating cursor activation

- Compare stock recordings of an off-target double tap and of the keyboard command, with the
  `vot` log, and read the app's own state afterwards. An offered action is not a performed one,
  and a passing recording test is not evidence of activation.
- Use strict assertions: a missing target, rotor setting or action fails at once; speech is
  awaited for a prefix or contained text within a bounded wait; the app's state is compared as
  a whole line. A check that speech names a visible snapshot item allows about 3 s for snapshot
  delivery and suits the app's own text only. Native controls' XCTest labels can differ from
  their VoiceOver names (an inspector's `+` is "Zoom In"), so assert their known speech
  explicitly. Never skip a stale line to find a passing one.
- Use a fresh VoiceOver session between independent workflows: disable VoiceOver, launch the
  next workflow, enable VoiceOver and wait until its move service answers. Keep an action and
  every focus, speech and rotor assertion that follows it in one uninterrupted session.
- Separate a navigation announcement from activation with an app timer that navigates by
  itself; that activates no accessibility item.
- Activate through off-target double taps, which match the device reference; the canary checks
  keyboard activation separately. Where gesture turns fail on an iPhone, use the keyboard rotor.
- Qualify on an iPhone Pro, a Pro Max and an iPad, in both orientations and every reading flow
  the app has, at most two simulators at once, stopping at the first failed session. Relax no
  assertion or timeout and convert nothing to a skip or an expected failure.
- Keep the patch, its base revision, the step lists, results and remaining gaps with the issue,
  so the experiment can be repeated without keeping an investigation branch.
- Read VoiceOver's simulator code statically, as
  [shared host](shared-host.md) describes; never attach a debugger.
