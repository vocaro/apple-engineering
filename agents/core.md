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
- Read a comparison's merge-base once and use that commit, not a moving origin/main ref.
  Fetch before final verification. Check whether a referenced PR already merged before
  building on it, and record the commit each verification actually exercised.
- Remove only task-owned scratch builds after recording results. Check available disk before
  creating build worktrees. Evidence belongs with its issue or subject, not only on a branch.

## Tests and evidence

- Automate tests. Do not ask the owner to tap, swipe, type, or repeat an observation that the
  automated acceptance lane already establishes. Report coverage automation cannot reach.
- Use the smallest relevant checks first. Verify a filtered run's executed count and expected
  identities: a successful command with zero selected tests establishes no coverage.
- Keep passed, failed, skipped, and unavailable distinct. Require an independent positive
  control before blaming an unavailable framework or model. Optional tests visibly skip.
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
- Coordinate heavy builds and measurements through the shared resource queue. An exclusive
  measurement conflicts with heavy work; nested work reuses its inherited admission.
- Give simulator and device commands an explicit identifier. Never select `booted`, erase,
  shut down, or clean up a device another session owns. The configured simulator capability
  determines whether disposable devices or an approved reserved pool are used.
- A tool timeout is an observation timeout. Follow the owned process to a terminal result
  before retrying. Preserve an uncertain orphan's reservation for recovery.
- Do not run Mac VoiceOver or foreground UI automation on the owner's Mac without the required
  explicit authorization. Run Mac speech on the allowed disposable hosted runner. Never run
  runner preparation commands on this workstation.
- Do not launch or attach a debugger, dtrace, or a sampler to another session's process. Use
  static disassembly for system-code questions and logging from code you own. If a password
  dialog appears, end your processes, leave the dialog alone, and tell the owner.
- Normal tests run locally. Do not add hosted workflows, triggers, or jobs merely to move
  tests off this machine. Honor each repository's permitted workflow and spending policy.

## Maintained knowledge

- Keep behavior and limits in a subject document; procedures in its runbook; actual issue or
  release verification at its owning issue or release. Link evidence rather than copying it.
- Capture reusable findings in this repository's subject articles, with source revision,
  applicability, counterexamples and limits. Link private implementations without copying app
  policy into a universal default. Keep evidence identities and original outcomes intact.
- Keep agent entry points short. Read shared guidance through scripts/eng, then local rules.
  Shared guidance is not automatically loaded merely because a file links to it.
- Preserve corpus provenance, licences, input identities and download restrictions. Permission
  to use a collection in one project does not admit it to another project automatically.
- Avoid unrelated formatting churn, formatter changes, new dependencies or universal schemas
  when extracting a small mechanism. Keep one canonical provider per runtime module.
