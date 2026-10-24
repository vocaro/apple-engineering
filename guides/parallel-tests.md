# Parallel tests

These mechanisms apply to every project. Original measurements establish their recorded host,
load and workload; they do not establish the speedup another suite or host will see.

A gate is shorter when its independent parts run at once. Work runs side by side at three
levels, and a project can use any of them:

| Level | What runs at once | Mechanism |
| --- | --- | --- |
| Suites | A gate's independent lanes: the Mac suite beside the simulator suites, script tests beside both | A lane group in engineering.json |
| Devices | One build's tests on several simulators | `eng simulator-tests` |
| Tests | One suite's tests in several workers | The test runner's own option |

Admission still counts the whole gate as one job, however many workers it starts
([heavy-work admission](shared-host.md#heavy-work-admission)), so every level is bounded
([budget](#bound-what-runs-at-once)). Each part keeps its own log and its own outcome, and the
whole fails when any part failed, and is otherwise unmeasured when any part was
([honest outcome states](evidence.md#honest-outcome-states)).

## Suites side by side

A lane whose `parallel` names other lanes runs them at once under its own single admission:

```json
"lanes": {
  "mac-tests": {"command": ["swift", "test"], "resource": "heavy", "minimumTests": 3000},
  "ios-tests": {"command": ["python3", "scripts/eng", "simulator-tests", "--scheme", "Package-Tests",
                            "--runtime", "iOS-27-0", "--device", "iPhone-17-Pro",
                            "--device", "iPad-Air-13-inch-M4"], "resource": "heavy", "minimumTests": 6000},
  "tests": {"parallel": ["mac-tests", "ios-tests"], "resource": "heavy"}
}
```

- `python3 scripts/eng run tests` takes one slot, starts every named lane, and writes each one's
  log to `.build/engineering/tests/lanes/LANE.log`. Each lane is judged as `eng run LANE` would
  judge it: its `minimumTests`, its `timeout` and the unmeasured tests its log reports. A
  failed lane's last 40 log lines print under its result; the others still run to their end.
  The run ends with each lane's seconds and the receipt records them.
- `jobs` bounds how many of the group's lanes run at once; it defaults to all of them.
- The group needs a `resource` at least as heavy as its heaviest lane. A lane that takes the
  screen cannot join a group, and a group cannot name another group. A group takes no
  arguments: filter one of its lanes instead (`eng run ios-tests -- -only-testing:T/C`).
- A group marked `buildHost` goes to the build host whole. Its lanes' own `buildHost` marks
  apply only when they run alone.
- `eng run --serial GROUP` runs the lanes one after another, on this Mac: the reference a
  failure seen only side by side is checked against ([parallel-only failures](#a-failure-seen-only-side-by-side)).

Lanes that share a build directory cannot run side by side: two `swift test` runs in one
`.build` wait on its lock, and two xcodebuild runs need separate `-derivedDataPath`s. A gate
step that needs another's output stays a separate step before the group.

## Simulators side by side

`eng simulator-tests` builds a scheme's tests once and runs them on every named device at once:

```sh
python3 scripts/eng simulator-tests --scheme SCHEME --runtime iOS-27-0 \
  --device iPhone-17-Pro --device iPad-Air-13-inch-M4 --build-jobs 4 -- -only-testing:TARGET/CLASS
```

- Each device is a [disposable simulator](simulator-testing.md#disposable-simulators): created
  for this run under a unique name, addressed by its UDID, and shut down and deleted however
  the run ends, a stop included.
- The devices boot while `xcodebuild build-for-testing` builds for the first device. Building for
  one simulator builds only its architecture, where `generic/platform=iOS Simulator` builds
  every one. Each device then runs `xcodebuild test-without-building` on the same `.xctestrun`,
  with its own log and a new result bundle under `.build/simulator-tests/logs`.
- Arguments after `--` go to every device's test run, not to the build. `-C DIRECTORY` runs in a
  package's directory, where xcodebuild finds its scheme; `--xcode-project` or `--workspace`
  names a project instead. `--setting NAME=VALUE` adds a build setting.
- A boot still running at `--boot-timeout` (600 s) leaves that device unmeasured and the others
  run on; a first boot can stall while other simulators boot. `--test-timeout` is a backstop for
  a hung run, which it leaves unmeasured. A device that ran no test fails.
- The run prints `Executed N tests` for each device, which a lane's `minimumTests` counts, and
  repeats every unmeasured line, so the lane is unmeasured too.
- `--jobs N` tests N devices at a time. `--jobs 1` tests them in turn: the serial reference.
- `--workers N` turns on xcodebuild's parallel testing on each device, which clones the device
  for each worker and deletes the clones itself. It stays off by default, as in the
  [simulator method](simulator-testing.md#xctest-execution-discipline), until a suite has been
  shown to pass with it.

The Mac suite joins through a lane group beside the simulator lane, as in the example above.
`tests/fixtures/SimulatorSmoke` is the toolkit's positive control: one XCTest and one Swift
Testing test, which every device must count.

## Tests within one suite

| Runner | Side by side | One at a time |
| --- | --- | --- |
| Swift Testing | Tests run concurrently in one process by default | `swift test --no-parallel`, or `.serialized` on a suite |
| XCTest under `swift test` | `swift test --parallel --num-workers N`: N processes | The default |
| xcodebuild | `-parallel-testing-enabled YES -parallel-testing-worker-count N`: a clone per worker | `-parallel-testing-enabled NO` |
| pytest | pytest-xdist: `-n N --dist loadgroup`, with an `xdist_group` mark on tests that share state | `-n 0` |
| unittest | `python3 scripts/eng unittest -s tests -j N` | `python3 -m unittest discover -s tests` |

`eng unittest` discovers the suite as unittest does and runs each module in its own process, N
at a time (four by default). `--split class` or `--split test` runs each class or each test
apart instead; a module or class that sets `serial_group = "NAME"` runs in one process with every
other of that group, one after another. Each process's output prints whole, under a line that
names it. The summary is not a `Ran N tests` line, so a lane counts each test once, and a
process that ran fewer tests than discovery found for it fails. The slowest module bounds the
run, so split a module that dominates.

Keep tests that share state out of each other's way rather than turning parallelism off: a
group, an `xdist_group` or a serialized suite for the few that must share; per-test fixtures
for the rest ([tests own their files and defaults](app-testing.md#tests-own-their-files-and-defaults)).

## Bound what runs at once

- A gate's concurrency is every part running at once: its side-by-side lanes, each one's test
  workers and simulators, and each build's compiler jobs. Bound each with one named setting,
  such as a lane group's `jobs`, `--build-jobs`, `-j` or `-n`, and state the bound where the
  gate is defined, so that the whole stays within one job of the host
  ([heavy-work admission](shared-host.md#heavy-work-admission)).
- Run two compiles side by side only with their jobs bounded, so that together they keep within
  the gate's bound.
- A test that waits for a duration fails when other work takes the cores. Its wait bounds a
  stall instead ([waits bound stalls](app-testing.md#waits-bound-stalls)), and a time limit leaves
  out the seconds its work waited for a core
  ([core-wait time](measurement.md#cpu-scheduling-and-core-wait-time)). A suite whose tests still
  assume a quiet host runs alone until they are fixed.
- Memory and timing measurements run in a process of their own and never beside other work
  ([framework lifetimes](../knowledge/apple/framework-lifetimes.md)). So do exclusive work and
  lanes that take the screen.

## A failure seen only side by side

Run the serial reference at the same commit: `eng run --serial GROUP`, `--jobs 1`, `-j 1` or the
runner's one-at-a-time form. A test that passes alone and fails beside others is an isolation
defect in that test or its fixture: two tests sharing a path, a defaults domain, a simulator or
a build directory, or a wait that a busy host can expire. Fix it, or put the tests that share
in one group. Never serialize the whole suite, rerun until it passes, or weaken an assertion to
hide it.

## Measuring a speedup

Compare the serial reference and the side-by-side run at the same commit on the same host, with
its one-minute load average recorded for both, and repeat under controlled load when the host
was busy. Report each part's seconds, which the lane group and `eng unittest` print.

The toolkit's own Python suite, 159 tests in 11 modules, took 168 s with
`python3 -m unittest discover` and 67.5 s with `eng unittest` at four processes, on an 18-core
M5 Max (2026-10-24). The host's one-minute load average was 93 during the first run and 507
during the second, so neither time is a bound. The second was bounded by its slowest module,
`test_remote`, which took 63 s by itself and 19 s with `--split test`. At 179 tests, run back to
back at load averages near 200, the whole suite took 56.0 s by module and 43.6 s by test, so
the toolkit's lane splits by test.

`eng simulator-tests` ran `tests/fixtures/SimulatorSmoke` on an iPhone 17 Pro and an iPad Air
13-inch (M4) simulator side by side on an M1 Max build host, macOS 27.2, Xcode 27.1, iOS 27.0
(2026-10-24): one 26 s build, both devices tested at once, 2 tests counted on each, 162 s in
all, and both devices deleted afterward. Its two tests measure the cost of booting and launching,
not a suite's speedup.
