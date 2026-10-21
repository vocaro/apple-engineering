# Background processing

These mechanisms and lessons apply when the stated capability is present. Original
measurements establish their recorded platform and workload; they do not establish
universal behavior on later operating systems or in a different application.

## Submission, acceptance and a grant are separate states

`BGContinuedProcessingTask` (iOS and iPadOS 26 and later) keeps work a person started running
after they leave the app. An attempt is registered, submitted, granted, then expired or ended;
or it is refused or withdrawn before any grant. Give each attempt its own identity, journal each
transition without content, and keep these states distinct.

- Submit only in the foreground, as the direct result of the person's action. Apple documents
  that the request is created on behalf of the currently foregrounded app. At scene phase
  `.background` the app is no longer that app, and `.inactive` also happens without leaving
  (Control Center, the app switcher, a call), so a request made as the person leaves has no
  documented basis. Whether iOS enforces this at submission was not tested.
- Permit an identifier family in `BGTaskSchedulerPermittedIdentifiers` and register each
  attempt's concrete identifier (the prefix, a dot and a UUID) immediately before submitting it.
  Continued-processing registration is exempt from the usual before-launch rule. On iOS and
  iPadOS 27 devices in September 2026, registering a handler for the wildcard itself was
  rejected although the Info.plist advertised the family.
- Never register one identifier twice: Apple documents that the system can end the app. Keep a
  reuse guard for the life of the process, covering attempts that have already ended.
- Submit off the main actor. On iOS 27 `submitTaskRequest` can take any time, warns against the
  main thread, and was once observed never to return, hanging every later attempt that waited on
  it. The system can also launch the task before the submission returns.
- Choose the strategy deliberately. With `.fail`, iOS starts the task at once or refuses the
  request, so a long wait means no grant is coming. A `.queue` request waits, and a queued
  request is cancelled when the person removes the app from the app switcher.
- Bound the wait for the grant. Past the limit, refuse the attempt as an iOS refusal is handled
  and withdraw its request (`BGTaskScheduler.cancel(taskRequestWithIdentifier:)`). A task iOS
  launches after that is a late grant: complete it at once as failed, start no work under it,
  and journal it with its time so a measurement can find one.
- Install an expiration handler on every granted task. Without one the system ends the task as
  failed instead of warning it. Scope the handler to its own attempt's task, once: a handler the
  system kept past completion, or one from an earlier task, must not stop other work. Set an
  expiring flag inside the handler, before hopping to the main actor, so no progress is reported
  in between.
- Complete a granted task exactly once with the work's real outcome, even after expiration:
  output published as the system stopped the work is still output. Cancelling before the grant
  withdraws the request.
- The Mac has no continued processing; refuse each attempt at once there.

With `.fail`, 26 of 26 grants arrived within about 1.4 s of the app's launch on an iPhone 17 Pro
Max and an iPad Air 13-inch (M3), iOS and iPadOS 27.2 (24B5110a), October 2026. A 30 s grant
limit is application policy that this measurement supports, not an iOS guarantee. Grants under
memory or thermal pressure, on older devices or beside another app's continued-processing task
were not measured.

Evidence: [Pagepour measurements/background-grant/record.md](https://github.com/vocaro/Pagepour/blob/68f508d14c2a2133592027eb89806009bccf0326/measurements/background-grant/record.md).

## A task whose count stops moving can be ended as stalled

The BackgroundTasks header says a continued-processing task must report progress and that tasks
that appear stalled may be forcibly expired. Apple DTS puts the threshold at about 30 s without
the task's `progress.completedUnitCount` moving, dasd logs that the task "has not reported
progress within expected cadence, marking stalled", and Apple's article says the system ends the
tasks with the least progress first. A changed subtitle that does not move the count does not
keep a task alive.

Enforcement varied on iOS and iPadOS 27.2 (24B5110a) in October 2026. An iPhone 17 Pro Max ended
stalled tasks between about 36 and 210 s in, sooner as one evening went on, after a 325 s stall
had survived hours earlier; power source did not explain the difference. An iPad Air 13-inch
(M3) ended none, even at 645 s. Design for about 30 s. An interval that survived once is not a
deadline.

Work can leave the count still while it genuinely goes on: setup with retries and pauses,
admission checks, one slow item, or an await on a model or service that uses no processor in the
app. A model await looks stalled to the scheduler, so do not run such work under a task that
reports nothing during it. Keep the count moving only with evidence of work:

- At a fixed beat of at most half the stall window (10 s), move a count that has not moved since
  the last beat by one unit of a large total (for example 1 of 10,000).
- Count as evidence the work's own declared waits (before its first status, during a setup
  attempt or its pause), a status that did not move the fraction, a tenth of a core or more used
  since the last beat, or threads runnable but waiting for a processor.
- Never reach the total that way, and never beat after completion or once the expiration handler
  has run. Work that hangs shows no evidence and still stalls, as it should.
- Report the work's own fraction monotonically. Update the subtitle only when it changes, since
  each update redraws the system's progress.

Evidence: [Pagepour measurements/background-stall/record.md](https://github.com/vocaro/Pagepour/blob/68f508d14c2a2133592027eb89806009bccf0326/measurements/background-stall/record.md).

## Starvation is not a hang

Within about 5 s of leaving the foreground, an app holding a granted task ran as
`TASK_DARWINBG_APPLICATION` (task role 8), at background quality of service and on no
performance cores (iPhone 17 Pro Max, iOS 27.2, October 2026). It still got about a core, but
scanned-page recognition took four to eight times as long as on a Mac. System work outranked it:
Spotlight's importer and `searchd` indexing newly copied files, photo and media analysis, and
the device file service the harness used. In the worst stretches the app got 1.2 s of processor
in 79 s, its count stopped moving, and iOS ended the task as stalled.

- Separate starvation from a hang by sampling the process's processor time
  (`CLOCK_PROCESS_CPUTIME_ID`) and its runnable threads. Enumerate threads with `task_threads`
  and read `thread_info(THREAD_BASIC_INFO)`: `TH_STATE_RUNNING` without `TH_FLAGS_IDLE` means on
  a processor or waiting for one, because the kernel reports both as running. Little processor
  with several runnable threads is starvation; nothing runnable is a hang or a wait.
- A diagnostic build can journal a sample every 5 s: processor, performance-core, runnable and
  page-wait seconds and processor time by QoS (`proc_pid_rusage`), the task role, threads by
  state, and both uptime and the monotonic clock (uptime stops while the device sleeps). Keep it
  out of release builds and budget for the journal space it takes.
- The harness can cause the starvation. Files staged into a Documents folder that the Files app
  shows are indexed by Spotlight once the device is locked and charging, above a background app.
  Frequent copies of the app's store over the device connection also take processor above it.
  Stage well before a timed run and poll no more often than the run needs.
- Locking the phone cut the app to 0.13 to 0.21 of a core for about 28 s, with three to five
  threads runnable, while the device stayed awake.
- Timers in an idle backgrounded app run late (a 600 s sleep took 640 s on an iPad Air 13-inch
  (M3), iPadOS 27.2); see [device testing](../../guides/device-testing.md) for timed waits.

Evidence: [Pagepour measurements/continue-question/record.md](https://github.com/vocaro/Pagepour/blob/68f508d14c2a2133592027eb89806009bccf0326/measurements/continue-question/record.md).

## Scheduler and power logs explain why a task ended

dasd logs each continued-processing task's progress tracker (`ProgressTracker` lines), the
questions it posts and why it ended a task, in its `ContinuedProgress`, `ActivityProgress` and
`ProgressReportingMonitor` categories. A device keeps these default-level lines for hours: an
evening's lines were gone the next morning. The power log in a sysdiagnose
(`logs/powerlogs/*.PLSQL`) keeps dasd's record of each task for days, including the suspension
reason and request time when the system ended it. On iOS 27.2 the stall rule's reason was
17592186044416 (1 << 44), and only stall-ended tasks carried it.

- Collect a sysdiagnose from a reserved device as
  [device testing](../../guides/device-testing.md) describes; it holds personal data. Extract
  only dasd's progress categories, lines naming your task identifier prefix, and processor use
  by your process and the system's. Open the power log read-only (`sqlite3` with `mode=ro`).
- In the tracker's lines, `Received event result for 0: N` answers event 0, the question below.

```sh
/usr/bin/log show --archive SCRATCH_DIR/ARCHIVE/system_logs.logarchive --style ndjson --info \
  --start 'START' --end 'END' --predicate '(process == "dasd" AND (category == "ContinuedProgress"
  OR category == "ActivityProgress" OR category == "ProgressReportingMonitor"))
  OR eventMessage CONTAINS[c] "IDENTIFIER_PREFIX"'
```

## iOS asks whether a slow task should continue

About five minutes into a task whose average progress dasd judges slow, iOS asks on the Lock
Screen and under Background Activities whether to keep going: "… is N% complete. Do you want to
continue running this task in the background?", with Continue and Stop. It asks once more a few
minutes later. Apple describes the prompt in WWDC25 session 227. Observed on an iPhone 17 Pro
Max, iOS 27.2, October 2026:

- dasd's tracker leaves `BaselineWarmup` and logs the average rate of progress since the start
  ("Slow warmup ROP"). Rates of 0.047 to 0.065 of the total per minute were asked about; the
  threshold is neither logged nor published.
- `Received event result for 0: 1` is Continue. When the second question comes, dasd closes an
  unanswered first with result 0. Neither an unanswered question nor Continue ended a task.
  Answers to cards of tasks that had already ended returned result 2 and "No tracker found".
  What Stop on the question does was not measured.
- Progress counted in units of uneven cost invites the question: fast foreground items followed
  by slow background items give a low average. Progress by expected time would be asked about
  less, but needs costs the work may not know in advance.

## iOS already draws a continued-processing activity

iOS draws an activity for every granted continued-processing task while the app is not in front,
in the Dynamic Island and on the Lock Screen (iPhone 17 Pro Max, iOS 27.2, October 2026). It
shows the app's icon, the request's title, the latest subtitle as its status line, progress and
a stop button. A custom Live Activity would duplicate it; build one only for what the system's
lacks.

- With the app in front, nothing shows. The island can open to its expanded form by itself as
  the app leaves. The Lock Screen card hides its progress bar while the always-on display is
  dimmed.
- A tap opens the app, not the item; route to the item yourself if that matters.
- Stop ends the task through its expiration handler, as Apple documents for user cancellation.
  Treat it as an interruption and keep the inputs for a retry.
- Finished tasks leave the list. Tasks iOS ended, by expiry or because the process died while
  the task ran, stay listed as "Task failed" for over an hour, stacked above the next task's
  card and hiding its progress. Check that no stale card of the app is listed before an
  observation that looks for one.

Evidence: [Pagepour measurements/continued-processing-activity/record.md](https://github.com/vocaro/Pagepour/blob/68f508d14c2a2133592027eb89806009bccf0326/measurements/continued-processing-activity/record.md).

## Background compute needs a resource, an entitlement and its own qualification

A background grant, a supported compute device, a signed entitlement and acceptable output are
separate requirements. As read from the iOS 27.1 SDK in Xcode 27.1 (27A9269) and Apple's
documentation in October 2026:

- `BGContinuedProcessingTaskRequest.Resources` has one option, `.gpu`. The default, `[]`, is CPU
  and network. There is no Neural Engine option.
- `.gpu` needs the Background GPU Access entitlement
  (`com.apple.developer.background-tasks.continued-processing.gpu`) and device support, read
  from `BGTaskScheduler.supportedResources`; Apple publishes no device list. Apple DTS has said
  it is supported only on iPads with an M3 or later and on no iPhone, and an iPad Air (M3) on
  iPadOS 27.2 reported `.gpu`. Under heavy GPU contention the header promises no runtime. Xcode
  27.1 does not offer the capability to wildcard App IDs, so the app needs its own App ID and
  profile.
- Without the GPU resource, iOS refuses GPU work from a backgrounded app: Metal returns
  `notPermitted` for each new command buffer.
- iOS 27 requires the Background Inference entitlement
  (`com.apple.developer.background-tasks.continued-processing.inference`) for any Neural Engine
  use in the background, with or without a continued-processing task. In September and October
  2026 Xcode rejected it as not a valid entitlement, no profile carrying it could be issued, and
  a build that claimed it failed provisioning before installation. An unentitled run cannot
  reveal which compute unit served it.

Consequences for recognition and inference work:

- Vision's automatic compute selection does not report the device it used and may choose the
  Neural Engine. For background work, select the CPU explicitly before every request: require
  CPU support at every advertised compute stage, select it, read the selection back, and fail
  with a typed error rather than fall back to automatic compute or an ordinary fallback path.
- Fix the compute policy before the work starts. It cannot carry on from the foreground into the
  background, and changing it midway would mix two recognitions in one output.
- CPU-only recognition can read worse than automatic compute, so qualify output quality
  separately. CPU eligibility alone does not qualify a background path: validate each request
  type on each supported device and OS, then complete runs, cancellation and cleanup in the
  intended execution context with the signed app. A foreground probe or policy unit tests give
  no background-lifetime or quality guarantee.
- A probe app needs a scene delegate: iPadOS 27.2 stopped an app without one as its first scene
  was created.

Evidence: [Pagepour measurements/ios-gpu-background/record.md](https://github.com/vocaro/Pagepour/blob/68f508d14c2a2133592027eb89806009bccf0326/measurements/ios-gpu-background/record.md).

## Testing continued processing

- Put the scheduler behind a seam that tests can make grant, refuse or never answer, and stand
  in for processor time and runnable threads, so lifecycle tests need no device.
- On a reserved device, in a window agreed with the owner (see
  [shared host](../../guides/shared-host.md)), a check that only needs work started and the app
  backgrounded runs without UI automation: launch the app with an argument that starts the work,
  then launch Settings to send it to the background, as
  [device testing](../../guides/device-testing.md) describes, and copy the journal afterwards.
  The device must stay connected, unlocked and untouched.
- Prove background execution from the journal: progress callbacks belonging to the admitted
  attempt, with UIKit's application state background, before any reactivation. Progress seen
  only after the app returns proves nothing about the background.
- No public API forces scheduler expiry. User Stop reaches the expiration handler and is
  testable; natural expiry under resource pressure stays unmeasured unless it is induced.
- Work that spans a device lock needs protected-data observations around it; see
  [data protection](data-protection.md).

## On the Mac, hold a user-initiated activity

The Mac has no continued processing, and macOS idle-sleeps on its energy settings whatever the
processor is doing unless a process holds an assertion. While work the person asked for runs,
hold a `ProcessInfo` activity with `.userInitiated`: it keeps the system from idle sleep and the
app out of App Nap, and lets the display sleep. Apple asks that it be kept to work the person
started, so work a relaunch resumes on its own does not qualify. Read the assertion back from
IOKit in tests.

## Shared implementation

BackgroundTaskLib owns the domain-independent continued-processing state machine: per-attempt
identifiers, registration and submission, bounded grant waits, late-grant rejection, the
evidence-based heartbeat and scoped expiration. Applications own admission (such as a compute
check), entitlements, status wording and persistence. A grant does not select a file protection
class or persist work across a restart.
