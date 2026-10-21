# Scenes and recovery

These mechanisms and lessons apply when the stated capability is present. Original
measurements establish their recorded platform and workload; they do not establish
universal behavior on later operating systems or in a different application.

## Durable recovery and actor isolation solve different failures

Durable recovery survives a process death; actor isolation only orders steps within one process.
Design for both. These are patterns, not one storage schema for every app.

Lifecycle:

- Save the lifecycle record before reading source bytes, so a death there becomes a durable
  "interrupted" failure at the next launch rather than a phantom in-flight item.
- Persist an expensive intermediate result (for example extracted text) before the next stage
  starts, so an interrupted stage resumes from it without rereading the original. Write it to a
  `.partial` sibling through its creating descriptor, synchronize, and move it into place before
  closing the descriptor.

Manifests:

- Two individually atomic files are not an atomic pair. Write each mutation as one checksummed,
  monotonically numbered generation to two independently atomic copies. At startup select the
  newest valid copy and repair a missing, corrupt or stale peer.
- Equal-generation disagreement, two invalid copies and a future schema version fail with typed
  errors. They never become an empty store, and their files are left untouched. Report recovery
  through stable codes.
- Keep launch reconciliation cheap: presence checks, not hashing every file. Keep an entry whose
  files are missing for a later restore to complete, move unreferenced folders to quarantine
  rather than deleting them, and delete only what checksummed metadata proves replaceable.
- Rebuild a lost manifest only on explicit request, admitting only folders whose metadata and
  content fingerprints validate and preserving the damaged copies. Never rebuild automatically.
- For a derived pair of files written separately, detect a torn pair on load (for example a
  count or dimension check), give each writer its own directory, and keep the pair rebuildable
  from source.

Versions and identity:

- Keep content versions immutable. Build a replacement completely, then swap it in under a new
  ID; a failed, unchanged or duplicate update deletes nothing, and nothing derived from the old
  version silently moves onto changed content.
- Verify an irreplaceable source against its fingerprint before rebuilding anything from it. A
  missing identity means unknown and never matches: do not backfill it from the component now
  running. Advance a recorded identity only after the write it describes.
- Delete the manifest entry first, then the files, so an interrupted deletion leaves a folder
  that reconciliation keeps.

Actors:

- An actor serializes each step, not a multi-await operation. After every suspension, re-read
  whether the object being updated still exists with the same authority, and write nothing
  otherwise. Distinguish an object deleted meanwhile (cancellation) from one that another owner
  took over, in the error the caller sees.

## Scene restoration is not just view reconstruction

Keep app-owned shared models and services, per-scene state and stable scene identities separate.

- On iOS, a scene the system restores keeps its `UISceneSession.persistentIdentifier`, but
  SwiftUI gives it no user activity: its restoration activity holds only SwiftUI's own scene
  identifier, and `onContinueUserActivity` is not called. Neither the session's
  `stateRestorationActivity` nor `@SceneStorage` restored an app identity in the same run
  (iPhone Duo Simulator, iOS 27.1, Xcode 27.1, October 2026). Keep an app-owned record from
  session identifier to scene identity.
- Write that record when the session attaches its content, not when the system saves scene state
  as the app leaves the foreground, so a foreground kill or a crash keeps it. Keep it
  content-free at the class readable after first unlock, so a background launch on a locked
  device can still release sessions discarded while the app was not running.
- When the system discards a session, release what only that session held, unless another
  session still shows it. Run release passes one after another, keep a failed release listed,
  and retry it at each launch. A scene with no identity after a bounded wait offers a choice and
  Close Window rather than showing another scene's content.
- Connected scenes do not establish retirement: archived sessions stay in `openSessions`, and a
  disconnected scene is not necessarily discarded. A snapshot taken at render time says nothing
  about callbacks that come later.
- On iOS, `handlesExternalEvents(matching:)` prefix-matches. Give each additional window an
  identifier longer than the primary's (the shared prefix, a dot and its session) so activating
  it never opens the main scene.
- Value-keyed scenes reselect an existing window for the same value; on the Mac, open windows by
  value and SwiftUI restores the value. Default SwiftUI restoration resolves saved values
  against the restored model; show a placeholder for a value that no longer exists rather than
  keep deleted content.
- Route external events (file opens, Spotlight activities) through the shared model and focus
  the existing window. Start shared services idempotently from whichever scene connects first.
- Decide app-wide interruption from the aggregate scene phase, so backgrounding one window does
  not stop work while another window is active.
- A capability flag can be wrong for the current display: on the iOS 27.1 iPhone Duo Simulator
  `supportsMultipleWindows` stayed true on the outer display, so combine it with the live hinge
  state.

Evidence: [studywright measurements/audits/iphone-duo-acceptance-2026-10-07.md](https://github.com/vocaro/studywright/blob/f1d1178e03949b2a6fb20dc6d85618988c0d01b2/measurements/audits/iphone-duo-acceptance-2026-10-07.md).

## A scene can be active while its presentation is still moving

On the iPhone Duo Simulator (iOS 27.1, 24A94401), presenting over a full-screen cover that was
still rising after its scene became `.active` ended the app. Waiting for the scene's first
`.active` phase is not enough. Wait for a stable anchor instead: the content in a window with no
presentation of its own still moving.
