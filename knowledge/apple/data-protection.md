# Data protection

These mechanisms and lessons apply when the stated capability is present. Original
measurements establish their recorded platform and workload; they do not establish
universal behavior on later operating systems or in a different application.

## A background grant does not grant file access under lock

A continued-processing grant gives work runtime after the person leaves; it does not reopen
files the lock has made unreadable. With a passcode set and the screen locked, each file's own
class decided the outcome (iPad Air 13-inch (M3), iPadOS 27.0 24A5418b, August 2026; the same
139 calls unlocked, locked and unlocked again):

| A file's own class | Open while locked | Descriptor held open across the lock |
| --- | --- | --- |
| `complete` (A) | `EPERM` | `EPERM` on read and write |
| `completeUnlessOpen` (B) | `EPERM` | reads and writes |
| `completeUntilFirstUserAuthentication` (C) | works | works |
| `none` (D) | works | works |

- Every failure was `EPERM`. A directory's class did not gate its children's reads or writes.
  The one operation the directory decided was creating a file: only a class A directory refused
  a new file while locked.
- So `complete` fails a job the moment the screen locks, the case continued processing exists
  for. Class B lets work that already holds its descriptors finish and create new files in a
  class B directory, but a closed class B file cannot be opened under lock: a cold background
  launch, such as a `BGProcessingTask` on a locked device, cannot read it. Let that task
  reschedule and record why, or change what it reads; do not weaken the class to suit an
  opportunistic task.
- Keep content-free operational journals at class C, so a background launch on a locked device
  can record that it was refused.
- The `com.apple.developer.default-data-protection` entitlement sets the app container's
  default, which can be `complete`. Everything nobody stamps follows it, including the
  container's `tmp`, `Documents` and `Application Support`: staging in a class A `tmp` cannot
  create a file while locked. Set the class explicitly on every directory written under lock.
- Choose the class per artifact kind, in one place, with a switch that has no default so a new
  kind cannot compile until someone decides its class. A job directory that must work on a
  locked phone (class C) and a library of user material (class B) can rightly differ. Another
  product assesses its own data rather than copying a class.

Evidence: [studywright measurements/audits/os27-dataprotection-under-lock-ipad.md](https://github.com/vocaro/studywright/blob/f1d1178e03949b2a6fb20dc6d85618988c0d01b2/measurements/audits/os27-dataprotection-under-lock-ipad.md).

## A directory stamp governs only files created afterwards

Stamping a directory applies its class to the files and directories created in it afterwards. It
does not change children that already exist. Observed on the same iPad (iPadOS 27.0, August
2026) in an app whose container default was `complete`:

- A plain create, `Data.write(options: .atomic)`, an open `.partial` sibling, `moveItem`
  publishing it, `replaceItemAt` over an existing file, a nested directory created without the
  stamping helper and a file inside it all inherited the directory's class.
- `copyItem` carries the source's attributes, protection class included, and overrides
  inheritance: a file copied in from the container's `tmp` kept that file's class whatever the
  destination directory said. Stamp the destination explicitly after copying a file in.
- Every class could be set above and below the entitlement's default, from the default and from
  class D; the default does not clamp explicit stamps.

Rules that follow:

- Stamp containing directories rather than each write site, so staging files, atomic-replace
  temporaries and quarantined copies inherit the class and cannot drift weaker than what they
  preserve. Stamping at each write site drifts, because the code that writes a staging file is
  not the code that writes the artifact it becomes.
- Migrate existing data explicitly: walk a tree whose root is not already at its assigned class,
  and have each long-lived record's writer bring the existing file up to its class when it opens
  it.
- `createDirectory(withIntermediateDirectories: true)` stamps only the directories that call
  creates, so a shared parent's class would depend on launch order. Give the shared parent an
  owner and derive its class as the weakest class assigned to anything beneath it.
- Make the levels comparable (C below B below A) and test "staging is never weaker than its
  artifact" as an inequality.

Unresolved: an App Group container's root reported no class (`fcntl` returned 0 and Foundation
reported none) while a file created in it read back class A, yet a file could be created in it
while locked. Apple documents the entitlement for the app container only. On macOS 27.0 a job
directory in a team-prefixed group reported no class while new files reported class C to both
the app and its extension; in the iOS Simulator, group-container files reported none.

Evidence: [studywright measurements/audits/os27-dataprotection-stamping-fixed-ipad.md](https://github.com/vocaro/studywright/blob/f1d1178e03949b2a6fb20dc6d85618988c0d01b2/measurements/audits/os27-dataprotection-stamping-fixed-ipad.md).

## Pass a typed class and keep the creating descriptor

- `[FileAttributeKey: Any]` accepts anything for `.protectionKey`. A raw `String` with the
  class's spelling is accepted by `setAttributes` and `createDirectory(attributes:)`, throws
  nothing and applies nothing: the file kept the container default (iPadOS 27.0). Pass a
  `FileProtectionType`, and assert both that the typed value applies and that the raw string
  does not, so a Foundation change that starts honoring it is noticed.
- Create a class B staging file and hold it open in one call:
  `open(O_CREAT | O_EXCL | O_WRONLY)` returns the creating descriptor. Creating an empty file
  and reopening its path is a forbidden open of a closed class B file once the screen locks.
  Write and synchronize through the creating descriptor, rename or replace the destination while
  it is still open, then close it.
- Never truncate existing staging bytes. Remove an owned staging file on failure. A close error
  after committed publication does not make the durable bytes a failure.
- macOS enforces neither class, but the two types stay distinguishable through `Any`, so the
  type assertions run there too.

## Verify protection classes on a device with a strong default

Data protection does nothing on a Simulator and macOS does not enforce it, so a green Simulator
or Mac run proves nothing about enforcement. Assert the policy there and measure on hardware.

- Host the probe in an app whose container default is `NSFileProtectionComplete`. Then a file
  reading back weaker was stamped and one reading `complete` was not. A harness target without
  that entitlement defaults to class C and cannot tell a working stamp from a missing one.
- Read the class with `fcntl(fd, F_GETPROTECTIONCLASS)`. `attributesOfItem` and the
  `fileProtection` resource value echoed the container default rather than the file's own class.
- Run the probes as hosted unit tests in the product's own process and container; they need no
  UI-automation grant. Under an XCTest session `backgroundTimeRemaining` stayed at
  `greatestFiniteMagnitude`, so the locked host was not on a background budget.
- Check the preconditions rather than assume them: a passcode is set
  (`LAContext.canEvaluatePolicy(.deviceOwnerAuthentication)`, which does not prompt), every
  probe file reads back its stamped class before the lock, and the unlocked phases before and
  after the locked one pass.
- No API locks a device. `devicectl` has no lock command, and posting
  `com.apple.springboard.lockdevice` with `devicectl device notification post` was accepted and
  did not lock. Wait, bounded, for `UIApplication.isProtectedDataAvailable` to become false
  while the owner presses the side button, and skip when no lock comes.
  `devicectl device info lockState` flipped `passcodeRequired` within 5 s of the lock on an iPad
  (iPadOS 27.0), but on an iPhone it did not (see
  [device testing](../../guides/device-testing.md)), so the app's own observation decides.
- Write each result row synchronously (`fsync`) to a results file stamped `none` and held open
  across the lock, so a run killed mid-phase keeps its evidence.
- Neither an XCTest session nor a `devicectl` launch can start on a locked device (see
  [device testing](../../guides/device-testing.md)), so only a system-issued background launch
  observes a process starting under lock. UIKit's early protected-data Boolean read false on a
  `devicectl --no-activate` launch of an unlocked device, so it cannot stand in for the lock.
- For work spanning a lock, bracket it with protected-data observations. Work that ends before
  the first locked observation is void, and an unlock observed before the locked operation ends
  invalidates the run, even after a relock.
- Not yet measured: reboot before first unlock, which separates class C from D, and backup
  restore.

Device sessions need a reservation and an agreed window; see
[shared host](../../guides/shared-host.md) and [device testing](../../guides/device-testing.md).

## Shared implementation

FileProtectionLib provides typed attributes, class read-back, directory creation with a class
and exclusive creating descriptors. Its caller selects protection classes and migration policy.
