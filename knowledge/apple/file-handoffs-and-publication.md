# File handoffs and publication

These mechanisms and lessons apply when the stated capability is present. Original
measurements establish their recorded platform and workload; they do not establish
universal behavior on later operating systems or in a different application.

## Provider file URLs are temporary capabilities

- Use `NSItemProvider.loadFileRepresentation` and copy inside its callback, while the provider's
  temporary file is still valid. An optional file-URL representation supplies only the original
  filename; never use its path or its sandbox rights for the handoff.
- Check eligibility twice, in the extension's activation rule and again against the actual
  providers at runtime, rejecting text, images, remote URLs and mixed input. Define it exactly,
  for example one extension item with one conforming attachment, where alternative
  representations on that attachment are fine. On macOS, Sharing Services offers the extension
  according to the types the host provides, and a web link to a file is not a file
  representation.
- Copy with coordinated reads (`NSFileCoordinator`), bounded buffers (1 MiB), a total size
  limit, SHA-256 identity, progress, cancellation between reads and a deadline. Give provider
  materialization its own timeout. Validate cheaply in the extension and leave heavy processing
  to the app.
- Provider and native calls can outlive a cooperative deadline, and macOS can terminate the
  extension. Design so that only unaccepted staging is ever left behind.

## A complete staged directory's rename is acceptance

- Lease a unique `.stage-UUID` directory in the App Group for each invocation. After every file
  succeeds, write a versioned manifest and rename the whole directory to its UUID. That rename
  defines acceptance.
- Failure or cancellation before the rename drops the whole batch, including files already
  copied. After it, closing the sheet or the host app cannot revoke the intake.

## A Share extension cannot launch its containing app

`NSExtensionContext.open` does not launch the containing app from a Share extension. Hand off
through the shared container instead: the app polls the inbox while it runs and drains it at its
next launch, and the extension tells people to open the app when it is closed. Do not use
responder-chain tricks, arbitrary URLs as sandbox grants, Apple events, launch helpers or the
real work inside the extension. The extension's view controller owns its container view and
embeds the SwiftUI host as a child with its own root view.

## Acknowledge intake only after durable admission

- Admit a batch by atomically persisting the whole batch and an intake receipt, then acknowledge
  the inbox record. A crash between the two restores the receipt and cannot admit the batch
  again, even after its jobs were removed.
- A failed snapshot write rolls back the new in-memory jobs and keeps the intake ready. An
  unreadable existing snapshot blocks intake and cleanup, preserving the evidence for recovery.
- Capture the destination and settings with the batch at admission, and route every intake
  surface (share, Services, Open With, the file picker) through the same admission helper.
- Keep accepted copies while their jobs are retained, including failed, cancelled and completed
  history. Delete them only after all of an intake's jobs are durably removed; published outputs
  stay. Never expire accepted intake because the app is not running.
- Remove abandoned staging only after acquiring its kernel lease, so a live extension's staging
  is never touched. One app process holds the inbox-consumer lease for its lifetime: another
  copy of the app cannot admit the same records or delete the first copy's sources, and says so.
  Each retained job holds a shared reader lease that cleanup must take exclusively.
- Test hosts and fixture launches never consume the production inbox.

## Snapshot a selected file before reading it

- Require a regular final path component and open it without following that leaf. Stream it into
  an exclusive new destination while hashing and counting the bytes, and stamp the destination's
  protection class explicitly.
- Abort, leaving no published copy, on a special file, a symlink leaf, an existing destination,
  a short write, a stamp failure, or a change in identity, size, modification time or change
  time across the read. Never fall back to reading the selected URL.
- Copy a security-scoped file while its grant is live. Insufficient space for the snapshot is a
  safe failure, not a reason to read the untrusted path directly.
- Prefer the snapshot to a security-scoped bookmark when the content is needed later: a bookmark
  resolves to nothing once the file moves or a file provider evicts it.

## A selected file does not grant its parent directory

- In the macOS sandbox, a single file's scope never shows permission to create files in its
  parent. Publishing beside the source needs a folder grant, for example from the folder panel.
  A related-item grant (`NSIsRelatedItemType`, with an `NSFilePresenter` whose primary URL is
  the source, through `NSFileCoordinator`) is narrower: it covers a companion file, not numbered
  names, a hidden temporary sibling or later recovery access.
- AppKit reads Services input as file URLs from the Services pasteboard. Capture security-scoped
  access and bookmarks before the handler returns; a text path pasted by another application is
  not a grant. A Service is enabled under System Settings → Keyboard → Keyboard Shortcuts →
  Services. After installing or moving the app, open it once, and log out and in if the Services
  list has not refreshed.
- The system Open panel is not the type boundary. On macOS 27.0 a filtered-out row's text field
  read `AXEnabled` true, like an allowed row's, while the panel refused to select it. Validate
  whatever the panel returns, and do not assert a panel row's enabled state in UI tests.
- Capture the destination policy when admitting work, so a later preference change cannot
  redirect admitted work. A missing bookmark keeps the chosen policy with an actionable notice
  instead of silently substituting another folder. A missing, revoked, read-only or unmounted
  destination leaves the job recoverable.
- Publish without overwriting: an exclusive rename, `lstat` to detect occupied names including
  dangling symlinks, and a uniquely named hidden temporary sibling for a move across volumes.
  Journal the destination and its bookmark before each attempt, check the staged size before
  publication and the final size and digest before marking completion, and let recovery remove
  only its journaled temporary path. Never rename or overwrite a source.

Evidence: [Pagepour measurements/save-destinations/record.md](https://github.com/vocaro/Pagepour/blob/68f508d14c2a2133592027eb89806009bccf0326/measurements/save-destinations/record.md).

## App Intent file results last only through the shortcut

- A file-backed `IntentFile` result with `removedOnCompletion = true` is valid through
  downstream actions in the same shortcut and is deleted when the shortcut ends. It is not a
  durable URL to keep for later; the Shortcuts Save File action makes a lasting copy, so save
  before opening a result in another app. A crash can leave temporary copies for the system's
  temporary-file cleanup.
- File-backed inputs and outputs use bounded coordinated copies; data-valued inputs arrive
  already materialized. A disk-full or copy error stops delivery and returns no files, while
  outputs already published stay.
- Keep copies of inputs with retained jobs, so a retry survives the provider URL or the shortcut
  going away. After the app ends, unfinished intent jobs restore as interrupted and need an
  explicit retry; running the shortcut again is a fresh invocation, not a continuation of a dead
  caller.
- A failed batch throws an actionable error and returns no files, even when some outputs were
  published; say how many were. Cancel only the invocation's own unfinished jobs, never adopt
  another caller's queued work, and never delete completed outputs on cancellation.
- Snapshot settings at invocation. An action never authorizes a purchase or takes a password;
  return an error that names the remedy instead. An evicted or inaccessible provider file fails
  before work starts.
- macOS 27's `LongRunningIntent` provides progress and cancellation hooks. Apple documents no
  macOS background time limit, so keep the app's own watchdog. Report progress as work done, not
  time; waiting behind other jobs adds none. Stop in Shortcuts and runtime expiration cancel
  only this invocation.
- A shortcut becomes a Finder Quick Action only when its Details enable Use as Quick Action for
  Finder; installing an App Intent installs no Quick Action. The extension setting has moved
  between macOS versions (Privacy & Security → Extensions → Finder, or General → Login Items &
  Extensions).

## Shared implementation

FileHandoffLib owns bounded coordinated copying, staging and inbox leases. Applications choose
accepted file types, App Groups, budgets and the durable admission transaction.
