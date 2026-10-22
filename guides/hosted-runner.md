# Hosted Mac runner

These mechanisms and lessons apply when the stated capability is present. Original
measurements establish their recorded platform and workload; they do not establish
universal behavior on later operating systems or in a different application.

GitHub's hosted macOS runner records Mac VoiceOver speech without taking over a workstation.
The current rules for using it on the shared account are in the
[shared-host policy](../policies/shared-host.md); this guide describes the mechanism. How a
session itself is driven and read is in [Mac VoiceOver](voiceover-mac.md).

## Purpose and limits

- One run builds the app under test at a ref, runs every speech session in one job and uploads
  the transcripts. The workflow starts only by manual dispatch.
- Hosted macOS jobs are for approved Mac VoiceOver sessions. Do not add hosted workflows,
  triggers or jobs to move ordinary tests off the workstation.
- A hosted session counts as Mac acceptance evidence on the same terms as a workstation session
  ([acceptance rule](voiceover.md#acceptance-rule)). It cannot serve a check that needs someone
  listening or a decision between two steps.
- The standard runner costs nothing in a public repository; see [billing](#billing-check).

## Preparing a disposable runner

The workflow prepares the runner before it builds. Each step is there for a failure seen
without it, on `xcode-27` public-preview images with macOS 27.0.1, October 2026. These commands
change settings of the logged-in user and belong on a disposable runner. Never run them on a
workstation. Make the workflow's first step refuse a machine whose `RUNNER_ENVIRONMENT` is not
`github-hosted`.

1. `defaults write com.apple.VoiceOverTraining doNotShowSplashScreen -bool true`: a Mac that
   has never run VoiceOver opens its welcome dialog first.
2. `defaults write com.apple.HIToolbox AppleDictationAutoEnable -int 0`: every VoiceOver
   command presses Control, and after about four of them "Do you want to enable Dictation?"
   took the VoiceOver cursor.
3. `launchctl bootout gui/$(id -u)/com.apple.dt.AutomationModeUI`: XCTest's "Automation
   Running" banner is a system launch agent with `KeepAlive` for as long as
   `/var/db/com.apple.dt.automationmode/automation-enabled` exists, and with
   `EnablePressuredExit`. On the image it was killed and restarted about every ten seconds
   during a UI test, and VoiceOver moved to an instance that survived and stayed there, which
   lost three sessions of seven. `launchctl disable` does not stop the banner. Bootout works
   only because the hosted runner has System Integrity Protection disabled; with SIP engaged it
   fails ("Boot-out failed: 150: Operation not permitted while System Integrity Protection is
   engaged") and changes nothing. Fail the job if the agent is still loaded, record the SIP
   status, and still stop any session in which VoiceOver names the banner.
4. `displayplacer` sets the screen to 1920 × 1080. The image's 1024 × 768 screen held the window
   to 1024 × 674, and an accessibility resize to 1100 points reported success without resizing.
   Fail the job if the screen is not that size afterwards.
5. Build with `CODE_SIGN_IDENTITY=- DEVELOPMENT_TEAM=`: an ad hoc signature needs no team,
   certificate or secret, and the image's own privacy grants were enough for the UI test.
6. Read a missing `voiceOverOnOffKey` as off when no `VoiceOver` process exists, the state of a
   Mac that has never run VoiceOver.
7. Read, and if an input asks, choose VoiceOver's link verbosity with
   `voiceover-link-verbosity.swift` ([link verbosity](voiceover-mac.md#link-verbosity)), never
   with `defaults`.

## Dispatching a run

The dispatcher is `src/python/vocaro_engineering/voiceover/hosted_run.py`, loaded by a project
adapter at `scripts/hosted-run.py` with the project's engineering.json. Start runs with it, not
with `gh workflow run`, and fetch transcripts with `gh run download`:

```sh
python3 scripts/hosted-run.py
python3 scripts/hosted-run.py WORKFLOW.yml -f steps='STEP STEP ; STEP STEP'
gh run watch RUN_ID --exit-status
gh run download RUN_ID --name ARTIFACT --dir DIR
```

- With no workflow it prints how many enrolled runs are on a runner and how many are waiting,
  then each run in flight, and starts nothing.
- A workflow must be in engineering.json's `voiceover.workflows` allowlist. The dispatcher
  starts the run from the branch checked out, or from `--ref`, with that branch's workflow file,
  and takes `gh workflow run`'s `-f KEY=VALUE` inputs.
- It starts nothing, says why and exits 1 when the branch already has its share of runs
  ([caps](#caps-and-canceling)), or, for a run from the branch checked out, when the steps fail
  the project's `scripts/run-voiceover-sessions.py --check` with each input passed as a
  `VOICEOVER_`-prefixed variable. The runner makes the same check only after waiting for a
  runner, so the local check saves the wait.
- It warns when GitHub's copy of the branch is not the commit checked out, because a run uses
  what is pushed, and refuses a ref GitHub does not have.
- It prints the new run's number with the commands to follow and to cancel it.
- `--force` starts a run that would be refused. A slow queue is not a reason for it.

engineering.json names the project's own `repository` (OWNER/REPO), the public
`hostedRepositories` that share the account, and the `voiceover.workflows` allowlist.

## Sharing the runner

- GitHub runs five macOS jobs at a time for a whole account on its Free, Pro and Team plans
  ([GitHub's limits](https://docs.github.com/en/actions/reference/limits)). Every agent
  session's runs draw on those five, and a run beyond them waits. The queue has no priorities:
  runs get a runner in the order they started, whatever they are for, so a run started to try
  something stands ahead of every run started after it.
- On the shared account in October 2026, a job started within 10 s while fewer than five ran.
  On an evening when unit tests also ran there, all five were busy for hours and a job waited a
  median of 13 minutes, 75 at worst; one branch had started four to nine runs within 90 s on
  sixteen occasions, each with a runner and a build of its own.
- Queue inspection spans every enrolled repository. The dispatcher asks GitHub for each
  repository's runs that are in progress, queued, pending, requested or waiting, all at once,
  and lists them oldest first. Enrolled repositories are those in `hostedRepositories` plus each
  `vocaroEngineering.hostedRepository` value in the checkout's local Git configuration, which is
  where private repositories on the account are enrolled ([public access](public-access.md)).
  A configured repository whose queue cannot be read is an error, never silently skipped.
  Enrollment grants no access or spending permission.
- Only the current repository's runs on the dispatched branch count against that branch's cap.
  A run waiting for a runner in any enrolled repository lowers the cap to one.

## Batching sessions

- Put every session a piece of work needs into one run. Each session can have its own settings
  ([session grammar](voiceover-mac.md#session-grammar-and-per-session-settings)), so step lists
  that differ in them share one run, one build and one runner.
- To hear several ways of doing one thing, put them in one commit behind a launch argument the
  app reads from `UserDefaults`, give each session its own, and take the commit out again when
  one way is kept. Nine variants were heard in two runs that way, where separate builds would
  have taken nine.
- In the qualified workflow (October 2026) a job had 20 minutes and a session at most 300 s.
  Preparing the runner and building took about 2 minutes and a short page-boundary session
  about 3 at the fixed pause, so a one-session run uploaded its transcript about 5 minutes
  after it got a runner. A session that could not end 3 minutes before the job's limit was
  reported as not run and failed the job, which left about 15 minutes for sessions. At the
  fixed pause a session took about 35 s plus 5 s per key; seven sessions of ninety keys between
  them filled a job. Four sessions with different settings took 239 s of a 5 min 50 s job, 82 s
  of it the build; as four runs they would have built four times on four runners.
- Advancing on a key's first phrase took about a quarter of the time across paired sessions,
  and 95 of 97 keys recorded the same first phrase as at the fixed pause. It cuts the hint that
  follows a move short. Use it to explore and to walk across controls, never for evidence.

## Caps and canceling

- Keep at most two runs in flight for a branch, and one while any run is waiting for a runner.
  A run counts as waiting for its first seconds, before GitHub gives it a runner, so a second
  run started straight after a first is refused: start it once the dispatcher lists the first
  as on a runner.
- Cancel a run as soon as it is no longer needed, with `gh run cancel RUN_ID`. Nothing else
  cancels one: a second run from a branch does not replace the first, whatever their inputs.
  Cancel only your own runs.

## Outcomes and downloads

- Fail the job unless every session exits 0. Record each session's settings, outcome,
  transcript and command in a sessions file, the job log and the run's summary page; the run's
  name can carry only run-level inputs. Give a reached deadline, a stop by the driver, refused
  steps and VoiceOver not restored their own outcomes.
- A session whose VoiceOver was not restored still has its transcript. The sessions after it in
  the job begin with VoiceOver in the wrong state.
- Download a transcript per session; a runner file with the commit, the runner image and its
  version, macOS, Xcode, SIP status, the screen, VoiceOver's link verbosity and Safari's
  version; the observer, xcodebuild and build logs; and a screenshot of the screen at the end.
  The job's "Set up job" log also prints the image, such as `xcode-27-arm64` 20261006.0244.1.
- Collect macOS's crash report (`.ips`) for VoiceOver, the app or Safari when one quit. A
  transcript in which VoiceOver's opening phrase follows an `ERROR` in the middle of a session
  is one in which VoiceOver started again.
- A failed job also uploads the result bundles (about 100 MB for four short sessions) and a
  system-log extract of the banner's starts and of Dictation. A stopped session's result bundle
  has no `Info.plist`, so `xcresulttool` cannot open it, but its log archive opens with
  `log show --archive`.
- Artifacts expire (after five days in the qualified workflow). Copy what must be kept to the
  issue or its evidence record.

## Differences from a workstation

- After preparation the screen is 1920 × 1080, and the app's window was 850 points high where
  workstation sessions had 882, so a full column held one line fewer. Take every boundary from
  the session's own observer state.
- macOS and Xcode are the image's: on 2026-10-12, macOS 27.0.1 (26A434) where workstation
  sessions used 27.0 (26A428).
- Nobody listens and nothing is stepped by hand: a step list goes in and a transcript comes out.
- The build is signed ad hoc, without a team.
- The three-processor runner was slow to start the app: 7 of 26 sessions opened with VoiceOver
  saying the app was "not responding", and every later phrase was the app's.
- A public-preview image's privacy grants, its automation mode without authentication and the
  banner's behavior belong to the image version and can change. Record the version.

## Billing check

Keep the workflow on the standard runner label. A larger runner, such as an `-xlarge` label, is
billed even in a public repository. To see what a run cost, expect `"billable": {}` from:

```sh
gh api repos/OWNER/REPO/actions/runs/RUN_ID/timing
```
