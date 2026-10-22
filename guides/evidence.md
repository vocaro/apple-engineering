# Evidence

These mechanisms and lessons apply when the stated capability is present. Original
measurements establish their recorded platform and workload; they do not establish
universal behavior on later operating systems or in a different application.

Measurement methods are in [measurement](measurement.md), oracles and reference engines in
[external validation](external-validation.md), and OS release protocol in
[OS and model drift](os-drift.md).

## Public and private destinations

Review source and payloads before publishing a record. Private integration logs, personal device
identities and raw private transcripts belong in their private owning project or the private
apple-engineering-evidence archive. Public articles and issues can retain reviewed methods,
source identities, results and limits. Private provenance links are supplemental; public
contributors must be able to run the tools without those records. See
[public access](public-access.md) for the repository boundary.

Publish only synthetic evidence:

- Exclude personal Home Screen, Lock Screen and authentication captures, presented share sheets
  (they can show the owner's contact suggestions) and proprietary inputs. Treat a raw result
  export as private: it can hold automatic diagnostic screenshots.
- Redact incidental device identity, host paths and memory addresses, then hash the final bytes.
  Verify every manifest entry against the bytes it names.
- Review the pixels and trees themselves. A file name does not prove a layout, orientation,
  rotor category or focus state. Prefix filtering and redaction do not prove that an input is
  free of personal data, and a receipt cannot prove that a simulator holds no personal contacts
  or imported files.

Classify each run's raw rows as public or private in its plan, and refuse a plan that does not
say. Private rows, the first fetched copy of them and any scorer input derived from them stay
outside the repository and every Git worktree, ignored or not, in an owner-only archive with
their receipt beside them.

Admit private sources and answer keys through a content-free receipt: pseudonyms, counts,
digests and review metadata, with no paths, bytes, prompts, reference answers, retrieved spans,
raw review notes or reviewer identities. Zero admitted receipts is a passing state, not evidence
that a private profile was measured.

Key a device in shared records by a project-namespaced SHA-256 of its hardware identifier
(`IOPlatformUUID` on a Mac), never by raw hardware identity, hostname or account. A run on
another device uses that device's key, never the controller's. Fail rather than group rows whose
device could not be identified.

## Planning acceptance and diagnostic work

Before physical-device, assistive or attended qualification, write down the behavior being
qualified, the required evidence, the actual host, device and runtime, the layout and text size,
the dependency pins and the build under test.

- Separate a complete acceptance run from smoke checks and diagnostic probes. A simulator pass,
  an accessibility hierarchy or a partly successful result bundle does not substitute for
  required physical or assistive interaction.
- Set a diagnostic timebox and a retry bound before spending scarce device time. When the
  timebox runs out, report what failed, what was learned and what further work is needed. Do not
  let a product check grow silently into a harness project; report material growth in effort or
  scope.
- Required coverage stays open until it is measured or the owner changes its scope.
- Run the smallest relevant observer case first on each required device or presentation. After a
  failure, keep its captures and logs, release the device and diagnose offline where possible.
- Validate an observer correction against the failing examples and negative controls. Rerun the
  failing case, then run the complete matrix once. Report diagnostic passes separately from the
  final acceptance result.
- Moving qualification work to another device needs a fresh artifact prepared there, and every
  path in one qualification package uses that same unchanged artifact. Never splice results from
  different artifacts into one package.

Device reservations and handoffs are in [shared host](shared-host.md).

## Evidence collection

Record, for every run that may become evidence, the source commit and working-tree state,
resolved dependency revisions, device, OS and build, the selected Xcode (`DEVELOPER_DIR`),
effective settings and actual viewport. For a hosted run also record the runner image and its
version, System Integrity Protection state and screen. Give every attempt fresh log and result
paths.

Freeze identities before the run:

- Hash the production executable, any debug dylib, the test binary, the exact measured test
  source and the copied launch manifest. Keep a reconstructable patch against a named base
  revision for an uncommitted probe. Verify the hashes again after termination. Hashing a later
  build cannot establish what ran earlier, and a later source edit does not change an earlier
  receipt.
- When correcting only an observer, reuse the exact production app already qualified. A copied
  `.xctestrun` must point to that frozen app, use the intended test binary, restrict the test
  identifiers and carry the required opt-in environment. A successful build alone establishes
  none of these launch identities.
- Record a build's revision when it is built, not when it runs. Take
  `git describe --always --dirty` before building and store it beside the products after a
  successful build. Remove the stored record before any rebuild, so a failed or interrupted
  rebuild cannot leave the old one, and read it back when a run skips the build. Report a build
  the runner did not record as unknown, and the checkout's current revision separately. `-dirty`
  says tracked edits existed; it does not identify them, so keep the patch or a digest of the
  working changes.

Reserve a private capture directory exclusively before a gate starts. Identify the commit, tree,
staged and unstaged changes and nonignored untracked inputs. A changed candidate refuses a
passing receipt and leaves the gate's results intact. Capture a failed early build too. An
interrupted capture is incomplete, never a pass.

Export result bundles sequentially. Serialize `xcresulttool` summary, test-tree and attachment
extraction for one bundle: concurrent readers met result and cache initialization races (Xcode
27, October 2026). Use the `DEVELOPER_DIR` of the Xcode that produced the bundle. A stopped
run's bundle can lack `Info.plist`, so `xcresulttool` cannot open it, while its log archive
still opens with `log show --archive`. Hosted-run artifacts expire; copy what must be kept,
including crash reports (`.ips`).

Have tests write synthetic captures, viewport receipts and accessibility text into a unique
directory in the runner's temporary container and print its path. The captures then survive a
result bundle Xcode could not finalize; they do not turn an interrupted run into a pass. Keep
failed captures as unavailable evidence, apart from acceptance pixels. Qualify an observer
change offline by replaying it against retained, hashed captures, including negative controls
whose expected result is empty, without lowering its thresholds; offline replay qualifies the
observer, not the product. The rotor-HUD replay method is in [VoiceOver](voiceover.md).

Retain raw rows before anything consumes them:

- Canonicalize each fetched row set, record its digest and publish it create-only and
  atomically: write a synced temporary file on the same file system (mode `0600` for private
  rows), then rename it into place, so an interruption cannot leave a short final file. A
  retention failure leaves the run collected for a retry without another generation, and the
  scoring boundary checks retention again.
- Deleted rows cannot be re-diagnosed, and the aggregates that outlive them are content-free. A
  missing, locked, timed-out or short job is missing coverage, never a measured zero.
- A rerun of a predeclared plan is a second generation, identified by job and run and stored at
  its own path. Never overwrite an earlier generation's archive or receipts.
- Normalize identifier case before binding. `uuidgen` prints uppercase; a harness that
  lowercases run IDs in its rows then fails exact joins, and re-binding with the corrected
  identity adds a second entry beside the first. Restore the receipt and bind again.
- Merge two appends to one ledger as the time-ordered union of both sides, each side's order
  kept. Never edit or drop a line to resolve the conflict.

Commit measurement evidence as plain, uncompressed files; what a record directory holds is in
[maintenance](maintenance.md). Ignored or externally supplied inputs need a checksum and a
durable location or a verified reproduction recipe. Commit small inputs that no producer can
recreate, and restore them create-only after verifying their pins.

## Evidence commands

`python3 scripts/eng run LANE` writes `.build/engineering/LANE/source.json` beside the lane's
`run.log`. It records the project's and toolkit's commit with a SHA-256 of their working changes
(tracked diff and untracked files), the policy commit for a heavy or exclusive lane, the argv,
and the exit status or `failed-or-interrupted`. After a zero exit, a lane with `minimumTests`
fails unless the log reports at least that many executed XCTest, Swift Testing or unittest
tests.

`python3 scripts/eng admit -- COMMAND` records the same fields, with the directory the command
ran in and whether it was exclusive, in `.build/engineering/admit/source.json`. Its output stays
on the terminal, so it writes no log, and the next admitted command in that checkout replaces
the receipt: copy it with the run's output when it is evidence.

`python3 scripts/eng evidence verify DIRECTORY` checks `DIRECTORY/receipt.json`, a version 1 map
of relative paths to SHA-256. It rejects an empty receipt, absolute or escaping paths and
changed bytes. It does not look for files the receipt omits.

`src/python/vocaro_engineering/reader_evidence.py` collects test-result evidence. A project
adapter defines its product's settings and then loads the module. No command launches an app,
controls a device or changes accessibility settings.

- `PROFILES` maps each publication profile to the attachment-name prefixes it may retain.
- `SIMULATOR_PROFILES` names the profiles whose run must have a simulator host receipt.
- `LOG_MARKER` is the prefix of the app's own runner-log lines, such as `READER`; `retain`
  refuses to run without it.
- `PRIVATE_LOG_LINES` lists prefixes of log lines withheld because they name a private
  location, such as a simulator's container path.

`retain` and `reader_log` also take these as arguments.

```sh
python3 ADAPTER receipt PREFIX-revision.json --metadata RUN.json FILE...
python3 ADAPTER verify-receipt PREFIX-revision.json
python3 ADAPTER export RESULT.xcresult PREFIX
python3 ADAPTER retain PREFIX DESTINATION --profile PROFILE
python3 ADAPTER index ROOT
python3 ADAPTER verify ROOT
```

- `receipt` takes run metadata (source revision, dependency pins, device, OS and build,
  toolchain, original settings, intended test IDs, measured patch base), adds `capturedAtUTC`
  and a `sha256` map keyed by absolute path, and refuses an existing output. Capture it before
  launch; run `verify-receipt` again after the terminal result. It hashes current bytes and
  cannot prove that a later snapshot is the binary that ran.
- `export` writes `PREFIX-summary.json`, `PREFIX-tests.json` and `PREFIX-attachments/` one after
  another, checking each JSON before saving it, and refuses existing outputs. The raw export is
  private. A failure can leave partial private outputs; use a fresh prefix for a deliberate
  retry.
- `retain` needs the export, `PREFIX-revision.json` from the before-launch receipt and
  `PREFIX.log` from the runner; it never invents a missing identity. It keeps PNG and UTF-8 text
  attachments whose names match the profile (`--text-only` drops images), groups them by test
  case, rejects colliding or escaping paths, removes known device-identity fields from JSON,
  replaces memory addresses in text, keeps the runner log's observation and test-case lines,
  copies images unchanged, and stages the package before moving it into a destination that must
  not exist. Review every retained file before publication.
- `index` replaces `ROOT/evidence-hashes.json` (`--index PATH` selects another location) with
  current hashes; `verify` reports missing, changed and unindexed files without modifying
  anything. Rebuilding an index over modified data does not verify its history, so review new
  evidence before indexing it.

## Source identities and receipts

The producing revision and environment are authoritative for an observation. Keep its raw
results, input hashes, configuration, toolchain and OS details and exact Git revision, and
resolve its source hashes at that revision, not against the current checkout. A refactor does
not change what an earlier run observed. It needs no rerun, compatibility adapter, monkeypatched
old reader or frozen current test. Changed product behavior needs fresh qualification before an
old result supports a current claim.

Replay a historical run explicitly: create an isolated worktree at the recorded revision, follow
that revision's setup, provision its recorded inputs and run its own commands. An old OS or
compiled model may no longer be available, so source retention does not promise reproduction.
Never run model or metered-service campaigns merely to validate archived files. Keep an explicit
inventory of tests excluded from the current suite, each with its reason and the revision that
retains it. Collect new tests by default, and never count an exclusion as passing.

Gate current behavior, not provenance. Split a receipt into a behavior projection (content,
spans, ranks, metrics and declared OS-owned states, as in [OS and model drift](os-drift.md)),
which its gate compares with a fresh capture, and producer identities, which are recorded as
provenance. Consumers pin the projection. Moving source changes provenance without failing a
gate; a changed outcome fails and needs investigation and a new measurement.

Choose producer pins that go stale for the right reasons:

- A commit pin goes stale on every commit. A module-interface digest misses implementation
  changes. Built-product bytes move with debug information, symbol order, signing and the
  checkout path a release binary embeds. Pin the producing source files' bytes.
- Pin a projection of the dependency lock, not lockfile bytes: every package reachable from the
  runtime dependencies with its version, source, edges and artifact hashes, plus the runtime
  specifiers. A development-tool change then leaves the pin current, and a runtime change stales
  it.
- Pin the stable files of a compiled model. On macOS 27.0 (26A428) with Xcode 27A266a, compiling
  one unchanged Core ML package rewrote `coremldata.bin` and `analytics/coremldata.bin` on every
  run and ordered two `metadata.json` keys either way; only `model.mil` and `weights/weight.bin`
  were stable. Record the full compiled population as history and never compare it with a fresh
  compile.
- An imported manifest that carries a fresh UUID and timestamp names one import event, not
  reproducible content. Freeze a content digest for a content claim and retain the exact package
  for a release claim. A semantic identity may normalize serialization noise, such as protobuf
  map order and manifest UUIDs, only while it keeps the model graph and weights exact.
- A weaker older receipt cannot be upgraded retroactively. A successor may validate what the raw
  receipt itself establishes and must state which joins remain unproved.

Receipts pin other receipts, so a refresh cascades. Regenerate bottom-up, then sweep again to a
fixed point. No gate compares a digest quoted in prose, so it drifts, and a policy value such as
"absent" for a fetch-on-demand source is not an observation. Regenerate a derived artifact that
decides eligibility atomically, as a campaign's terminal step with all its inputs wired, never
one link at a time while evidence is still arriving. Diff the artifact and also run its
consumers; prefer a visibly stale report to a half-advanced chain.

Write a release receipt only after every required test passed with none skipped, bound to the
source, app version and build, OS and Xcode; an edit during or after the run invalidates it.
Fixture smoke evidence establishes wiring, not delivery of shipping assets or quality.

## Honest outcome states

Report one of four outcomes:

- **passed**: the selected check ran and met its expectations.
- **failed**: it ran and did not.
- **skipped**: it was not selected, or it is opt-in and disabled, and the skip is reported.
- **unmeasured**: it was selected but produced no valid result. Record the cause: an unavailable
  framework, model or device, host pressure, an observation timeout or a transport failure.

Unmeasured is never green. Exit 0 for passed, 1 for failed and 3 when unmeasured results are all
that stand between a run and a pass; 2 stays a usage or tool error, as in `eng` and argparse. A failure outranks anything unmeasured, which is still
listed. Require an independent positive control before blaming an unavailable framework or
model.

Gate an opt-in test visibly. An early `return` when a variable is unset reports the un-run
harness as a pass; Swift Testing's `.enabled(if:)` trait reports a skip, which keeps "nothing
ran" apart from "everything passed". Keep the predicate a site was measured under: presence of a
variable differs from requiring exactly `1`. Gate artifacts, fixtures, models and OS floors the
same way, and never put a generative call in a trait condition. Optional integration tests skip
visibly when their inputs are absent; a require flag turns that skip into a failure.

Judge a test that needs a live framework reading by an independent probe, never by the test's
own expectations:

- Hold the test's failures. When the test ends, have test support, not the library, ask the
  framework for a known input, such as one large word drawn black on white for OCR.
- If the probe succeeds, record every held failure exactly as it was. If it throws, reads
  nothing or misreads, cancel the test as unmeasured with the probe's reason and show its
  failures as warnings. A pass made without a reading is unmeasured too, and the whole test is
  unmeasured, including expectations that did not need the framework.
- Run the probe after the test. Run first, it released every such test onto a shared
  serialization gate at once and starved the cooperative pool (see
  [Swift concurrency](../knowledge/apple/swift-concurrency.md)).
- An end-of-test probe sees only a framework that is still failing; a failure that recovered
  during the test goes unseen.
- `swift test` can only pass or fail, and a canceled test passes. Run it through a wrapper that
  reads an out-of-band report of unmeasured tests, starts from a fresh report file each run,
  treats an unreadable report as a failure and maps the result to 0, 1 or 3. A simulation switch
  that makes the probe report unavailability proves the treatment on a working host; every line
  it causes says SIMULATED.

Classify device and assistive results as product defects, observer failures, transport failures
or unavailable coverage. Reproduce a supplied control's failure in a minimal host before
assigning it. A failed aggregate stays failed even when several cases passed; a later successful
result supersedes it without rewriting its outcome.

A `devicectl --console` stream is not completion authority: the Xcode test transport can omit
the terminal line after the app finished. Device-written rows and host-side validation are
authoritative, and a watchdog classifies locked, unavailable, wedged and incomplete work as
unmeasured. A harness that hears nothing at extreme load has failed as a harness, not as a
product: simulator VoiceOver sessions at load averages near 1,000 read nothing at all (iOS 27.0
simulators, Xcode 27.0, October 2026).

Mark a test that exposes an open defect as a known issue with its issue URL (`XCTExpectFailure`,
or `withKnownIssue` in Swift Testing), so it fails once the defect is fixed, and remove the
marker with the fix. Make it non-strict or platform-specific only where the defect is
timing-dependent or appears on one platform. Disable a test whose input kills the test process
by name, with its issue beside it. Bound work that might never terminate, such as a layout that
keeps asking for space, so the test fails instead of hanging the suite.

## Late callbacks and quiet periods

A bounded quiet period after an operation detects late callbacks; it cannot prove that none will
ever arrive. To catch both work queued during the operation and work sent from the component's
own short timer:

1. Yield, so work queued while the operation ended has started.
2. Wait the quiet period, then a margin more.
3. Look.

Two overdue sleeps resume in either order, so a callback from a short sleep can arrive just
after the quiet period ends. The margin is not a bound: under heavy load on macOS 27 (October
2026) a 20 ms margin was exceeded, at 29 and 42 ms, in 2 of 11,235 attempts. Reproduce the race
by stopping the test process from a helper across both sleeps (`kill -STOP`, then `kill -CONT`
once both are due), which delivers them together.

Wait the same way before counting events after a reset, so a correct component's trailing
reports are not read as a stale step's effect. Keep two controls: a correct component that must
pass and a broken one that must fail.

## Independent correctness checks

Take expectations from standards, independent implementations, an explicit product decision or a
reading of the source itself, never from the implementation under test. Independence belongs in
the rule, not merely in a second extractor: one that runs words together is no recall reference.
Keys for recovered content come from an independent extractor, because keys written from derived
text cannot see a hole in the derivation.

When adding or changing a regression:

1. Reproduce the defect from a pinned source. Add a small original synthetic fixture when that
   isolates the mechanism, and keep a source-derived target.
2. Read the source before writing expected text, order, values or image properties.
3. Prove the test fails on the old behavior. Keep unresolved defects as issues with known-issue
   markers; never bless them as golden output or disguise them as passing tests.
4. Add positive controls for neighboring behavior and for another input type.
5. Review changed counts in both directions; increases and decreases can both be suspicious.
   Update an expectation only after reviewing the source and stating the intended change.

Run seeded fuzzing over a bounded seed range in the regular suite and over a wider range on
demand in an optimized build. Run optimized test builds as well as debug ones (see
[simulator testing](simulator-testing.md)), and give recursive code exact-stack worker coverage
(see [stack and work bounds](../knowledge/apple/stack-and-work-bounds.md)).

## Comparing runs across builds and environments

A comparison holds everything fixed except the change. The same binary can produce different
rasters and OCR when launched from different environments on one Mac, and an OS string or a
caller-supplied context label does not establish comparable capabilities. Executable name and
code-signing identity also select framework state; see
[framework execution identity](../knowledge/apple/framework-execution-identity.md).

Before and after a change:

- Record both sides on the same main. Merge main into the branch first, and take as "before" a
  commit that holds main and only the change's fixture, built in a second worktree. Main gains
  commits quickly, and one landing between two recordings can be mistaken for the change.
- Build the base commit's release product once, in its own worktree, and give every comparison
  that one binary.
- Record evidence in the acceptance mode. An exploratory shortcut can record something else: an
  accelerated step once recorded a control's hint in place of its name. Rerun a failure first
  seen in an exploratory mode in the acceptance mode before reporting it.
- A release binary embeds its checkout path, so identical sources give different executable
  hashes in different checkouts. Show that a landed change is the one measured by comparing
  outputs, not binary hashes.

For a strict drift comparison:

- Compile one capability probe and reuse that exact executable for both runs. Run it immediately
  before each conversion against the same verified input and launch environment, and recapture
  both runs when the probe's identity changes. A probe timeout, launch failure, malformed
  output, stale identity or framework failure fails the capability gate and keeps the
  diagnostics.
- Record per run a fresh run ID, the SHA-256 of each executable, of the probe result and of the
  output, the source identity, and the system, build and architecture. Verify retained outputs
  against their receipt. A declared execution-context label is supplemental.
- Refuse missing, failed, stale or incompatible capability receipts, and runs that failed a
  gate. A run whose resource ceiling was merely unmeasured can be compared when nothing compared
  depends on it; name it in the result.
- Compare content, not generated identifiers. Normalize document-wide renumbering (paragraph
  ordinals, asset names), hold images by content hash, and report renames and identifier-only
  shifts separately without failing. Record attributes that change meaning without changing
  text, such as direction.
- Converting twice with one binary is not a no-op: a framework's reading can differ between two
  runs of one unchanged binary on one host. Take a third run with the baseline's own binary as a
  control. Attribute to the change only what the control does not also move, report the rest as
  unstable, and refuse a control whose binary hash differs from the baseline's. An unstable item
  may still hold a real change; say that the comparison cannot tell.
- Record compiled framework-model digests before and after each run, and flag a comparison whose
  runs did not share one unchanged compile.
- Across a corpus, compare one document at a time and delete both outputs as you go. For a
  document that differs, keep per-part SHA-256, block and character counts, and hashes of
  tag-stripped text and of its letters alone, so moved markup, reordered text and lost
  characters show in different fields.

Local receipts are consistency checks, not signed attestation. A capability probe on one page
samples one instant; it cannot prove later pages or service states equivalent. A content
comparison does not cover every semantic detail, decoded image equivalence or visual fidelity,
so keep content, resource, conformance and human-review gates beside it.

Evidence: [PDFReflowLib measurements/same-binary-control-runs/record.md](https://github.com/vocaro/PDFReflowLib/blob/dc89a4eccecb99943661709887fd2a61a1a51b29/measurements/same-binary-control-runs/record.md).

## Byte identity for refactors

A change that claims to preserve behavior produces byte-identical output against the previous
build on every corpus, policy-variant and fixture conversion that completes under default
budgets, and inputs that stop at a budget stop at the same point. Pin fields that vary per run,
such as a package identifier and modification time, normalize them to placeholders that must
each occur exactly once, and compare reports except for output paths. Give the identity tool
negative controls. State the claim and the number of conversions checked in the commit message.

Identity is stronger than a content comparison and narrower: it holds on one host and OS build.
Rendering, OCR and image encoding can differ across builds and devices, which is what capability
receipts and content comparison handle. A change that alters bytes on purpose is a fix, not a
refactor, and goes through reviewed expectation changes.

## Corpus provenance

Pin every external input in a committed manifest: byte count and SHA-256, or the extractor
identity where a consumer holds the pin, plus license, retrieval date, provenance note and the
exact derivation command. Keep source and attribution URLs separate from the direct download
URL.

Fetch explicitly, through the repository's own path:

- Download into an ignored cache. Read a pinned download completely into private staging on the
  destination volume, verify its size and SHA-256, and publish it create-only. A failed transfer
  or mismatched candidate leaves no destination or staging file, and a failed refresh keeps the
  existing copy. Verify cache hits as well as downloads.
- Reject symlinks, directories and other nonregular files without reading them. Report a present
  file whose bytes drifted and never overwrite it. Record an unpinned entry's observed bytes
  only on explicit request, and never change an existing pin that way.
- Tests and conversions never fetch. Gates run offline against verified local copies and report
  a missing optional source as a skip; a dedicated command whose source is missing fails.
- To pin a new source, use the publisher's own official download location and record how it was
  established, never a URL an arbitrary page suggested or an undocumented mirror. Verify through
  the repository's path and reproduce the identity with an independent re-fetch; a source that
  fails any of these stays unpinned. When the primary location stops serving automated clients,
  a separate manifest may name the publisher's own alternate location with the same identity.
  Pin a user agent only when an official endpoint rejects the default one.

Respect each site's automated-access policy:

- Read robots.txt first. Make one request at a time, at least 2 s apart, and run one fetch at a
  time across sessions. Where a robot-access policy limits automation to mirrors or harvest
  endpoints, fetch only from those.
- Where robots.txt disallows AI agents' user agents, or a bulk route needs a login, only the
  owner fetches. Never bypass a bot challenge or log in. Record owner-supplied bytes with their
  hash and size, the publisher's page and the fact that the owner supplied them. Never
  auto-download such a source; verify the local copy, or tell the owner it is needed.
- A source whose URLs carry no version republishes in place. Keep a mismatched download beside
  the corpus under a distinct name and leave its variable unset. Re-pin deliberately: fetch
  every item afresh into a directory named for the date, record the new hashes and date, rerun
  the corpus tests and commit the manifest with the reason and the results.
- Commit the raw bytes of a source that changes in place and is not archived elsewhere; for it,
  a checksum can only say that the original is gone.

Licenses:

- Pin the exact license-verified snapshot or edition. Later editions can carry different terms,
  and the freer label is often the one that circulates: pin the artifact, not the name of the
  work or curriculum.
- A catalog's license label is metadata, not clearance; the work's own statement governs.
  Illustrated works often credit figures under other terms chapter by chapter, and an AI-use
  notice can sit in a collapsed attribution block of an otherwise permissive page.
- Admit affirmatively. "Not NonCommercial" is not the test: a no-derivatives license does not
  survive chunking, indexing or generating questions, and share-alike can conflict with the
  consuming project's license policy.
- Keep NonCommercial or otherwise restricted inputs outside the repository and distributed
  resources. Their importer verifies the exact source and license hashes, retains originals and
  attribution, and refuses DOCTYPE and entity declarations.
- An agent may give a tentative rights or age verdict with a written basis; only the owner's
  confirmation makes it final. Ask the owner before adding a collection. Permission to use a
  collection in one project does not admit it to another.
- Review a model's training-data provenance at paper level, not only on its model card; a
  card-level check rewards non-disclosure.

Commit derived text, and keep its derivation mechanical and re-runnable, so a re-derivation from
the same bytes reproduces the corpus. Keyed questions are a separate artifact and need their own
license clearance.

Bundled corpora live only in test resources, with their licenses, notices and per-case
provenance. Their checks are robustness invariants (input hash, finite and bounded dimensions,
determinism, ink containment), not visual or specification expectations. Record human or model
review dispositions separately from standards expectations; a corpus "pass" means only that a
limited review found no obvious defect.

Sample deterministically: deduplicate normalized inputs while retaining every source occurrence,
stratify, then select round-robin across strata in seeded SHA-256 order. Record IDs, source-file
hashes, item indices, license, dataset release and transformations, and report input-limit
exclusions and shortfalls explicitly. Start with a bounded subset when the importer holds
candidates in memory.
