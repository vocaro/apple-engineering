# App extensions

These mechanisms and lessons apply when the stated capability is present. Original
measurements establish their recorded platform and workload; they do not establish
universal behavior on later operating systems or in a different application.

## Qualify an extension's memory limit on the target hardware

An app-defined ExtensionKit extension (an `AppExtensionPoint.Definition` with no user interface,
launched with `AppExtensionProcess`) was held to 35 MiB on an iPhone 17 Pro Max and an iPad Air
13-inch (M3), iOS and iPadOS 27.2 (24B5110a), October 2026. `os_proc_available_memory` read
about 34.4 MB at every launch, and the iPad's jetsam report named the extension killed for
`per-process-limit` at 2,240 pages of 16 KiB. A text-only conversion peaking near 20 MiB
finished; work that peaks at hundreds of MiB on a Mac ended within half a second with
"Underlying connection interrupted". The iPhone wrote no jetsam report for the same kills.

- The Increased Memory Limit entitlement (`com.apple.developer.kernel.increased-memory-limit`)
  on the extension did not raise the limit on the iPad. The App Store Connect API's
  `capabilityType` did not accept that capability, so it had to be enabled in the developer
  portal.
- Apple DTS has said each extension point defines its own fixed limit, which overrides the value
  the entitlement modifies, and that there is no way past it. Developers report about 100 MB for
  a Quick Look preview extension, about 15 MiB for network extensions and 20 MB for File
  Provider extensions on iOS. The 35 MiB figure belongs to the tested extension kind, devices
  and OS, not to every extension point.
- The iOS Simulator enforces no limit: `os_proc_available_memory` returns 0. On macOS 27.0 an
  extension dirtied 4 GiB without being stopped; `memorystatus_control` returns `EPERM` without
  root, even for a process's own limit, and RunningBoard's log names none.
- Measure on the device before choosing an extension as a process boundary: record
  `os_proc_available_memory` at each job's start and its minimum during the job, dirty memory in
  steps (a ballast) to find where the extension is killed, read the jetsam reports, and compare
  the kernel's lifetime peak (`ri_lifetime_max_phys_footprint`) with the same work in process.

Evidence: [PDFReflowLib measurements/converter-extension-693/record.md](https://github.com/vocaro/PDFReflowLib/blob/dc89a4eccecb99943661709887fd2a61a1a51b29/measurements/converter-extension-693/record.md#the-ipad).

## invalidate() withdraws the host's hold; it does not end the process

Observed with an ExtensionKit host on macOS 27.0 (26A428) and an iOS 27.0 Simulator in October
2026; process reuse was confirmed on the iOS 27.2 devices.

| What the host did | What happened |
| --- | --- |
| Asked for a second `AppExtensionProcess` while the first lived | The system returned the same process; unguarded, it accepted both sessions |
| Called `invalidate()` on an idle process | RunningBoard suspended it, and the next launch got it back |
| Called `invalidate()` after work that held a file lock | RunningBoard suspended it and killed it about 127 ms later with `0xDEAD10CC`, "suspended while holding a shared file lock", in 6 of 6 runs |
| Cancelled the session of a running extension | Its cancellation handler exited within about 22 ms; later launches got new processes |
| Cancelled the session of a suspended extension | The next launch got the suspended process back; it ran the old cancellation and exited, the new session never heard from it, and the launch after that failed too, with no error reported |

The lock behind the kill was Metal's `archiveUsage.db` lock in the process's temporary folder,
which Vision work took even under CPU-only compute, so the kill is not a compute setting. Apple
documents that `invalidate()` does not terminate a process.

- End each job by sending an explicit finish message on which the extension calls `exit`, or by
  cancelling the session of a running extension. Then wait until the process is gone before
  launching the next. Never `invalidate()` a process that must end.
- Keep a one-session guard in the extension so a reused process shows itself.
- Keep a watchdog for a session that never answers. `onInterruption` fired for 15 of 17 observed
  exits, so it is not completion evidence on its own.
- On iOS, a suspended extension that holds such a lock is killed, so whether an extension keeps
  working while its host is in the background needs its own device check.
- An app-defined extension launched without user approval (`unapprovedCount` 0) on the Mac, the
  Simulator and both devices, and the extension monitor listed it within milliseconds.
- launchd starts an XPC service at most once every 10 s, which slows suites that need a fresh
  service process per test. The ExtensionKit extension was not throttled; launches took 12 to 95
  ms.

Evidence: [PDFReflowLib measurements/converter-extension-693/record.md](https://github.com/vocaro/PDFReflowLib/blob/dc89a4eccecb99943661709887fd2a61a1a51b29/measurements/converter-extension-693/record.md#check-5-lifetime).

## Linking, resources and App Groups need per-platform checks

Release builds link local packages statically into each binary that uses them. An app-hosted
test bundle changes that: when the app and its hosted tests (or the app, an extension and the
tests) all link one package, a Debug build makes it a framework and embeds a team-signed copy in
the app's `Frameworks`.

- XcodeGen 2.46.0 gives a multiplatform target (`supportedDestinations`) only the iOS runpath,
  `@executable_path/Frameworks`. The Mac app then found only the ad hoc build-folder copy,
  library validation refused it, and dyld aborted the sandboxed, hardened test host at launch
  ("Library not loaded … code signature … not valid").
- Either set `LD_RUNPATH_SEARCH_PATHS[sdk=macosx*]` on every multiplatform target that embeds a
  framework (`@executable_path/../Frameworks` for the app, a path from the extension's
  executable up to the app's `Contents/Frameworks`, and `@loader_path/../Frameworks` for the
  test bundle), or keep the package static by linking it from the app alone and letting the
  hosted tests reach it through the app. When static linking is the intent, check that the
  build's package frameworks list is empty.
- With the runpaths right, a local package's resource bundle loads in the app, the extension and
  the test bundle alike.
- An extension is a new process identity for frameworks that cache per executable. Vision
  compiled its models again for the extension, in the extension's own container: its first
  recognition took about 159 s against 8 to 11 s warm on the Mac. See
  [framework execution identity](framework-execution-identity.md).
- An extension that draws nothing still loads UIKit or AppKit and SwiftUICore.

App Groups:

- On the Mac, a host and its extension resolved the same team-prefixed group container
  (`~/Library/Group Containers/TEAMID.GROUP`) without a provisioning profile, and nothing
  prompted. On iOS both App IDs need the App Groups capability and the group; the wildcard team
  profile lacks App Groups. The Simulator's group container works without provisioning.
- A Mac target uses a team-prefixed group while iOS uses a bare `group.` identifier. Spell each
  identically across the Info.plist, the entitlements and the code, or the container is silently
  not shared.
- On macOS, `containerURL(forSecurityApplicationGroupIdentifier:)` returns a URL of the expected
  form even when the group is invalid, as its header says. Prove the container is writable
  before relying on it.

Store acceptance is separate from a development launch. Xcode writes the extension point's
identifier into the extension's Info.plist as
`EXAppExtensionAttributes.EXExtensionPointIdentifier`. In October 2025 App Store Connect
rejected an iOS build carrying it (ITMS-90349), and Apple's answers on third-party app-defined
extensions for the iOS App Store were inconsistent. Validate through an upload before depending
on one.

Evidence: [PDFReflowLib measurements/converter-extension-693/record.md](https://github.com/vocaro/PDFReflowLib/blob/dc89a4eccecb99943661709887fd2a61a1a51b29/measurements/converter-extension-693/record.md#check-6-linking).
