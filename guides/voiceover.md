# VoiceOver

These mechanisms and lessons apply when the stated capability is present. Original
measurements establish their recorded platform and workload; they do not establish
universal behavior on later operating systems or in a different application.

This guide says what each VoiceOver lane establishes and how speech evidence is recorded and
read. The lanes have their own guides: [simulator VoiceOver](voiceover-simulator.md),
[Mac VoiceOver](voiceover-mac.md) and the [hosted Mac runner](hosted-runner.md). What VoiceOver
itself does with tables, links, rotors and role phrases is in the knowledge articles on
[iOS VoiceOver](../knowledge/apple/voiceover-ios.md),
[Mac VoiceOver](../knowledge/apple/voiceover-mac.md),
[VoiceOver and tables](../knowledge/apple/voiceover-tables.md) and
[accessibility](../knowledge/apple/accessibility.md); these guides keep the testing method and
the harness behavior.

A *speech session* is one fresh launch of the app under test with one step list, recorded as
one transcript. A hosted *run* is one dispatched workflow, which holds many speech sessions in
one job. Every lane reads speech through Apple's
[XCUIVoiceOverService](https://developer.apple.com/documentation/xcuiautomation/xcuivoiceoverservice);
the Mac observer checks AppKit's
[value-changed notification](https://developer.apple.com/documentation/appkit/nsaccessibility-swift.struct/notification/valuechanged)
contract.

## Lanes and what each establishes

- **Native accessibility tests** (in-process AX queries, XCTest snapshots, the Mac
  accessibility observer) establish the app's labels, traits, values, notifications and actions.
  They do not establish what VoiceOver says or the order it reads in. XCTest's accessibility
  audit names only the controls it flags, so print the frames of the controls of interest beside
  its issues. See [background Mac testing](background-mac-testing.md).
- **Simulator VoiceOver** records real VoiceOver speech on owned, muted, headless simulators,
  with no device, window or sound. It establishes what VoiceOver reads on iPhone and iPad and
  where its cursor and rotor move. Stock simulator VoiceOver activates nothing.
  See [simulator VoiceOver](voiceover-simulator.md).
- **Mac VoiceOver on the hosted runner** records real Mac speech on a disposable GitHub-hosted
  runner, which takes over no workstation. It cannot serve a check that needs a listener or a
  decision between two steps. See [Mac VoiceOver](voiceover-mac.md) and the
  [hosted runner](hosted-runner.md).
- **Physical iPhone and iPad** establish what the simulator cannot: VoiceOver's own activation
  and what follows it. See [below](#physical-iphone-and-ipad) and
  [device testing](device-testing.md).

## Acceptance rule

A simulator VoiceOver transcript is acceptance evidence for what VoiceOver reads on iPhone and
iPad: the content of each phrase, their order, and where the cursor and the rotor move. Record
such a session as a simulator's, with its device type and runtime where a device's model and
OS would stand. Do not ask for a device session to hear the same reading again.

A physical device is still needed for:

- VoiceOver activating the item under its cursor: a button, a link, an item's default action;
- an action performed from the rotor, such as a page action or Inspect Image;
- a page turned in landscape;
- on iPad, what VoiceOver reads after an activation. iPad VoiceOver asks again for the items
  round its cursor after it activates something; a simulator's VoiceOver receives the double
  tap as a plain touch, does not know anything was activated and reads on from the items it
  held. Run the moves that follow an `activate=` step on a device, or make the same change
  without an activation (for example from an app timer), before filing or fixing what a
  simulator read there.

A change to what VoiceOver reads needs no device session. A change to what an activation or a
rotor action does needs one, for that step. Where a simulator and a device differ, the device
result stands and the difference is recorded. Before proposing a device session, say what it
would show that a simulator cannot; a check said to need a finger usually needs a timing or an
input that a UI test can make.

The comparisons behind this rule were made on stock iOS 27.0 simulators (Xcode 27.0) against a
physical iPhone 17 Pro Max and iPad Air 13-inch (M3) on iOS and iPadOS 27.2, October 2026. The
simulator runner now defaults to iOS 27.2 with
[guarded cursor activation](voiceover-simulator.md#guarded-cursor-activation). That hook is a
diagnostic qualified for one runtime build and one VoiceOver binary; it does not move
activation acceptance off the device.

A Mac speech session on the hosted runner counts on the same terms as one on a workstation.
Record a Mac transcript offered as evidence at a fixed pause between keys.

## Recording speech evidence

- Record the app's build revision (with `-dirty` when tracked files were edited), the OS and
  Xcode builds, the device or simulator type and runtime, a hosted runner's image and image
  version, window size or orientation, text size and the steps. Say whether anyone listened.
- A session that completes is not an acceptance result. Read the transcript against the visible
  text, starting with its first phrases. A fresh accessibility label is not speech.
- A screenshot shows what is on the screen independently of every accessibility snapshot.
  Take screenshots of the isolated app only after checking its bounds: the first Mac XCTest app
  frame was invalid and its screenshot showed the desktop.
- Export text attachments one bundle at a time. The attachment can hold events that
  xcodebuild's console dropped (below).

  ```sh
  xcrun xcresulttool export attachments --path SESSION.xcresult --output-path DIR \
    --filter '*.txt'
  ```

- For a before-and-after comparison, merge main into the branch first and take as "before" a
  commit that holds that main and only the change's fixture. Main moves within the hour, and a
  commit landing between two recordings can change what VoiceOver does. Build "before" in a
  second worktree.
- Record evidence at a fixed pause. Advancing as soon as a key's first phrase arrives is for
  exploring: it cuts short whatever follows that phrase and once recorded a control's hint in
  place of its name. Rerun a failure first seen that way at a fixed pause before reporting it.
- Restore every VoiceOver and scripting setting a session changed, and verify the restoration
  with an independent read.
- A passing session shows that VoiceOver read correctly in that session. It does not prove a
  fault absent when the condition that triggers it may not have arisen; record which.
- List what was not heard. A session that was selected but produced no valid transcript (silent
  VoiceOver, host pressure, a lapsed device authorization, an observation timeout) is
  unmeasured, with its cause, and never green.

## Speech fixtures and reference views

- Use original synthetic content, generated deterministically, never a private or licensed
  book. Keep generated projects, build products and result bundles out of Git.
- Use no word VoiceOver uses for a role or state ("link", "image", "heading", "table", "group",
  "button"): such a word in a transcript is then VoiceOver's.
- Give positions numbered words and each line a unique last word, so a phrase shows exactly
  where VoiceOver is. Put the distinguishing words first: phrases are cut at 64 characters.
- A deterministic fixture establishes layout and accessibility values, not speech or focus
  order.
- Before calling a behavior the app's, hear the same content in a stock view: AppKit's own
  `NSTextView` in TextKit 1 and TextKit 2, or Safari showing the same HTML
  ([Safari as a reference](voiceover-mac.md#safari-as-an-independent-reference)).
- Put the variants to be heard in one commit behind a launch argument the app reads from
  `UserDefaults`, give each session its own, and remove the commit when one is kept.

## Harness pitfalls across lanes

- `XCUIVoiceOverService.currentSpeech()` returns at most 64 characters of a phrase, and a
  phrase identical to the one before is recorded once. A move that returns to the same item
  leaves no line: `left` straight after `right` repeats the item, and turning round needs two.
- A hint follows a move after a delay: about 2 s in the first workstation sessions (macOS 27.0),
  about 3 s after arriving at a column or heading, entering text or closing a menu in hosted
  sessions (macOS 27.0.1). Within a fixed pause the latest phrase can be the hint; keep every
  phrase with its time instead of only the last.
- On the Mac a second phrase within about 50 ms replaces the first (macOS 27.0.1). A listener
  hears the second; the transcript can hold both.
- Under heavy load the service can hand back the phrase from before a move, which reads as one
  item said twice and the next missing. After a repeated phrase, wait up to 3 s for a new one.
  A phrase twice running is one entry heard before and after a step that did not register.
  Compare counts moving forward and back before blaming the app.
- A step records the phrase standing when it ends. Where VoiceOver speaks by itself, as after a
  page turn under its cursor or during Read All, record every phrase for a set time with a
  listening step, and send no touch or move inside it: either stops the reading.
- A transcript that begins in an editing field, with the keyboard's keys read after the
  content, is not a reading-order result.
- xcodebuild's console lost 3 of one device run's 160 event lines, consecutive moves, that the
  result-bundle attachment kept. Check a gap against the attachment.
- XCTest cannot perform VoiceOver's three-finger scroll or the two-finger swipe for Read All.
  Its synthesized hardware keys did not reach VoiceOver on a physical iPad.
- XCTest's stop-on-failure exception can bypass Swift `defer`. Use Swift errors and
  `continueAfterFailure = true`, restore VoiceOver from teardown, and still verify the state
  independently after transport failures or forced termination.
- VoiceOver keeps settings from one speech session to the next: Mac cursor tracking and the
  rotor menu last shown, and a device's rotor setting. Settle them at the start of a session
  and end a session in the state it began in, orientation included.
- Other work disturbs speech. On the Mac VoiceOver announces other processes' windows and
  menus. Another agent session's tests on the same device bring their own app forward or switch
  VoiceOver off; discard such a run. At load averages in the hundreds to about 1,000 on the
  shared host, simulators stayed silent, `devicectl` timed out and XCTest failed with "Critical
  process xctest crashed"; record those sessions as unmeasured with the load.
- A crash of the app under test, and the dialog macOS shows for it, spoil the later sessions of
  a run. A probe that logs an accessibility attribute by reading that same attribute recurses
  until the app crashes.

## Observing the rotor HUD and other transient overlays

VoiceOver's rotor shows as a HUD that no accessibility query returns: on iOS it is in the
device screenshot, and on the Mac it is a window of its own that shows only in
`screencapture -x`. To observe the rotor category from screenshots with Vision text
recognition:

- Accept a category only on an exact label, confidence of at least 0.8 and a position inside
  fixed center bounds, in two consecutive frames that match each other and differ from the last
  accepted category, within a short observation deadline (3 s in the qualified observer).
- Run several recognition passes per frame: full screen first, then crops in normalized image
  coordinates. Map each crop's boxes back to full-screen coordinates before applying the same
  confidence and position bounds. The first accepted label wins; a later pass never replaces it.
- Let only a verified category permit navigation keys. Reverse the issued turns in the same
  cursor context and assert that the rotor is restored.
- Keep several early screenshot and OCR pairs as well as the deadline frame. A HUD can have
  vanished by the last capture, so a missing final overlay does not explain a failure.
- Qualify an OCR change offline: replay the recognizer against hashed images with expected
  labels, including visually reviewed images with no HUD whose expected label is null. Refuse
  existing output, record per-pass candidates, image hashes and compute mode, and exit nonzero
  on a mismatch while still writing the report. Never lower the label, confidence, position or
  consecutive-frame requirements to pass.
- A Vision compute-resource error is its own outcome. A CPU-only retry (`usesCPUOnly`, which
  the current SDK marks deprecated) does not establish the device observer's compute mode.
- A single-image replay does not qualify consecutive-frame stability, speech, rotor navigation
  or hardware. Vision results change with the runtime; record the toolchain and compute mode
  with each new measurement rather than rewriting an old one. Offline recognition qualifies
  the observer; hardware runs establish acceptance. Never assign an observer or transport
  failure to the app without a separate reproduction.

## Physical iPhone and iPad

The device procedure (an agreed window with the owner, the reservation and handoff, preflight,
passcodes, `devicectl` states and timeouts) is in [device testing](device-testing.md). Approval
of a run covers installing and launching the app, not operating the device by hand. The
VoiceOver-specific steps:

- Preserve a VoiceOver session that was already on. XCTest's VoiceOver service enables
  VoiceOver if necessary and restores the original state on normal completion. A probe that
  fails or is stopped part way leaves VoiceOver on, on a device the owner then picks up: read
  the state from the Mac and switch it off, then read it back.

  ```sh
  xcrun devicectl device info voiceover --device DEVICE_ID
  xcrun devicectl device settings voiceover --device DEVICE_ID --disable
  ```

- Count xcodebuild's start into the deadline: on a busy Mac it took nearly five minutes to
  begin a session whose steps then took one.
- A session that ends before its first step with "Timed out while enabling automation mode"
  has met an expired UI-automation authorization. Stop; a retry shows the prompt again on a
  device the owner may be holding. The same error once cleared by itself half an hour later.
- While VoiceOver is on it reads whatever the device shows, such as an arriving notification
  or the app that was in front. Such a phrase replaces the one a step should have recorded and
  its text is the owner's. Delete that session's log, result bundle and screenshots unread and
  run it again; classify a withheld phrase only by a comparison that prints true or false.
  Do not stream VoiceOver's own log on a device: it holds whatever else the device did.
- Do not perform an action that changes the owner's state, such as Copy, which replaces the
  clipboard; let unit tests perform it.
- Run the same steps with VoiceOver off as plain touches to tell a VoiceOver failure from the
  app's.
- Distinguish VoiceOver's activation from a plain touch with a double tap away from the cursor
  item's activation point. A keyboard activation can leave the previous phrase standing while
  the cursor has reached the target; compare the next forward and backward moves.
- The last item repeats its phrase, and so does a second item with the same label: one move
  back tells them apart. After an item's last action the rotor says "Activate Default" and
  starts again, so the list has been heard whole once that phrase comes.
- Gestures observed on a physical iPhone 17 Pro Max and iPad Air 13-inch (M3) on 27.2, October
  2026: XCTest's two-finger turn moved the iPad's rotor, one setting at a time only at its
  smallest size, and in thirty turns of several sizes never moved the iPhone's. A landscape
  iPhone registered only the upward flick. A touch on an item with actions put the iPad's
  rotor back on Actions, so turn the rotor after the touch that places the cursor. A rotor
  step and each of VoiceOver's own flicks took about 6 s under XCTest.
- On a busy Mac a swipe was once taken for a touch and moved the cursor to the item under it.

## Human review of generated speech

Generated spoken output (descriptions, localized vocabulary) needs native-speaker review
separate from automated checks. Generating examples, or passing a wording test, is not a
review.

- Publish a review packet with stable case IDs, the exact utterance per language, the input
  and a rendered image for context. Identify the snapshot by its revision and a source
  fingerprint that includes uncommitted changes; the revision identifies code, not approval.
- Reviewers state their language, region or teaching convention, their relevant experience
  and exactly which case IDs they covered. A partial review is useful when its coverage is
  recorded.
- Read each utterance aloud or listen through a host voice, and paraphrase what was understood
  before looking at the image or intended structure; then compare.
- Mark each case accept, revise, unclear or not reviewed. A revision gives the complete
  replacement utterance and the reason or regional preference.
- Keep wording review separate from listening and screen-reader QA (platform, voice, locale,
  rate, pronunciation and pause problems). Listening is useful QA, not a gate on vocabulary
  that already has sourced support.
- Source support and human validation are distinct statuses. Agreement with an upstream
  vocabulary is not proof of human review: upstream entries can cite machine translation, and
  a test named for one language can run another. Prefer a rule for the actual construct, then
  a test in the requested language, then a symbol name.
- Record acceptable regional alternatives and unresolved cases instead of declaring universal
  approval. After accepted changes, update independent regression expectations, regenerate the
  packet and keep the remaining unreviewed coverage visible.
