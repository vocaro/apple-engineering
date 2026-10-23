# Common engineering rules

These defaults apply across Vocaro projects. A project's engineering.json identifies the
capabilities it uses and documents justified exceptions. Product policies remain local.

## Concurrent work

- Preserve other sessions' files, commits, processes, devices and settings. Read co-edited
  files immediately before changing them. Stage explicit paths, never `git add .`, `-A` or
  `commit -a`. Do not reset a shared checkout to remove somebody else's work.
- Work on an isolated branch or worktree when concurrent changes require it. Inspect the
  project's integration policy: private projects currently integrate directly to main.
- When one command acts on several branches, name the exact refs from your own task records.
  A prefix match can include another session's branch; never use it as an ownership test.
- A landed leftover needs no owner. Any session may delete a local branch that no worktree has
  checked out, once a landing check proves its work is in origin/main (by ancestry, equal
  patches, or a merged pull request that holds its tip) and it has been untouched for an hour.
  An agent's worktree may go the same way when it is also unlocked, clean and unused, with
  nothing ignored but build caches. That is proof, not judgment. Leave session worktrees to the
  app, which reuses them.
- Read a comparison's merge-base once and use that commit, not a moving origin/main ref.
  Fetch before final verification. Check whether a referenced PR already merged before
  building on it, and record the commit each verification actually exercised.
- An issue is closed by what main's tree holds: put `Closes #N` only on a commit that lands on
  main with its content. To take your own change out of a tree, reverse your own commit's patch.
- Remove only task-owned scratch builds after recording results. A building worktree can hold
  8-14 GB: check `df -h /System/Volumes/Data` before creating build worktrees, because a full
  volume fails every session. Evidence belongs with its issue or subject, not only on a branch.
- When the volume runs short, run `python3 scripts/eng disk` and tell the owner what it found.
  It proves what nobody owns; never remove what another session left on your own judgment, and
  leave `--delete`, which asks on a terminal, to the owner.

## Tests and evidence

- Automate tests. Do not ask the owner to tap, swipe, type, or repeat an observation that the
  automated acceptance lane already establishes. Report coverage automation cannot reach.
- Before proposing a physical device, say what it would show that a simulator cannot; a check
  said to need a finger usually needs a timing or input a UI test can make. Behavior a simulator
  or the Mac does not enforce, such as data protection or extension memory limits, is qualified
  only on the device.
- Use the smallest relevant checks first. Verify a filtered run's executed count and expected
  identities: a successful command with zero selected tests establishes no coverage.
- Keep passed, failed, skipped and unmeasured distinct. An unmeasured result records its cause
  (an unavailable framework, model or device, host pressure, an observation timeout) and is never
  green. Require an independent positive control before blaming an unavailable framework or
  model. Optional tests visibly skip.
- Prove a new regression test fails on the old behavior. Deferring work lowers its priority; it
  never removes tests, cases, contracts or gates.
- Preserve raw observations with actual source/input/toolchain/runtime identities. Never
  rewrite a historical observation to match current behavior. A later hash does not establish
  what an earlier run used. Qualification claims name their measured platform and limits.
- Compare the same execution identity and environment when measuring framework behavior.
  Repeat under controlled load when the machine was busy; do not weaken assertions to hide it.
- Expectations come from standards, independent implementations, or explicit product decisions,
  not merely from the current implementation. Preserve meaningful regression controls.

## Shared resources

- Before using shared devices, foreground input, or hosted runners, refresh current operating
  policy and read the project's current main rules. An old branch or another session's brief
  does not override the owner's current restrictions or authorize an attended session.
- Coordinate heavy builds and measurements through the shared resource queue: a configured
  lane with `python3 scripts/eng run LANE`, adding `-- ARGUMENTS` such as a test filter, and any
  other build, `swift test`, `xcodebuild` or simulator run with
  `python3 scripts/eng admit -- COMMAND`. Add `--exclusive` for a gate suite or a whole-machine
  measurement, which conflicts with heavy work. Never build a private slot pool: the queue
  cannot see it. Nested work reuses its inherited admission.
- Before a full gate, inspect active test and gate processes across the host, including
  checkouts outside the usual worktree directories. A checkout path alone is not a complete
  inventory of other sessions' running work; never stop a process merely because it is busy.
- Give simulator and device commands an explicit identifier. Never select `booted`, erase,
  shut down, or clean up a device another session owns. The configured simulator capability
  determines whether disposable devices or an approved reserved pool are used. Do not open a
  live simulator view unless the owner asked to watch.
- Agree a window with the owner before any session on the paired iPhone or iPad (the iPhone is
  the owner's personal phone), then reserve it. Approval of a run covers installing and
  launching, not operating the device.
- A tool timeout is an observation timeout. Follow the owned process to a terminal result
  before retrying. Preserve an uncertain orphan's reservation for recovery.
- Do not run Mac VoiceOver or foreground UI automation on the owner's Mac without the required
  explicit authorization. Run Mac speech on the allowed disposable hosted runner. Never run
  runner preparation commands on this workstation. A locked screen or sleeping display leaves
  background Mac UI tests unmeasured; rerun them later, and never keep the Mac awake unasked.
- Do not launch or attach a debugger, dtrace, or a sampler to another session's process. Use
  static disassembly for system-code questions and logging from code you own. If a password
  dialog appears, end your processes, leave the dialog alone, and tell the owner.
- Normal tests run locally. Do not add hosted workflows, triggers, or jobs merely to move
  tests off this machine. Honor each repository's permitted workflow and spending policy.

## Maintained knowledge

- Keep behavior and limits in a subject document; procedures in its runbook; actual issue or
  release verification at its owning issue or release. Link evidence rather than copying it.
- Match evidence to its destination's audience. Keep private payloads, device identities and
  raw private transcripts in a private owning project or evidence archive. Public summaries
  contain reviewed results and reproducible methods; they do not require private access.
- Capture reusable findings in this repository's subject articles, with source revision,
  applicability, counterexamples and limits. Link private implementations without copying app
  policy into a universal default. Keep evidence identities and original outcomes intact.
- General engineering content is written out here, not linked from a project. When projects, or
  a project and this repository, disagree on a point that is not product-specific, tell the
  owner, choose the better rule (ask when unsure; this repository's current text may lose),
  state it here as the rule and change the projects to follow it. Keep no record of which
  project held which rule.
- Keep agent entry points short. Read shared guidance through scripts/eng, then local rules.
  Shared guidance is not automatically loaded merely because a file links to it.
- Preserve corpus provenance, licenses, input identities and download restrictions. Permission
  to use a collection in one project does not admit it to another project automatically. Fetch
  corpus sources only through the repository's pinned path; never bypass a bot challenge, and
  where a site disallows automated agents, the owner fetches.
- Avoid unrelated formatting churn, formatter changes, new dependencies or universal schemas
  when extracting a small mechanism. Keep one canonical provider per runtime module.

## Writing

- Spell in American English everywhere: code, identifiers and public APIs, strings and UI text,
  file names, documents, comments, commit messages, issues and pull requests (color, license,
  behavior, center, gray, canceled, labeled, recognize). Sessions copy the spelling they read, so
  a British form left in place spreads; an existing British name is no precedent. Keep only what
  others named or wrote: another project's API (`isCancelled`, `MonoBehaviour`), a standard's
  terms (PNG's "colour type"), proper names, URLs, quotations and cited titles, retained upstream
  text and recorded observations. Keep reading data stored under an old name until it migrates.
  `python3 scripts/eng spelling` finds British forms; list a kept name, with its reason, in
  engineering.json's `spelling`.
