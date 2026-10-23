# Mac VoiceOver

These mechanisms and lessons apply when the stated capability is present. Original
measurements establish their recorded platform and workload; they do not establish
universal behavior on later operating systems or in a different application.

A Mac speech session records real VoiceOver speech of the app under test with three parts: a
key driver that sends VoiceOver commands, an XCTest probe that only records speech, and the
shared accessibility observer. The [hosted runner](hosted-runner.md) is where sessions run.
What Mac VoiceOver does with text, links, tables and roles is in
[Mac VoiceOver](../knowledge/apple/voiceover-mac.md) and
[VoiceOver and tables](../knowledge/apple/voiceover-tables.md).

## Where Mac sessions run

- A Mac speech session takes the keyboard focus for its whole length, which stops the owner
  and every other session on that Mac. Run Mac speech on the hosted runner.
- A session on the owner's Mac needs the owner's explicit authorization, and only for what a
  runner cannot do: someone listening, or stepping by hand. A brief, an older branch or an
  earlier approval of a mechanism does not authorize one.
  [Attended sessions](#attended-sessions) has the methods for an authorized session.
- Never run the runner's preparation commands on a workstation
  ([preparing a disposable runner](hosted-runner.md#preparing-a-disposable-runner)).
- Unsigned Mac UI-test runners did not complete on a workstation. A hosted build is signed ad
  hoc (`CODE_SIGN_IDENTITY=- DEVELOPMENT_TEAM=`) and needs no team, certificate or secret.
  Keep a personal team identifier out of Git.

## Speech capture and the key driver

- Use one automation controller: no competing agent, `swift test`, simulator UI run or manual
  VoiceOver command during a session. VoiceOver announces other windows and menus too, and any
  window or system dialog that takes keyboard focus ends the session. Launch a fresh instance of
  the app under test for each session and close earlier ones first.
- The probe polls `XCUIVoiceOverService.currentSpeech()` and prints each new phrase with its
  time. The driver sends the steps in order through System Events and waits a fixed pause after
  each VoiceOver command (5 s by default in the qualified driver). An optional mode sends the
  next step a set time after a key's first new phrase; it is for exploring only
  ([recording speech evidence](voiceover.md#recording-speech-evidence)).
- Send keys through System Events, not XCTest. XCTest returns from a synthesized VoiceOver key
  about 10 s later, because VoiceOver consumes the key; polling records each phrase as it is
  spoken.
- Use `currentSpeech()` alone. XCTest's `moveIn()` returned the previous phrase without
  entering when called right after VoiceOver started, and `testmanagerd` crashed once after
  five native moves while other tests ran. VoiceOver's AppleScript `last phrase` property and
  clipboard copying gave no usable speech, even with the scripting setting changed. Anyone
  exploring that route records and restores the setting and the clipboard and rejects an
  unchanged clipboard sentinel.
- Before every key, check that the app under test (or Safari, in a Safari session) is
  frontmost, that no dialog holds secure keyboard input (`kCGSSessionSecureInputPID` in
  `ioreg -l -w 0 -d 1`) and, on the owner's Mac, that the session still holds `mac-foreground`
  (`devices check`, [attended Mac sessions](shared-host.md#attended-mac-sessions)), and stop the
  session otherwise.
- Bring VoiceOver to the app's content by a change of keyboard focus through the accessibility
  API, never a click. A focus click moves the insertion point, and VoiceOver enters text and
  reads from there; a click near an edge can also trigger the app's own controls.
- Send an activation or a menu choice only when one of VoiceOver's last two phrases names the
  intended item, so a session cannot activate the wrong one.
- List other sessions' unit-test hosts (`pgrep -x xctest`) at the start and the end of a
  session: VoiceOver announces their windows.
- Stop a session as soon as VoiceOver names XCTest's "Automation Running" banner: its cursor can
  be on the banner, and the speech after that can be the banner's. Once a probe queries the app
  through XCTest, the banner took the VoiceOver cursor about every 30 s while keys were sent, so
  take XCTest snapshots of the app only in sessions whose steps are all observer steps.
- Write one transcript per session, merged by time: steps, phrases, observer events and fresh
  states.
- Leave several seconds between sessions: VoiceOver ignores its toggle while it is still
  quitting.

## VoiceOver state and restoration

- Read the original state with a read-only check; `0` is off and `1` on:

  ```sh
  defaults read com.apple.universalaccess voiceOverOnOffKey
  ```

  A Mac that has never run VoiceOver has neither the key nor a `VoiceOver` process; read that as
  off. Abort the session when the state cannot be determined otherwise.
- Toggle with Command-F5 sent through System Events, only when the state differs, and wait up to
  5 s for the key to show the new state. XCTest's `enable()` timed out on the Mac.
- Restore the original state in `finally`, rather than always disabling. Close any rotor or
  Actions menu first by sending Escape, and record that as a driver step: VoiceOver ignores its
  own Command-F5 under an open rotor or Actions menu, whether the list holds items or none, so a
  session that ends under one leaves VoiceOver on.
- A session whose VoiceOver will not return to its original state still writes its transcript,
  with the reason in a `NOT_RESTORED` line, and exits with a status of its own. Later sessions
  of the same job then begin with VoiceOver in the wrong state. Process cleanup cannot recover
  from killing the driver itself: verify restoration independently with the read above.
- Never edit system preferences, VoiceOver's AppleScript-control setting, TCC databases or the
  clipboard. Request a new Accessibility, Automation or device permission through the normal
  OS approval flow.

## Key commands

VO is Control-Option. Behavior was observed on macOS 27.0.1 hosted runners, October 2026,
unless noted; see Apple's
[VoiceOver text commands](https://support.apple.com/en-ca/guide/voiceover/cpvokys06/mac).

- Into and out of an item: VO-Shift-Down Arrow and VO-Shift-Up Arrow. Repeating VO-Shift-Down
  does not read successive lines.
- Next and previous item, and inside text the next and previous word: VO-Right and VO-Left
  Arrow.
- Read the line: VO-L. Next and previous line: VO-Down and VO-Up Arrow. The first VO-Down after
  entering text reads the rest of the current line from the insertion point. From an insertion
  point that is not at its line's end, a by-line move goes first to that line's end and the next
  one to the line after, so the first move can add no phrase; a selection event in the observer
  shows that it moved.
- Word: VO-W. First and last visible word: VO-Home and VO-End. Start and end of the text:
  VO-Shift-Home and VO-Shift-End.
- What is in the cursor: VO-F3; twice gives the total and visible line counts. Text attributes:
  VO-T. Read All from the cursor: VO-A.
- Activate: VO-Space.
- Rotor: VO-U. Its keys are plain keys: Left and Right Arrow between lists, Up and Down along
  one, Return to move to the item named, Escape to close. Send them only while the rotor is
  open, or the app takes them. The rotor opens on the menu it showed last, also in later
  sessions of a run. A list with nothing in it stays open after Return.
- Actions menu: VO-Command-Space. VoiceOver says "Actions menu" and its item count; Down and Up
  say each item, Return performs the last one said, Escape closes it ("Closing Actions menu").
  The list does not wrap. On a group the menu held the actions of what the group holds.
- Next heading: VO-Command-H. With Shift added VoiceOver asked for the next heading again, so
  go back with the rotor's list.
- Find Next Link and Find Previous Link: VO-Command-L and VO-Command-Shift-L. Previous went
  forward, in AppKit's own text view too.
- Find Next Table and Find Previous Table: VO-Command-T and VO-Command-Shift-T.
- In a table: VO-C and VO-R say the header of the cell's column and row, and twice read the
  rest of the column or row; outside a table VO-C reads the character under the cursor.
  VO-Shift-T, Apple's command for a cell's row and column numbers (twice for the table's size),
  said little in custom accessibility tables.
- Cursor tracking: VO-Shift-F3 turns it off or on again ("Cursor Tracking Off"). VoiceOver keeps
  the setting into later sessions, so a session that turns it off turns it back on.
- VoiceOver on and off: Command-F5.

## Accessibility observer

`src/swift/VoiceOver/voiceover-ax-observer.swift` reads what the app under test gives an
accessibility client, from outside the app and independently of XCTest. It needs Accessibility
trust and runs with a bounded duration. In a hosted session the driver runs it. Elsewhere use it
only on an app you own, and treat its steps that press, resize or move focus as UI automation
under the same authorization rules.

```sh
VOCARO_AX_ALLOWED_BUNDLES=BUNDLE_ID \
  xcrun swift "$(python3 scripts/eng source voiceover-ax-observer.swift)" PID 60 \
  lines next lines width=600 > ax-events.log
```

- It accepts only a process whose bundle ID is in `VOCARO_AX_ALLOWED_BUNDLES` (comma-separated),
  or Safari's, and a duration of 1 to 300 s (20 by default). It prints `TRUSTED` first and exits
  2 when untrusted. Each line starts with an ISO 8601 time in milliseconds, so events, steps and
  speech merge into one transcript.
- It registers for value, selected-text and layout notifications on every text area, again
  after each step because text areas come and go, and for value and layout notifications on the
  app. Each notification is an `EVENT` line with its source, the selection and the start of the
  value.
- After each step it reads every text area afresh: `STATE WINDOW` with the window size and text
  count, and `STATE TEXT` with width, characters, lines and selection. `lines` adds a `LINE`
  for each accessibility line, at most the first 500 of a text area whatever is on screen.
- Steps: `next` and `previous` press the app's page buttons; `press=LABEL` any button;
  `larger` and `smaller` choose text-size menu items; `width=POINTS` resizes the window;
  `focus`, `focus=N`, `focus=N.M` (a table cell's text area) and `focus=search` give keyboard
  focus without a click; `focused` prints what holds it; `caret=WORDS` puts the insertion point
  before those words; `follow=WORDS` presses a link by its own action; `action=NAME` performs a
  named action; `links`, `tables` and `actions` print what the app gives (below);
  `wait=SECONDS` only observes. With Safari's PID the steps are `width`, `focus`,
  `focus=address`, `tables` and `wait`. A single step `-` reads steps from standard input, so a
  driver can interleave them with VoiceOver keys; no steps only observes.
- `links` prints a text's own children, which Find Next Link walks (`CHILD`: role, what it is
  called, URL, actions, `FOCUSABLE` where a client can set its focus, its children), then the
  runs of its attributed accessibility string that carry a link or attachment element (`LINK`).
  A table cell's lines begin with `CELL`. `actions` prints each column, everything that holds
  it up to the window and any other element with a named action, as numbered `ELEMENT` lines
  with depth; VoiceOver's Actions menu holds the actions of the item under its cursor, so they
  show where the cursor must be. `tables` prints `TABLE`, `TABLEROW`, `TABLECELL` and
  `TABLEHELD` lines, or `WEB` lines for a page in Safari.
- A step whose target is absent prints `MISSING`; accessibility calls print their status. The
  run ends with `FINAL` values and `DONE`.

Reading it:

- A changed final value does not prove that the notification was delivered. Check for the
  value event after every page turn, resize and text-size change.
- The observer's presses test the app's actions and notifications, not VoiceOver's activation.
  For that, move VoiceOver's cursor to the control and send VO-Space.
- `AXPerformAction` returned -25200 (`kAXErrorFailure`) for a scroll action in a scroll view
  that did scroll; the status came from AppKit's entry point, not the app's handler. Read the
  next `STATE`.
- A window resize through the accessibility API is an AppKit live resize, with what that does
  to text views ([background Mac testing](background-mac-testing.md)).
- The selection in an event line tells a step that said nothing from one that did nothing.
- Read an element again rather than reuse a value. Treat neither XCTest nor the observer as
  speech.
- The observer still carries assumptions from the app it was written for: its value summary
  counts eight-character `word…` tokens, it finds page buttons by "Next Page", "Previous Page",
  "Scroll Forward" and "Scroll Backward", and it takes text areas that are not inside another
  text area as reading columns. Extend those for another app.

## Session grammar and per-session settings

- `vocaro_engineering.voiceover.grammar.sessions(text)` splits a step list into sessions at `;`
  or a line break, and each session into words as a POSIX shell would, with no comments. Quote
  a step that holds a space: `"activate=Next Page"`.
- The project's session runner gives each session a fresh app. A session can open with
  settings of its own, in any order before its first step: in the qualified runner the window
  width, text size, reading flow, launch arguments, pause, advance-after and a Safari page. The
  workflow's inputs are the defaults for a session that sets none. One run then holds sessions
  that differ in them, with one build.
- Refuse, before anything is built or waits for a runner, a setting that follows a step, is
  given twice or has an impossible value. The dispatcher runs the same check locally first.
- A setting of the whole runner, such as the link verbosity, is set once before the first
  session; sessions of a run cannot differ in it.
- A `ref` input can build one commit with the harness of another: the driver, observer, session
  and link-setting scripts come from the dispatched branch, the app and probe from `ref`. An
  older commit can then be heard, and two compared, with one harness. A run builds the commit
  its branch had when it was started; give the branch's name as `ref` to build what the branch
  holds when the job begins.

## Link verbosity

- What VoiceOver says of a link while reading depends on VoiceOver Utility, Verbosity, Text,
  "When encountering a link/attachment": Speak, Change Pitch, Play Tone or Do Nothing. A
  transcript holds speech and neither tones nor pitch, so record the setting with every run. A
  Mac whose VoiceOver was never configured has Speak.
- `src/swift/VoiceOver/voiceover-link-verbosity.swift` reads it, and given a choice sets it,
  through VoiceOver Utility's own window, then quits the utility, which writes the setting:

  ```sh
  xcrun swift "$(python3 scripts/eng source voiceover-link-verbosity.swift)" "Do Nothing"
  ```

  It prints `LINK VERBOSITY` and the value. It refuses to run unless `RUNNER_ENVIRONMENT` is
  `github-hosted` (status 1) and needs Accessibility trust (2); it exits 3 when the utility does
  not open, 4 when the setting is not found and 5 when the choice fails, printing the utility's
  accessibility tree for the last two (`--tree` prints it always).
- Never write the setting with `defaults`. A `com.apple.VoiceOver4/default` domain written
  before VoiceOver had ever run left it silent for the whole run, `ERROR 3` after every key.

## Safari as an independent reference

- A Safari session records what VoiceOver says of the same content as a web page, with nothing
  of the app in it. Run it on a hosted runner only: the session runner quits Safari first,
  opens the page as a file in a fresh Safari and keeps a screenshot from before VoiceOver comes
  on. Send keys to Safari and to nothing else, give the observer Safari's PID, and record
  Safari's version.
- On hosted runners (Safari 27.0.1, macOS 27.0.1, October 2026) Safari opened a local file with
  no question where it had never run. The runner's screenshots show the page white although it
  is laid out and VoiceOver's cursor is drawn. A link to a sibling file did not open ("Safari
  Can't Open the Page"), most likely because only the one file was given; serving the content
  over HTTP was not tried.
- VoiceOver started on the page or on the toolbar. Give the page keyboard focus, or the address
  field and then the page, to bring VoiceOver to it.
- A transcript in which `ERROR 3` and then VoiceOver's opening phrase follow a key is one in
  which VoiceOver quit and started again, in Safari as in the app; macOS's crash report is in
  the run's download.

## Reading VoiceOver's own code

- Read VoiceOver's code statically, without running or attaching to it
  ([shared host](shared-host.md)). Its classes are in `ScreenReader.framework`, which is only in
  the dyld shared cache; `lldb target create` refuses it, and `dyld_info` prints its code under
  its method names, `-[SCRTable statusDescription]` among them:

  ```sh
  dyld_info -disassemble \
    /System/Library/PrivateFrameworks/ScreenReader.framework/Versions/A/ScreenReader
  ```

- What it reads of an element goes through `AXFUIElement`, in
  `AccessibilityFoundation.framework` inside `AccessibilitySupport.framework`'s `Frameworks`.
- In that output a call goes to a stub and a string is an address, so neither is named. A
  helper that reads the shared cache as its own process maps it can write each stub's selector
  or function and each string's characters beside the line that uses it; no such helper is in
  this repository.
- VoiceOver's words are in the `.loctable` files of
  `ScreenReader.framework/Versions/A/Resources`, property lists by language. A word heard leads
  to its key and the key to the code: "empty" is `SCRGeneral`'s `empty` (macOS 27.0).

## Probing what VoiceOver asks the app

- On a throwaway branch, have the app append each query to a file in its temporary directory
  (`FileManager.default.temporaryDirectory`), with times in the transcript's format, and copy it
  from `~/Library/Containers` into the results after the sessions. `log show` on the hosted
  runner returned no line the sandboxed app logged.
- To see every request VoiceOver makes of a view, override AppKit's legacy methods, log and call
  `super`: `accessibilityAttributeValue(_:)`, `accessibilityAttributeValue(_:forParameter:)`,
  `accessibilityAttributeNames()`, `accessibilityParameterizedAttributeNames()`,
  `accessibilitySetValue(_:forAttribute:)` and `accessibilityPerformAction(_:)`. Every request
  to a view passes them, and some to an `NSAccessibilityElement`, though not those for its
  frame. A rotor's delegate sees only what VoiceOver asks of the rotor.
- Log on the view and leave the elements alone where they are what is being heard. With those
  methods overridden on an `NSAccessibilityElement` a link reported no `AXPress`, and an element
  that read its own title inside its logging override recursed until the app crashed. An
  override added to log can change what VoiceOver does: it focused a heading element that
  overrode `isAccessibilityFocused()` and not one that only took the focus.
- A call stack logged from the app's own handler says who moved something: VoiceOver's scroll
  arrives as a set of the scroll bar's value.
- Put variants in one run behind `UserDefaults` launch arguments. Add a missing driver step on
  the throwaway branch and dispatch from it with the real branch as `ref`.
- The rotor is a window of its own and shows in nothing but a screenshot: capture it with
  `screencapture -x` into the results.
- To learn what the system voice makes of a character without playing sound, write its
  synthesis to a file and compare durations: `say -o FILE.aiff TEXT`. "Sign" with U+FFFC after
  it lasted as long as "Sign" alone, 0.70 s, and the character alone 0.01 s (macOS 27.0, default
  system voice). What VoiceOver voices for it was not heard.

## Attended sessions

These are methods for a session on the owner's Mac that the owner has explicitly authorized.
Nothing here authorizes one. The general rules for any attended session (announcements,
availability intervals, restoring settings) are in
[shared host](shared-host.md#attended-mac-sessions); these add what VoiceOver needs.

- Validate the exact app path and PID before each observation, and stop using that binding when
  the app ends: a later observation can relaunch the app without its fixture arguments. Where
  the app's own keys suffice, dispatch `NSEvent`s inside the owned process rather than global
  input ([background Mac testing](background-mac-testing.md)).
- Native menus and real VoiceOver need the app in front. Stop when another app takes the
  foreground. Keyboard observations from a background window do not establish that a real
  keyboard reaches every menu or overflow item.
- Send System Events keys only from a fixed allowlist, each guarded immediately before sending
  by the exact PID, the foreground process and the secure-input state, under a deadline (at most
  180 s in the qualified helper) and with a receipt per key. A command is measured only when its
  receipt is present. Allow VO-Space only when recent observer speech names the target.
- Change VoiceOver's state only with the owner's separate approval to do so, only when the
  requested state differs from the current value, and verify the result. Record the original
  state first. An observer started after VoiceOver was turned on finds it on, so its own cleanup
  does not restore a Mac on which it was off: turn VoiceOver off before closing the session.
- Restore VoiceOver before Full Keyboard Access (`AppleKeyboardUIMode`), wait for the VoiceOver
  process to exit, then verify both original values. Restore the previous foreground app only
  if the session still owns the foreground.
- An XCTest observer can use the public VoiceOver service, bound to the owned PID and app path,
  without creating `XCUIApplication`. A passing exposure assertion (every control named) does
  not establish actions or rotor operation: keep their resulting state and key receipts
  separately. Serialize such an observer with physical-device XCTest runs and record the
  observer binary's hash.
- After any interrupted run, restore VoiceOver explicitly and verify its original state before
  returning the Mac to the owner.
