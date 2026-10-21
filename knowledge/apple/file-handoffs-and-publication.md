# File handoffs and publication

These mechanisms and lessons apply when the stated capability is present. Original
measurements establish their recorded platform and workload; they do not establish
universal behavior on later operating systems or in a different application.

## Provider file URLs are temporary capabilities

Copy an NSItemProvider file representation inside its callback while valid. Publish an App Group batch only after bounded coordinated copies and a complete manifest; the directory rename defines acceptance. Acknowledge intake only after durable app admission, and use leases so cleanup cannot remove another process’s retained source.

[Pagepour doc/mac-share-intake.md](https://github.com/vocaro/Pagepour/blob/e8cce638223f4751f4365b61ade888c3eeefb4bd/doc/mac-share-intake.md#acceptance-and-handoff). The small extension-to-app handoff pattern generalizes beyond PDFs; exact activation rules and source budgets do not.

## A selected file does not grant its parent directory

Beside-source publication needs the proper folder grant; a related-item permission is narrower than arbitrary sibling creation. Capture destination policy when admitting work, preserve missing/revoked grants as recoverable state, and verify cross-volume publication and crash journals without overwriting existing files or following dangling symlinks.

[Pagepour measurements/save-destinations/record.md](https://github.com/vocaro/Pagepour/blob/e8cce638223f4751f4365b61ade888c3eeefb4bd/measurements/save-destinations/record.md). Keep bookmarks, source ownership and final-output lifetime distinct; a later preference change must not silently redirect admitted work.

## App Intent results and cancellation need ownership boundaries

File-backed IntentFile results may last only through downstream actions in the same shortcut. Retain originals for retries, cancel only the invocation’s unfinished jobs, and distinguish a failed batch’s API result from already-published durable outputs. Snapshot settings and return actionable errors rather than triggering purchases or password UI from the action.

[Pagepour doc/shortcuts-conversion.md](https://github.com/vocaro/Pagepour/blob/e8cce638223f4751f4365b61ade888c3eeefb4bd/doc/shortcuts-conversion.md#failure-stopping-and-file-lifetime). Transfer the file-lifetime and caller-ownership model to other intents; Pagepour’s batch/error policy is a product choice.

## Shared implementation

FileHandoffLib owns bounded coordinated copying, staging and inbox leases. Applications
choose accepted file types, App Groups, budgets and the durable admission transaction.
