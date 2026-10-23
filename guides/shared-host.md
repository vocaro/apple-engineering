# Shared host

These mechanisms and lessons apply when the stated capability is present. Original
measurements establish their recorded platform and workload; they do not establish
universal behavior on later operating systems or in a different application.

## Heavy-work admission

On the shared host, builds, `swift test`, `xcodebuild test`, gate suites, corpus lanes and
conversions run through heavy-work admission: one host-wide resource namespace with bounded
concurrency. Run a configured lane with `python3 scripts/eng run LANE`; a lane whose `resource`
is `heavy` or `exclusive` is admitted, and a `light` lane runs directly. Arguments after `--`,
as in `eng run test -- --filter SUITE`, are appended to the lane's command. Run any other heavy
command with `eng admit`:

```sh
python3 scripts/eng admit -- \
  xcodebuild test -scheme SCHEME -destination "platform=iOS Simulator,id=UDID"
```

Add `--exclusive` for a whole-machine measurement or a gate suite whose budgets assume a quiet
host; `--timeout` bounds the wait for admission. The command runs in the current directory with
its output on the terminal. Like a heavy lane, `eng admit` first refreshes the operating policy,
printing it to standard error, and records the command's receipt in
`.build/engineering/admit/source.json`. It needs no `PYTHONPATH` and works from a session
worktree ([locating the toolkit](adoption.md#locating-the-toolkit-from-a-worktree)). A toolkit
clone older than `admit` reaches the same queue through the resource CLI:

```sh
PYTHONPATH="$VOCARO_ENGINEERING_ROOT/src/python" python3 -m vocaro_engineering.resources -- COMMAND
```

Public project documentation may show plain commands for outside contributors on their own
machines; the admission rule is about this host. Project adapters (a `heavy_slot.py` shim,
scripts that import `vocaro_engineering.resources`) all call
`src/python/vocaro_engineering/resources.py`; there is no second queue to keep in step. A
private slot pool, such as `mkdir` locks in a scratch directory, is a second queue that the host
queue cannot see: it ignores load and memory pressure, and nothing makes its gate exclusive.
One such pool ran ten agents' builds beside another session's full gate, and the load average
reached 764 (October 2026).

Ten agents each building on every core, with other lanes and Xcode indexing, kept watchdogd from
checking in for 93 seconds and panicked an 18-core, 36 GB Mac (2026-10-14). A fixed limit of
three then left the host idle while queued work waited behind jobs blocked on simulators.
Overlapping gate suites also fail for no reason of their own: a test that bounds a nested
session with a fixed wall-clock budget expires when a second suite takes the cores, and a red
gate that means "the host was busy" teaches people to rerun rather than read a failure. So a
second suite waits.

HEAVY_SLOTS jobs (3) are always admitted. Beyond them one job at a time is admitted, up to
HEAVY_SLOTS_MAX (half the CPU count), while the one-minute load average is below
HEAVY_LOAD_LIMIT (75% of the CPU count), macOS reports normal memory pressure
(`kern.memorystatus_vm_pressure_level` is 1), and no slot was taken in the last
HEAVY_SETTLE_SECONDS (30) for the load average to show. Setting HEAVY_SLOTS_MAX to HEAVY_SLOTS
restores a fixed limit. Admission cannot preempt: a job admitted while the host was quiet may
become heavy later. Exclusive work holds every slot up to the maximum. Each process reads these
variables from its own environment, so set them for every session or for none: an exclusive
job holds only the slots below its own maximum, and a caller with a higher one can take slots
above it.

Nested work reuses its inherited admission. Admission exports `VOCARO_RESOURCE_TOKEN` and keeps
its lock descriptors open across exec. A nested `eng run`, resource CLI call or legacy gate
validates the inherited descriptors against their lock files, the owner's nonce, its guard
entry and its process start time, then runs inside the outer admission without taking a slot.
Nesting the queue therefore never obtains a second slot, and an exclusive request inside shared
admission is refused. Work that needs the whole machine asks for exclusive admission.

The default macOS pool lives in the system's canonical user temporary directory, as reported by
`getconf DARWIN_USER_TEMP_DIR`, under the legacy `pdfreflow-heavy-slots` name, independently of
the command's TMPDIR. A private TMPDIR set before or inside the queued command joins the same
queue. HEAVY_SLOT_DIR is an explicit namespace override for isolated tests; a separate scratch
directory must not multiply the host's build budget.

A wait is expected. Admission prints `heavy: waiting (Ns): REASON` when it starts waiting and
every five minutes after, naming the reason: the guaranteed slots are busy and the load, memory
pressure or settling time refuses another; a legacy gate holds its lock; or a foreign, dead or
uncertain guard owner requires inspection. After its timeout (5,400 s by default) admission
fails without reclaiming any lock. A script that runs several jobs at once leaves at least one
of the guaranteed HEAVY_SLOTS for other sessions.

Before a full gate, look for other sessions' runs across the host, not only under the usual
worktree directory: sessions also test from checkouts elsewhere, such as a share under
`/private/tmp`. The brackets keep `grep` from matching its own command line:

```sh
ps -Ao pid,args | grep -E '[x]ctest|[x]codebuild|[c]heck-all\.sh|[t]est-ios\.sh'
```

Several projects have a `check-all.sh`; its path says whose run it is. Never stop a process
merely because it is busy.

### Load the queue cannot see

Admission reads the load before it admits and cannot account for work that never asks:

- Code-navigation (LSP) queries make `sourcekit-lsp` build the worktree at full parallelism.
  Agent sessions navigate with `grep` instead.
- Another session booting a fresh iOS Simulator ran the one-minute load average past 400 for
  two minutes on the 18-core host (October 2026).
- Xcode's indexing and an open Xcode's own builds.
- A long background measurement holds its checkout's SwiftPM build lock, so a `swift test` from
  a pre-push hook in that checkout waits silently behind it for up to the measurement's length.

## Scratch and result directories

A worktree that builds a package and its apps holds 8 to 14 GB of SwiftPM and Xcode output, and
a full data volume fails every session's shell with `ENOSPC`. Before fanning sessions out into
build worktrees, check `df -h /System/Volumes/Data` and budget about 12 GB for each; when the
budget does not allow it, work one at a time in one worktree. Put a scratch build
(`--scratch-path`) outside the repository and delete it once its result is read. Remove a
worktree once its work has landed.

A change to documents or scripts that builds nothing needs no full checkout. Add the worktree
with `git worktree add --no-checkout`, list the paths with `git sparse-checkout set --no-cone`,
then run `git checkout`. A link check needs each changed document's local link targets on disk,
and a hook that lints every document on disk needs every document and its targets. That set was
13 MB of studywright's 2.5 GB tracked tree (October 2026). Check `extensions.worktreeConfig`
first: with it on, the sparse setting stayed in the new worktree's own configuration and left
the main checkout whole.

Keep a run's results directory only while it is worth reading: a run that passed removes its
own, and a run with a failure or an unmeasured result keeps it and prints the path. Prune
earlier runs' directories by count, naming each one removed. Keeping every run's results once
filled a 1.8 TiB volume in three days. Concurrent runs share TMPDIR, so record the owning
process's PID and start time in a directory before it takes the name the pruner matches. The
pruner leaves a directory whose recorded process still has that PID and start time (a reused PID
has a different start time and protects nothing) and counts only finished runs against the
limit. A directory made by an older tool that records no owner is pruned as finished, so the
protection holds only between runs that record owners.

Key a scratch package that is kept between runs by checkout, for example
`NAME/<directory name>-<checksum of the checkout path>`. One scratch shared by every checkout
raced: two builds started together failed on a manifest holding one checkout's text and the
tail of the other's, and runs started 20 seconds apart passed while one ran a harness compiled
from the other checkout's source. Two runs from one checkout still share its scratch.

The macOS temporary-file cleaner deletes files in the user's temporary directory that have not
been read, written or changed for three days, and leaves the directories. A kept SwiftPM scratch
then holds dependency checkouts without their `Package.swift`; SwiftPM takes them as resolved
and fails with "the package manifest … cannot be accessed" (observed on macOS 27, October 2026).
When a build fails in a scratch an earlier run left, discard that scratch's build directory
once, say so, and build again from nothing. Report a failure only after the clean build.

A reboot empties `/private/tmp`. The reboot after the 2026-10-14 panic removed a coordinator's
scratch, a shared baseline, every agent's notes and the handoff records kept there; the
worktrees survived. Keep notes, counting scripts and proposed commit messages that must outlive
a reboot in the worktree's ignored `.build/`. The device record now lives outside `/private/tmp`
([device reservations](#device-reservations)).

## Reclaiming disk space

The rules above slow growth; they do not recover what crashed or finished sessions left behind.
Reclaiming that needs proof that nobody's live work is in it, and a quiet session, a passed
deadline or a finished-sounding name proves nothing. `eng disk` takes the inventory and changes
nothing:

```sh
python3 scripts/eng disk
```

It covers the whole host, whichever project runs it, and measures only the items it lists. It
prints each item's size, the reason for its status and the exact command that would remove it.
A **candidate** is proven unowned by the rules below. An **owner** item shows no sign of a
session using it, but only the owner can say whether it is still wanted: Xcode's default
simulators, a runtime no device uses, archives, test results, a directory no repository has
registered and a worktree outside the session directories. Everything else is **kept**: in use,
owned, of unclear ownership, or holding work or evidence. `--map` also reads the whole home
directory, `/private/tmp` and `/Applications` with `du`, which takes several minutes, to list
the largest other directories, never candidates, and to say how much of the used space it could
not measure.

- **In use.** One `lsof` and `ps` census of the account's processes is taken first. A path is in
  use when a process's working directory, an open file or a path in its arguments lies inside
  it, and a path in use is kept. Every candidate has also been unchanged for `--min-idle-hours`
  (24 by default): a worktree created a moment ago at origin/main is clean and landed before its
  session's first process starts.
- **Linked worktrees** of every main checkout in `~/Development`, from `git worktree list`. A
  candidate lies in its project's `.claude/worktrees` or `.codex/worktrees` or in
  `~/.codex/worktrees`, is unlocked (Claude Code locks an agent's worktree while the agent
  runs), has no process, is clean (no modified or untracked path) and has landed: its HEAD is
  contained in origin/main, or every one of its commits has an equal patch there and none is a
  merge. Ignored files under a `measurements` or `evidence` directory keep it. The inventory reads
  origin/main once per repository and does not fetch, so work that landed after the last fetch
  stays kept. Its `git status` runs with `GIT_OPTIONAL_LOCKS=0`, so it never refreshes another
  session's index. The command is `git worktree remove` without `--force`, which itself refuses
  a dirty tree and leaves the branch. A session left open in a removed worktree cannot run
  commands there again; its work is on main and its branch remains.
- **Simulators**, from `simctl list -j`. Only a disposable device can be a candidate: its unique
  name carries a UUID, as the [disposable lifecycle](simulator-testing.md#disposable-simulators)
  names it, and a pool or default device's name never does. It must also be shut down, unused
  for the idle time, absent from every process's arguments and files, and unnamed, by UDID or
  name, in every device record (the device record and any legacy `/private/tmp` handoff file).
  An unreadable record keeps every device. Xcode's default devices and unavailable named devices
  are owner items; any other named device is a pool member or one made by hand and is kept. A
  runtime no device uses is an owner item: a lane may create its devices on it next.
- **Build caches.** A DerivedData folder in `~/Library/Developer/Xcode` (named
  `NAME-<28 letters>`) is a candidate when its `info.plist` names a workspace that no longer
  exists; one without `info.plist` is an owner item, and the folders every build shares
  (`ModuleCache.noindex`, `SDKExplicitPrecompiledModules`) are kept. A SwiftPM scratch (a
  directory holding `workspace-state.json`) or an Xcode `-derivedDataPath` directory under
  `/private/tmp` or the user temporary directory is a candidate when it lies outside every
  checkout. Claude Code keeps each session's scratchpad in
  `/private/tmp/claude-UID/<checkout path, each other character a hyphen>/<session>/`; while
  that checkout exists, or a process still works inside its path (a session whose worktree was
  removed can still be running there), the session may return, so its scratch builds are kept.
  Hyphens in names make that match loose, which only keeps more. A clone or artifact in SwiftPM's
  cache, `~/Library/Caches/org.swift.swiftpm`, is a candidate too: SwiftPM fetches it again.
- **Results.** Result bundles, and run directories whose `owner` file records a finished run's
  PID and start time, are owner items; a run whose recorded process still has that start time is
  kept.

`eng disk --delete` runs only on a terminal and asks once per category. Immediately before each
removal it takes a fresh census and checks that candidate again, refuses an `rm` inside any
working tree or reached through a link, and appends every decision to
`~/Library/Application Support/vocaro-engineering/disk-reclaimed.jsonl`. It never runs an owner
item's command. Sizes are allocated sizes from `du`; APFS clones share blocks, so removing one
can free less than its size. Run the inventory again after removing worktrees: DerivedData whose
workspace went with them becomes a candidate.

On 2026-10-21 the 1.8 TiB data volume had 21 GiB free. Of about 1.74 TiB used, a measurement
archive held 314 GiB, linked worktrees 150 GiB (nearly all in use or unlanded), `/private/tmp`
116 GiB (76 GiB of it agent session scratch, mostly Xcode derived data built in scratchpads),
simulators 79 GiB (one default iPhone 23 GiB), simulator runtimes 38 GiB, and applications,
another account and a virtual machine about 300 GiB together. About 600 GiB lay in folders the
shell cannot read, which macOS privacy protection hides (`~/.Trash`, Mail, Messages, app
containers), and in system data; `--map` reports that remainder rather than guessing at
it. The inventory found 37 GiB of candidates, almost all derived data in finished sessions'
scratchpads, and 76 GiB of owner items, 48 GiB of them Xcode's default simulators.

## Device reservations

Physical devices, and simulators of the reserved pool under the simulator-pool capability, are
used only under a real reservation in the host's one device record, a human-readable JSON file
outside every repository: `~/Library/Application Support/vocaro-engineering/device-handoff.json`
of the account the sessions run as. `src/python/vocaro_engineering/devices.py` is its only
writer. It finds the record from the account's home directory, not `HOME` or `TMPDIR`, so a
session with a private environment joins the same record; `VOCARO_DEVICE_RECORD` names an
isolated record for tests only. Committed documentation keeps no device identifiers or live
session details. An entry records:

- the device and the owning session, with the revision the helper assigns;
- reserved, testing or released state, whether a run is active, and the process whose end ends
  the run;
- the purpose, the expected release time and the bounded run being attempted;
- the original accessibility settings, and the apps, outputs and owner data to preserve;
- at handoff, the terminal outcome, the restoration checks and the explicit release time.

Read and change the record through the helper's CLI, or from a script through
`devices.Record()` and its `reserve`, `update`, `release` and `recover` methods:

```sh
export PYTHONPATH="$VOCARO_ENGINEERING_ROOT/src/python"
python3 -m vocaro_engineering.devices status
python3 -m vocaro_engineering.devices show iPhone    # the entry and its revision; 0 if new
python3 -m vocaro_engineering.devices reserve iPhone --owner SESSION --revision N \
  --device UDID --purpose "…" --release-by 2026-10-21T18:00:00Z \
  --set 'originalSettings={"voiceoverEnabled": false}' --set 'preservation=…'
python3 -m vocaro_engineering.devices update iPhone --owner SESSION --revision N --set 'run=…'
python3 -m vocaro_engineering.devices release iPhone --owner SESSION --revision N \
  --outcome "…" --restoration "…"
```

The record is a coordination record, not a mutex: agree ownership with the other session first.
Each change takes an exclusive lock, reads the record fresh, refuses unless the entry is still at
the revision the caller read and, for an update or release, still the caller's, and replaces the
file whole without rewriting any other entry. A refusal changes nothing: read the entry again
and decide afresh. Each change prints the entry's new revision, which the caller's next change
names. The lock covers one change, never a reservation. One device is never held under two
keys, and the helper takes only a canonical uppercase UDID, never a name or `booted`.

Sessions used to keep ad hoc records in `/private/tmp`. In October 2026 two were live at once,
so two sessions could reserve one device in different files; unlocked read-modify-write could
lose another session's entry; and the restart after the 2026-10-14 panic emptied `/private/tmp`
while device work could still be running. The helper refuses a record there.
`devices import PATH… --by SESSION` merges such a file once, by its SHA-256, and leaves the file
untouched. Every entry survives: a held version stays current over a released one, the later
activity wins between equals, the other version is kept in the entry's `importedVersions`, and
two holds of one device leave it uncertain. `status` names a legacy file whose current bytes
were never imported; once it is imported, stop writing it.

A device is released only explicitly. A passed expected release time, an idle screen or a silent
session proves nothing: obtain the release and verify the device's state freshly. A deadline
never releases a device; `status` reports an overdue entry and changes nothing. Release yours
during offline analysis instead of holding an idle reservation. `release` refuses while a run is
active: record its confirmed terminal result first.

Preserve a live or uncertain reservation until recovery confirms its work has stopped, as a
heavy-work guard is preserved. Marking a run active records its process
(`hostProcessIdentifier`) and that process's start time. An active run whose process is gone, or
has another start time, is an orphan; an entry marked `uncertain` or `restoration-unverified` is
uncertain. Neither is reserved again until its owner releases it or
`devices recover KEY --by SESSION --revision N --verified "…"` records an attended recovery: by
the owner or a session they agreed, once the run's processes have stopped and the device's
settings and apps are verified. Recovery refuses while the recorded process still runs.

Give every command the device's explicit identifier: the canonical uppercase UDID of a device
you own or have reserved, never a name or `booted`. [Simulator testing](simulator-testing.md)
covers the pool's take, use and release steps.

Agree a window with the owner before any session on a paired iPhone or iPad. A real reservation
and handoff are still required inside that window, and approval of a run covers installing and
launching there, not operating the device by hand. [Device testing](device-testing.md) has the
window, preflight, UI-automation authorization and restoration steps for physical devices.

A launcher for one bounded session in a granted interval:

- requires the exclusive reservation to exist already, and never acquires or extends
  availability;
- runs the test under an explicit limit (the current adapter accepts 30 to 600 seconds) that
  never exceeds the reservation's remaining time less a reserve for termination and restoration
  queries;
- counts `xcodebuild` start-up in that limit: on a busy Mac it took nearly five minutes to begin
  a session whose steps then took one;
- never changes VoiceOver, uninstalls apps or deletes data;
- updates only its own entry through the device record's helper, naming the revision its
  previous change returned, so an ownership change or a concurrent change is refused;
- keeps ownership and records `restoration-unverified` when restoration fails; an unconfirmed
  termination does not release the device.

Read the launcher's terminal output and verify its receipt before reporting a release.

An interrupted test bypasses its own restoration code. After a transport failure or a forced
termination, query the settings independently before releasing; if connectivity prevents
that, record restoration as unverified and coordinate recovery. An uninstall timeout has an
unknown outcome: query the exact bundle's presence, retry removal only if it is still installed,
and verify absence separately.

To release, verify the original accessibility and keyboard settings, the absence of owned test
processes and the measured build identities. Remove only the exact owned app and runner bundles,
verify their absence, release the entry, and tell the other session that the device is released,
including any unresolved restoration state.

## Attended Mac sessions

Mac VoiceOver and foreground UI default to the [hosted runner](hosted-runner.md), not the
owner's Mac. These rules are a method for an attended session on the owner's Mac that the owner
has explicitly authorized; they grant nothing by themselves.

- Approving a mechanism is distinct from the Mac being available now. Announce each start and
  when the owner can resume work, and wait for the go-ahead.
- An explicit, uninterrupted availability interval covers bounded sessions within it without
  repeated requests. Never extend the interval yourself; keep its original deadline and
  restoration requirements.
- Guard every action by the exact app path and PID. Stop global navigation on foreground loss
  or when a helper expires.
- Restore the original settings before returning control.

[Background Mac testing](background-mac-testing.md) and [Mac VoiceOver](voiceover-mac.md)
describe the drivers, key guards and VoiceOver restoration.

## Copies that share a bundle identifier

Several sessions may run their own Debug builds of one app, all with one bundle identifier. A
tool that picks an app by bundle identifier, such as computer use or AppleScript's
`application id`, can reach another session's copy and its windows. List the running copies'
paths with `ps -Ao pid,args`, and act on or quit only your own, by path and PID. The same holds
for Xcode: with two Xcodes running, `application id "com.apple.dt.Xcode"` can reach the wrong
one, so address Xcode by its path.

## Process supervision

Keep three deadlines distinct: the tool's output wait, the connection or launch timeout, and the
test's behavior or observation deadline. A tool timeout is an observation timeout. A tool that
returns a session handle may leave the command running: resume the handle and inspect its log
and processes rather than launching a duplicate. Wait for a confirmed terminal result before
starting dependent tests or pushes. Never infer termination from a missing parent or an expired
observation wait.

Supervise the process group you own. The toolkit's `processes.supervise`, which `eng run`,
`eng admit` and the resource CLI use (`eng run` with a unique log per lane under
`.build/engineering/LANE/`), follows these rules:

- Start the command in a new session and process group. Capture the root's start identity
  (`ps -o lstart=`) before `poll()` can reap it; once reaped, its PID cannot seed adoption or
  group signals, even if another process reuses it.
- Signal the group and each observed descendant individually, comparing each descendant's start
  identity: Swift drivers can start other process groups and sessions.
- A refused signal never ends supervision. Darwin answers `killpg` with EPERM when the group's
  only member is the exited root that has not been reaped yet, and an unsignalable descendant is
  still awaited.
- A command waits for its observed descendants before its status counts. The periodic census
  cannot prove that a fast child did not orphan itself between samples, so a timed-out,
  interrupted or otherwise uncertain run raises and admission keeps its guard for inspection; a
  confirmed terminal exit keeps its status and releases normally. A push keeper is stricter: any
  failure leaves its guards in place even after the observed children drain.
- Once the root exits, its observed descendants have 60 s to end. The supervisor lists any still
  running on stderr, as `ps -o pid,ppid,pgid,lstart,args` rows with the parent and group each
  had when first seen, and stops them: SIGTERM, then SIGKILL 10 s later. The root's status counts
  once they are gone; a process that survives SIGKILL is still awaited. A lane's `timeout` bounds
  only the root, so a root that exits in time keeps its status through the grace. Agents
  reported Xcode's `DTServiceHub` outliving an ad hoc `xcodebuild … test` on a fresh iOS
  simulator by 10 to 15 minutes, ignoring SIGTERM, until they killed it by hand (EPUBLib, macOS
  27.0, Xcode 27.1, October 2026).
- A command that cannot start, such as a mistyped name or a script without its executable bit,
  raises `NotStarted` and releases admission. `Popen` reaps the child whose exec failed before
  it raises, so nothing is left to inspect; keeping the guard would stop every session's
  admission over a typo.

Terminate only an observed launch PID whose current executable still matches; an unknown or
reused PID never authorizes termination, and a cleanup error keeps the first failure.

A lock keeper started independently of the invoking client survives the client's loss and holds
its locks until its command group drains. Cancellation sends SIGTERM without automatic
escalation, so a nonresponsive child can leave a live keeper holding the locks until attended
recovery. Never remove a live keeper's locks.

An `xcodebuild` UI-test root and the shared supervisor finish at different times. Follow the
root to a terminal test result and copy the evidence. Then shut down only the owned simulator,
which ends the remaining simulator descendants sooner than the supervisor's grace, and follow
the supervised command until it exits and admission is released. Root exit, an observation
timeout, a passed deadline or the shutdown alone does not release a reservation; when the
supervisor's outcome is uncertain, keep the reservation for recovery and launch no replacement
run against it.

Tests of supervision code bound stalls rather than durations and start a timeout under test
only once the real descendant has published its identity ([app testing](app-testing.md)).

## Long-running measurements

Background a long run with its output redirected to a log.

- Agent shells can start with an empty PATH. Export it first, including Homebrew's `bin` where
  tools such as `uv` live, and invoke binaries by absolute path. Redirect to a file rather than
  piping through `tail` or `grep`: a missing pipe binary kills the whole pipeline.
- An empty log is buffering until shown otherwise: redirected output is block-buffered (about 4
  to 8 KB). Check the processes, twice, since a run alternates working and reporting.
- In zsh, the shell agents' commands run in, `status` is a read-only parameter. `status=$?`
  after a run fails, stops the wrapper and loses the run's exit code: a 48-minute gate's result
  had to be read back from its log (October 2026). Capture it as `rc=$?`.
- Apple's `git grep -E` has no `\b`: a pattern using it matches nothing and exits 1, exactly as
  a search that found nothing does. A sweep for British spellings read that silence as a clean
  tree (October 2026). Use `git grep -w`, or `grep -E`, which honors `\b`.
- Wait for a run by its own completion signal, a line its wrapper appends or a file it
  publishes, never by `pgrep -f PATTERN` from a shell, whose own command line matches the
  pattern.
- On-device FoundationModels generation burns CPU in `TGOnDeviceInferenceProviderService` and
  `modelmanagerd` while the test runner sits near idle. Private Cloud Compute generation shows
  about 0% local CPU for the runner and the local model server alike, so check their connection
  instead (`lsof -nP -iTCP:PORT` shows an `ESTABLISHED` pair) and the server's health response
  (macOS 27, October 2026).
- The first Vision text recognition in a process cost about 55 seconds of model preparation and
  about 0.35 seconds a page after it (macOS 27, October 2026). Time warm-up apart from
  throughput.
- Run one generative-model workload per machine. Two processes driving one Mac's on-device model
  both sat at about 0% CPU with no output for many minutes, and concurrent Core ML and
  FoundationModels work made an embedder return silently wrong vectors
  ([embedding correctness](../knowledge/ml/embedding-correctness.md)). Before starting, look for
  other `swiftpm-testing-helper` and `xctest` processes, including another worktree's suite, and
  take a process listing during any wall-clock measurement. Use exclusive admission.

[Measurement](measurement.md) covers what to record.

## Long pre-push checks

Git's SSH transport holds the connection that read the remote refs open for the whole pre-push
hook. During long gates GitHub closed that connection despite an SSH `ServerAliveInterval`
keepalive, and the push ended on SIGPIPE after every gate had passed (October 2026). Push over
HTTPS instead: it reads the refs before the hook and sends the pack in a separate request after
it, so no connection has to outlast the gates.

A per-command global configuration publishes over HTTPS without changing the repository's or the
user's configuration. Pass it through the environment so the hook and every nested gate see it:

```sh
cat > "$SCRATCH/push.gitconfig" <<'EOF'
[include]
	path = ~/.gitconfig
[url "https://github.com/"]
	insteadOf = git@github.com:
[credential "https://github.com"]
	helper = !gh auth git-credential
EOF
GIT_CONFIG_GLOBAL="$SCRATCH/push.gitconfig" git push origin SHA:refs/heads/main
```

HTTPS has failure modes of its own:

- A pack larger than `http.postBuffer` (1 MiB by default) is streamed with chunked encoding, and
  GitHub answered a 116 MB chunked pack with HTTP 408 after both lanes had passed. The same push
  with `http.postBuffer` at 1 GiB and `http.version` at `HTTP/1.1` published a 208 MB pack.
  Measure the pack first and set the buffer above it:
  `git rev-list --objects origin/main..SHA | git pack-objects --stdout | wc -c`.
- Because the refs are read before the hook, another push to `main` while the gates run makes
  GitHub refuse the update afterwards
  (`cannot lock ref 'refs/heads/main': is at NEW but expected OLD`). Fetch; if the gated commit
  still descends from the new `origin/main` (`git merge-base --is-ancestor origin/main SHA`),
  push it again, and otherwise integrate and run the gates on the new tree. Push the gated
  commit by name (`SHA:refs/heads/main`) rather than `main`, so a retry never publishes a local
  `main` another session advanced after the gates ran. In zsh, brace a variable in that refspec
  (`"${sha}:refs/heads/main"`): an unbraced `$sha:refs/…` reads `:r` as a history modifier and
  mangles the refspec.

Follow the owned hook to its terminal result before starting more work. Record the exact commit,
the clean tree and each complete gate result. A transport failure does not establish a test
failure, and interrupted or missing checks never count as passed. A retry follows the
repository's hook policy and publishes only the verified commit. Whether a documentation-only
commit may skip the hook is that repository's policy, not a shared default.

## Checkout provisioning and publication

A fresh checkout or worktree has none of the ignored inputs its gates need. Provision them
idempotently: fill gaps only, verify each input against a committed identity, and report a
present input whose bytes drifted rather than overwriting it. A `--check` mode reports without
changing anything.

A Claude Code session started in a worktree reads the project configuration from the checkout
the worktree was made from, so a `SessionStart` hook's `$CLAUDE_PROJECT_DIR` and working
directory are that checkout; the session's own directory arrives only as the `cwd` field of the
hook's input (observed October 2026). Read that field and hand over to the worktree's copy of
the provisioning script.

Reuse a large input from another registered worktree of the same repository before fetching it:

1. Open the donor's regular file without following a symbolic link.
2. Verify its committed byte count and SHA-256.
3. Make an APFS clone in private staging on the destination volume.
4. Verify the staged clone the same way, then publish it create-only.

Donor and destination keep independent file identities. A missing, drifted or unusable donor, a
different volume or unsupported cloning falls back to the fetch path; report verified donor
reuse separately from fetch completion.

Link a shared ignored directory with `ln -sn TARGET LINK`. In a reused worktree that already
holds the link, a bare `ln -s` follows it and writes a link inside the target pointing at
itself; `-n` refuses with "File exists".

Keep writable build products and Python environments private to one checkout, at a stable path,
so warm builds stay warm. An APFS-cloned `.build` at a different source path recompiled with
stale-path warnings (6.6 s against 0.7 s for a same-path warm build), and adding compiler CAS
flags directly to a normal SwiftPM gate command failed planning (both on Xcode 27.1, Swift 6.4,
October 2026).

A pre-push hook runs its gates over the working tree, not over the commits being pushed, so a
tested publication comes from a clean checkout of the exact commit. Never push a shared tree
that holds another session's edits. A persistent push checkout makes this cheap:

- a separate, canonical linked worktree at a stable path, detached, with its own ignored inputs
  and build products (`git worktree add --detach PATH origin/main` creates it);
- advancement only to a descendant of its HEAD, by detached checkout; it refuses dirty tracked
  bytes or modes, a differing index, nonignored untracked files, symbolic paths and backward or
  divergent moves, and never resets or cleans;
- a keeper that holds the checkout and host gate locks from before it moves the tree until the
  remote acknowledges the push, and refuses an inherited variable that redirects the host lock;
- nested lanes that take their own temporary locks while the host lock stays held, so test
  fixtures keep real locks rather than an inherited opt-out;
- Git variables that a hook exports for its repository (`GIT_DIR`, `GIT_INDEX_FILE` and the
  others) cleared before any command touches a nested repository;
- HEAD, the index tree, every tracked byte and mode and the nonignored untracked files checked
  against the frozen commit before and after each lane;
- success reported only with a commit and tree receipt; a no-op push without a hook receipt is
  not a qualified publication.

## Toolchain selection

Use a full Xcode, not the Command Line Tools. The Command Line Tools ship the same Swift, so a
version check passes, but they lack `coremlcompiler` and cannot build test targets;
`xcode-select -p` shows which is selected. Name the stable path, `/Applications/Xcode.app`,
rather than an installed version, and prefix direct `swift`, `xcrun` and `xcodebuild` commands
with it:

```sh
DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer xcrun xcodebuild -version
```

Name a beta or second Xcode by its own path in the same way for every command that needs it, and
record `xcodebuild -version` and `sw_vers` with each result. Installing or first launching
another Xcode can restart the simulator service under every session;
[simulator testing](simulator-testing.md) covers what that does to running simulators.

## Inspecting system code without starting it

Use `dyld_info -disassemble` on a framework's path under `/System/Library`, which prints its
code under its method names even for a framework that exists only in the dyld shared cache, or
`lldb -b -o "target create BINARY" -o "disassemble -n METHOD"` without a run command for a
binary on disk. `target create` refuses a framework that is only in the shared cache as one that
"does not exist". Neither names the selector a stub call goes to or the characters of a string
address; a reader that maps the shared cache as its own process does can annotate both. A
framework's localized `.loctable` property lists map a word heard or shown to its key, which
leads to the code that uses it ([Mac VoiceOver](voiceover-mac.md) applies this to VoiceOver). To
see calls made into code you own, log from that code.

Never start or attach a debugger to answer a framework question on the shared workstation.
Developer Mode is off there (`DevToolsSecurity -status`), so a debugger launch raises an
administrator-password dialog that takes the keyboard from the owner and every session. If one
appears, stop your processes, leave the dialog for the owner and say so. Sampling your own child
(`sample "$(pgrep -P $!)"`) needs no password; never sample another session's process.

## Lock reclamation

Three kinds of marker coexist, and they are reclaimed differently:

- The legacy shlock gate file (`/tmp/studywright-gate-suite.lock` by default) holds a PID, and
  `shlock` reclaims it once that process is gone, so a killed gate does not strand the next one.
- A guard (`<gate lock>.warm-push-guard`, which admission and the push keeper publish) records
  each owner's PID, process start, label and an uncertainty flag. It is never reclaimed by PID
  or by time, because a dead keeper's compilers or simulator children can outlive it. Gates
  check the guard before trying `shlock`, and admission refuses to proceed while any guard owner
  is dead, foreign or uncertain.
- The device record's lock (`device-handoff.json.lock` beside the record) is an `flock` held for
  one change. The kernel releases it when its process ends, so it needs no reclamation, and its
  file is never removed. A reservation in the record ends only by its owner's release or an
  attended recovery ([device reservations](#device-reservations)).

A job leaving admission changes only its own guard entry, whatever state the other owners are
in: a clean exit removes the entry, and the guard with its last one, and an exception marks it
uncertain. It never changes or drops another owner's entry. Until 2026-10-22 a job that left
while another owner was dead changed nothing, so its own entry died with its process: one lane
killed by its agent stranded a run that finished normally beside it, and the host admitted no
heavy work for 80 minutes, until the guard was recovered by hand.

A signal that ends the admitting process before it leaves its context leaves its entry dead.
`eng admit` and `eng run` install no signal handlers, so SIGTERM and SIGHUP end them as SIGKILL
does, while the command, in its own session, keeps running unsupervised. SIGINT raises inside
supervision, which stops the command's process group and marks the entry uncertain. An agent's
task stop is such a signal: Claude Code's TaskStop sends SIGTERM to every process descended from
the task's shell, the command in its own session included, and SIGKILL 1.5 s later (observed
2026-10-22, macOS 27.0, Python 3.14). To end an admitted command early, stop the command's own
processes, which supervision then follows to a terminal result, never the task or the admitting
process.

Recovery of a guard is attended. Inspect its recorded owner, that owner's command processes and
any reserved tree; stop or wait for all of the transaction's children; then remove the abandoned
markers by hand. A free owned descriptor or a later foreign acquisition, checked against the
recorded process birth and descriptor nonce, establishes that an old lock was released. Preserve
every foreign reservation. Time passing alone establishes none of this.

A push keeper's guard is `{"keeper": PID, "checkoutLock": PATH}`. Admission reads it as foreign
and waits, so while it stands no session on the host is admitted to heavy work. `PATH/owner.json`
lists each command the keeper ran, with its PID, process group, start time and observed
descendants, plus `childrenUncertain`. Check each recorded process by PID and start time. This
was observed when a studywright warm push's keeper died with uncertain children (2026-10-21).

## Ending a coordinated command

Use the supplied `eng run` or resource CLI for commands. They return the child's status after
leaving admission normally. If using Admission directly, leave the context before raising
SystemExit for a nonzero result. An exception inside the context retains its uncertain guard,
by design, because the coordinator cannot infer whether that exception left children running.

Legacy shell gates authenticate inherited exclusive admission for their exact lock namespace.
The coordinator does not export a lock opt-out into the suite: regression fixtures retain
independent real locks. A process wrapper must forward the admission descriptors, as the
shared process supervisor does; copying the token environment alone does not transfer ownership.
