# Background mac testing

These mechanisms and lessons apply when the stated capability is present. Original
measurements establish their recorded platform and workload; they do not establish
universal behavior on later operating systems or in a different application.

This guide covers Mac tests that leave the owner's keyboard, pointer, focus and screen alone:
views hosted off screen, an owned app driven in the background, and snapshot renders with their
baselines and galleries. Unless a line says otherwise, its observations were made on macOS 27.0
(26A428) and 27.0.1 (26A434) with Xcode 27.0 to a 27.2 beta, September and October 2026. Which
test layer establishes what is in [app testing](app-testing.md).

## Test hosts and what they reach

- **A SwiftPM test process** (`swift test`, or `xcrun xctest` on its bundle) runs AppKit views
  with no app. It suits layout, paint and state read directly from the views. There the
  accessibility API asked of its own process returned `kAXErrorNotImplemented`, and SwiftUI
  built no accessibility tree for an in-process query, so SwiftUI controls can be neither found
  nor pressed through accessibility.
- **An app-hosted test bundle** runs inside the real app, under its sandbox and entitlements,
  and can read and act on the app's own accessibility tree without the Accessibility permission.
  The difference between these two hosts was observed, not isolated.
- **A separate driver process** reads another process's tree: an open or save panel, a web
  view's content process, or what an accessibility client is actually given. The driver's host
  needs the Accessibility permission.
- **XCUITest on the Mac, native menus and Mac VoiceOver** take the keyboard, pointer, focus or
  speech: [foreground work](#foreground-work-is-a-separate-lane).

## Offscreen AppKit hosting

`OffscreenWindow`, in the test-only
[EngineeringTestSupport](../src/swift/EngineeringTestSupport) package, places a window at
(-30000, -30000) and refuses AppKit's constraint of its frame back onto a screen. AppKit moves a
sheet onto a visible screen, so its `beginSheet` makes the sheet transparent and click-through.
Link the package only into test and tool targets.

- Never make the window key or activate the app. Find a window by an accessibility identifier of
  its own, never by its title, which the host app's own windows can share.
- A background app's windows draw as inactive ones do: gray window buttons, switches and default
  buttons. For renders that must look active, answer AppKit's key, main and active-appearance
  questions with yes for the test's own windows and their sheets only, keeping each window's
  class, because AppKit observes windows with KVO. Those questions include private selectors:
  this is test-only support that an OS update can break.
- Before constructing a window or starting `NSApplication`, put
  `ApplePersistenceIgnoreState=YES` in the volatile `NSArgumentDomain`, preserving the other
  arguments. Saved-window restoration is then off for `swift test` and bare `xctest` runs, no
  user default is written, and a test process that was killed cannot leave a modal restoration
  alert that blocks the next run. OffscreenWindow does not do this itself.
- AppKit keeps every titled window for the life of the process; a block it registers for each
  title bar holds it. Empty and shrink each window when a test is done with it. A long render
  run's host still grew to about 500 MB.
- Toolbars that share an identifier share their visibility across a process's windows, so give
  each test window's toolbar its own. Nothing lays a view out when a toolbar changes a scroll
  view's insets: wait for the insets, then ask for layout.
- `setFrame(_:display:animate:)` with animation is a real live resize: AppKit tells every view
  that it starts, resizes through the sizes between and tells every view that it has ended,
  before the call returns. `viewWillStartLiveResize()` called on one view does not reach its
  subviews. Setting a window's size through the accessibility API is also a live resize, and
  `NSTextView` scrolls itself in `viewDidEndLiveResize`, which moved text at the top of a
  continuous scroll 48 points down.
- AppKit's text checking redraws a text view about a second after its text is set. Turn it off
  in views whose paint a test reads.

## In-process accessibility actions

In an app-hosted test, `AXUIElementCreateApplication(getpid())` gives the app's own tree.
Nothing is granted, nothing activates the app and the owner's work is undisturbed.

- Press with `kAXPressAction`, fill by setting `kAXValueAttribute`, confirm with `AXConfirm` and
  read values. Match controls by identifier, label, title or value, as XCUITest does.
  EngineeringTestSupport's `AccessibilityRead` reads one attribute.
- Keep the queries on the main thread: AppKit answers its own process's requests on the
  calling thread.
- Build each test's model over storage of its own. The host app's container holds the owner's
  real documents, state and preferences.
- AppKit's informal methods do not show what a client is given. `accessibilityAttributeNames()`
  and `accessibilityAttributeValue(_:)`, called on custom elements in a test, listed five
  attributes and nil for every value, and the process then ended with "freed pointer was not
  the last allocation". To see what a client is given, launch the built app with
  `open -g -n -a APP --args …`, so that it takes no keyboard, and query it from another process
  with `AXUIElementCopyAttributeNames` and the attributes' values.

Out of reach in process:

- the key window: keyboard shortcuts, menu commands whose state follows the focused window or
  scene, and focus traversal;
- scene activation, such as a second window opened through the scene system;
- another process's interface: the open and save panels, whose Powerbox contents in-process
  accessibility does not expose, and a web view's page in WebKit's content process. Use a
  [separate driver](#driving-an-owned-app-in-the-background);
- native menus, which open only in front, and actual assistive behavior. An accessibility
  snapshot is an observation, not VoiceOver speech or keyboard activation; see
  [VoiceOver](voiceover.md) and [accessibility](../knowledge/apple/accessibility.md).

The cross-process client check is recorded in an
[EPUBLib issue comment](https://github.com/vocaro/EPUBLib/issues/485#issuecomment-6270877949).

## In-process key events

A fixture inside the owned app can take commands from a companion process, one JSON object per
line for example, and act on its own windows.

- Create `NSEvent`s and dispatch them inside the validated process. Never post global keys or
  move the pointer. AppKit's backward Tab character is U+0019; normalize Shift+Tab to it.
- With each observation, record the key window, first responder, focused accessibility element,
  Full Keyboard Access state and frontmost app. Native menus finish asynchronously, so a
  response still pending must never be given the previous command's observation.
- Keyboard observations from a background window do not establish that the owner's real
  keyboard could reach every menu or overflow item.
- Prefer process-local arguments, such as `AppleKeyboardUIMode` in the argument domain, to the
  owner's global setting. Making a test window key or changing global Keyboard Navigation takes
  focus or changes the owner's Mac, and needs the owner's explicit approval.
- End the session on a deadline, EOF or a quit command; terminate only the owned app and restore
  every setting the session changed.

## Sandboxed app-hosted tests

- Xcode's test signing of the app host added a read-only exception for `/`. A test can read the
  checkout but not write to it, and the exception authorizes no write elsewhere. A test of a
  user-selected grant first checks that the location is not writable before the selection.
- Other processes cannot read the app's container. Stage references and outputs through a
  location the app is entitled to, such as Downloads, in a hidden folder named with the PID and
  time, as hard links that cost no time or space. Move them back when the tests end; the next
  run removes a stopped run's folder. Inside the sandbox Downloads is a symbolic link: follow it
  before validating the directory. Run a suite that needs this staging only on explicit request.
- The host app starts as usual and opens its own window without taking focus. Quitting it ends
  the run partway.
- A hosted test that uses a local StoreKit configuration switches the StoreKit environment that
  every copy of that bundle ID on the Mac shares. Ordinary hosted tests use a scheme with no
  local StoreKit configuration and stand-ins for the App Store; coordinate purchase suites with
  other sessions. See [StoreKit environments](../knowledge/apple/storekit-environments.md) and
  [StoreKit testing](storekit-testing.md).

The grant and Powerbox observations are recorded in a
[Pagepour measurement record](https://github.com/vocaro/Pagepour/blob/68f508d14c2a2133592027eb89806009bccf0326/measurements/save-destinations/record.md#validation).

## Driving an owned app in the background

Use a driver process when a test crosses a process boundary or exercises a built app, such as
an archive smoke test or a long qualification run.

1. Launch without activating: `NSWorkspace.OpenConfiguration` with `activates = false`,
   `addsToRecentItems = false` and explicit arguments, or `open -g -n -a APP --args …`. Check
   that the launched bundle URL resolves to the exact app you built, since Launch Services can
   open another copy, and record the PID. Refuse to start while another copy that shares the
   app's state is running.
2. Hand it files as Finder's Open With does:
   `NSWorkspace.open(_:withApplicationAt:configuration:)` with `activates = false`. Launch
   Services lends the sandboxed app access to each file. The app's own activation request was
   declined while another app was in front, so it stayed in the background.
3. Drive it through `AXUIElementCreateApplication(PID)` with `AXUIElementSetMessagingTimeout`:
   find windows by identifier, press, set values and read state. The menu bar is readable too;
   a menu item's enabled state can tell the driver when the app is idle. The driver never
   requests or grants a permission.
4. Show that the app stayed in the background: sample the frontmost app every few seconds with
   `lsappinfo front` and record how many samples had the owned PID in front. The accessibility
   API's focused application is not available for every frontmost app, and `NSWorkspace` and
   `NSRunningApplication` update only on a running main run loop, which a blocking driver lacks.
   Poll `kill(PID, 0)` for the app's exit.
5. End on a deadline, EOF or a quit command: terminate the recorded PID only and wait for it to
   exit.

Address the process by PID and verified executable path, never by bundle ID or name: other
sessions may run their own builds of the same app ([shared host](shared-host.md)), and `pkill`
by name can end one of them. A tool that picks an app by bundle ID can also relaunch it without
its fixture arguments after the owned process ends.

Tools that address app bundles cannot target a bare executable. System Events reaches one
through the accessibility API. Element commands such as `click`, setting `value` and
`perform action "AXConfirm"` are accessibility actions on the named process and take no focus,
so they are background driving of an owned process:

```sh
osascript -e 'tell application "System Events"' \
  -e 'tell (first process whose unix id is PID) to click button 2 of window 1' \
  -e 'end tell'
```

`keystroke` and `key code` post keyboard events to whichever app is frontmost, and
`set frontmost` activates the process: those are foreground input. The invoking host needs the
Accessibility permission, and controlling System Events needs Automation permission. A missing
permission raises a consent prompt on the owner's screen, so use this route only where both
are already granted.

## Capturing a background window

In process, draw the owned window or view with `cacheDisplay(in:to:)` into a bitmap from
`bitmapImageRepForCachingDisplay(in:)`. This needs no permission and works off every screen. It
draws afresh, as `CALayer.render(in:)` does: it shows what the views would paint now, never a
surface that nothing invalidated, which is what stays on screen. To test what stays on screen,
such as a cleared highlight still painted, record each `draw(_:)` the system makes of a view
into a bitmap kept for that view, and compose those as the views are arranged.

Out of process, list the windows whose owner is the owned PID and capture one by number
without bringing it forward:

```swift
import CoreGraphics
let owned: pid_t = PID
let windows = CGWindowListCopyWindowInfo([.optionAll], kCGNullWindowID)
    as? [[String: Any]] ?? []
for window in windows where window[kCGWindowOwnerPID as String] as? pid_t == owned {
    print(window[kCGWindowNumber as String] ?? "", window[kCGWindowBounds as String] ?? "")
}
```

```sh
screencapture -x -o -l WINDOW_NUMBER window.png
```

`-x` plays no sound and `-o` leaves out the shadow. Capturing another process's window needs
the Screen Recording permission for the capturing host; without it macOS also withholds window
names from the list, so match on the owner PID. Check with `CGPreflightScreenCaptureAccess()`,
record the capture as unmeasured when it returns false, and never raise the permission prompt on
the owner's Mac. Capture only the owned window: a whole-screen capture records the owner's other
work.

## Lock screen and display sleep

Background Mac tests need the screen unlocked and the display awake.

- While the screen is locked, macOS hides every offscreen accessibility window behind its lock
  shield. In-process accessibility tests time out, and a render that works a control through
  accessibility fails. Keeping the display awake with `caffeinate -d` does not help.
- While the display sleeps, AppKit does not advance a scroll view's animation, which runs from
  the display's refresh, so a test waiting for scrolling to move content times out.
- A screen saver that requires a password locks the session too. Treat it as a locked screen;
  this is inferred, not separately observed.

The display sleeps after the Mac's idle time, which can fall inside a long run. Check before a
run, and before blaming a change for such a failure:

```sh
ioreg -n Root -d1 | grep -o '"CGSSessionScreenIsLocked"=[A-Za-z]*'  # no output: unlocked
swift -e 'import CoreGraphics; print(CGDisplayIsAsleep(CGMainDisplayID()) != 0)'  # false: awake
pmset -g log | grep "Display is turned"
```

Record tests that ran while the screen was locked or the display asleep as unmeasured, with that
cause, and rerun only them after the owner unlocks the Mac. Never keep the owner's display awake
or the screen unlocked, with `caffeinate` or a settings change, unasked: that is the owner's
call. The display-sleep failure is recorded in an
[EPUBLib pull request comment](https://github.com/vocaro/EPUBLib/pull/561#issuecomment-6179173544).

## Foreground work is a separate lane

Native menus, context menus and menu-bar commands, key-window commands and focus traversal,
XCUITest on the Mac, computer use, global keyboard or pointer events, a change to global
Keyboard Navigation and Mac VoiceOver all take the owner's focus, keyboard, pointer or speech.
The hosted runner is the default for them. An attended procedure on the owner's Mac is a method
only for a session the owner has explicitly authorized; an earlier approval of a mechanism does
not establish that the Mac is available now. The
[shared host policy](../policies/shared-host.md) and the attended-session rules in
[shared host](shared-host.md) apply, and [VoiceOver](voiceover.md) covers Mac speech. Such a
session also restores the previous foreground app only if it still owns the foreground when it
ends.

## Building snapshot scenes

- Build each scene's state through the app's own models and stores in a scratch location, with
  stand-ins for system services (memory and storage readings, the App Store, notifications,
  Spotlight), so that a state draws the same way on every run. Use made-up content that looks
  real.
- Show the app's real root view. Open sheets, alerts and selections through initializer
  parameters only tests pass, so that the production presentation path draws them.
- Give each scene a stable, unique identifier, which names its files. Reach a state through the
  app's models rather than copying a view's text into the test.
- Keep one plan per module listing its scenes, how each is sized, the canvases it is drawn on,
  and each scene left out with the reason. Fail when a module exports a scene its plan neither
  draws nor leaves out, and when a baseline that no plan asks for is on disk.
- Mount each scene in a window that is never put on screen or never becomes key, and reach it
  with no navigation, input events or accessibility polling. A scene that must work a control
  does it through accessibility, and fails, saying why, while the screen is locked.
- A dedicated gallery app that detects that it is hosting tests opens no window of its own and
  stays out of the Dock.

## Rendering until stable

- Render until consecutive frames agree: two identical renders in a row, or three frames 150 ms
  apart that match to within a few color levels where a material's blur keeps shifting by one.
- Remove motion: spinners at rest, scroll indicators hidden, animations off. Text fields show no
  focus ring or caret, whose animations can stop partway off screen.
- Add a readiness predicate beyond pixels for content that loads asynchronously (laid out, no
  pending navigation, visible text), so that a settled blank page is never taken.
- Fail a page still changing at a bound (12 s has served), keeping its last two frames to show
  what moved, and log a slow first frame (over 2 s).
- A toolbar can settle into different appearances in different windows of one run. Draw each
  page in two independently created windows and require them to agree. A disagreement fails,
  is marked unconfirmed in the gallery with the first window's image kept, and never becomes a
  reference, including while recording; a later recurrence of an earlier appearance cannot
  rescue it.

## Pinned render settings

Draw every image under explicit settings, whatever display, preferences and pointing device the
host has: two pixels per point, the `en_US` locale, UTC, an explicit appearance per canvas,
overlay scroll bars, and emptied preview preferences before each scene is mounted.

Set them in the test process, never in the owner's global preferences. For `xctest`, pass
arguments after `-XCTest`, where they reach the volatile argument domain. For `xcodebuild`, pass
the suite's environment with the documented `TEST_RUNNER_` prefix (`man xcodebuild`), which is
stripped before the variable reaches every test runner process of the test action; unprefixed
shell variables do not reach the test process. Run the suite through heavy-work admission:

```json
"LANE": {
  "command": ["xcrun", "xctest", "-XCTest", "All", "-AppleShowScrollBars", "WhenScrolling",
              "-NSRequiresAquaSystemAppearance", "YES", ".build/debug/PACKAGETests.xctest"],
  "resource": "heavy",
  "minimumTests": 1
}
```

```sh
python3 scripts/eng run LANE
```

- `-AppleShowScrollBars WhenScrolling` gives overlay scroll bars and `Always` legacy ones. With
  the automatic setting, a Mac shows legacy scroll bars while a mouse is attached, and a legacy
  scroller's width narrows the layout beside what scrolls. AppKit gives every scroll view the
  preferred style again when the preference changes, and a process learns its preference a
  moment after it starts. A test that depends on the style holds its scroll view to it, and a
  renderer refuses to draw in a process that prefers legacy scroll bars.
- `-NSRequiresAquaSystemAppearance YES` runs the process light. A test window can instead keep
  its own appearance light unless the test asks for dark, so that results do not differ between
  day and evening.

Record a render identity with every baseline: the Mac model, the macOS build, the SDK the app
was built with, and the settings that change how windows draw (accent and selection colors,
Increase Contrast, Reduce Transparency, Differentiate Without Color). A simulator baseline adds
the device, runtime, display, scale, safe area, orientation, fold and hardware keyboard state
([simulator testing](simulator-testing.md)).

## Baselines and their review

- Recording is explicit, through a flag the run sets. Review every changed image, then run
  without the flag. Never accept an image automatically because an OS, font or Xcode change
  moved it.
- A comparison fails when an image's size differs, when a selected scene has no baseline, or
  past a stated tolerance: for example a color sample more than 8 of 255 from its baseline, or
  more than 0.03% of points differing by more than 24 in a channel. Write the failed image, its
  reference and a diff outside the checkout, and name them in the failure.
- Compare only against a baseline recorded under the same render identity. A run that names a
  baseline from another identity reports the mismatch as unmeasured, not every page as changed;
  an ordinary run on a host with no matching baseline skips the suite visibly. Record again
  after an OS, runtime, Xcode or display-setting change. A scene added after the baseline fails
  until it is recorded.
- Check small baseline sets in. Keep large ones, such as every page at device resolution, out of
  Git with their render identity. A separate baseline directory serves a run that must leave the
  checked-in baselines alone.
- To check that a change leaves a page exactly as it was, compare two runs pixel for pixel,
  reporting each differing image's largest channel difference, the number of differing pixels
  and the box of those over a level. Materials and alerts change by a few levels between runs of
  one build, so a small peak with nothing over 8 is noise. When system-drawn content changes
  between runs, such as a status-bar clock, compare the band that holds the subject.

## Galleries and comparisons

- A gallery shows every scene side by side across profiles, grouped by area with the condition
  that brings it about, with choices of variant, render kind and profile and a text filter.
  Generate it into an output folder that Git ignores; rebuild it from an existing output without
  rerunning. A gallery app or target is development-only: never released, never run on push.
- Mark changed scenes and link each to its baseline ("before") and a diff, such as the new image
  faded with the changes in red.
- Photographs of real interactions, taken as system screenshots, form a separate review gallery
  and never enter the window-render baseline. Before each capture, check that the expected state
  and actions are present, and inspect the images: a passing semantic assertion does not prove
  that the photograph shows the menu. Never substitute app chrome, a confirmation dialog, a menu
  preview or a stack of action labels for the opened system presentation.
- Snapshot builds and runs are heavy work and go through admission
  ([shared host](shared-host.md)). A script that photographs on several hosts at once takes
  admission for each job and leaves at least one of the guaranteed `HEAVY_SLOTS` for other
  sessions. Slots above `HEAVY_SLOTS` are admitted only while the host shows spare capacity; a
  script never plans on them.

## Window renders and system screenshots

A window render and a system screenshot establish different things.

- A window render is the app's own pixels, drawn in process. It is deterministic, so regression
  comparisons use it. It omits what the system draws: the menu bar, status bar, camera cutout,
  home indicator, the window's shadow, and on the Mac the window server's Liquid Glass and blur.
  A sidebar's glass draws flat in the window's background color, so text scrolled under a
  title shows through it, and vibrancy appears only as far as the renderer reproduces it from
  each layer's color matrix. A render of a hosting view alone also omits what the window adds
  or presents: the toolbar, sheets and popovers. A sheet rendered alone has no window behind it,
  and PDFKit's highlight layer is left out. Exclude scenes whose render would say nothing for
  these reasons, or whose content follows the clock or the OS version, recording the reason.
- A system screenshot shows what the system composited at that moment: `simctl io screenshot`
  on a simulator ([simulator testing](simulator-testing.md)) or `screencapture -l` of an owned
  Mac window. It serves design review, not pixel regression.
- A Mac content render at a mobile canvas size is a Mac render, with Mac controls and each
  view's own minimum size. It is not iOS safe-area, system-toolbar or compact-layout evidence.
- An in-process catalog cannot open context menus, swipe actions or toolbar menus: SwiftUI
  exposes no presentation bindings for them, and a unit test cannot synthesize the touches, so
  they need a UI-test lane with real gestures. On the Mac, menus, context menus and menu-bar
  commands open only in front, which is [foreground work](#foreground-work-is-a-separate-lane).
  The open and save panels, Share, Mail, notifications, tooltips, the drop highlight and the
  Dock badge are drawn by the system and need lanes of their own. A catalog that does not cover
  them does not show that the platform prevents capturing them.
