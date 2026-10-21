# OS and model drift

These mechanisms and lessons apply when the stated capability is present. Original
measurements establish their recorded platform and workload; they do not establish
universal behavior on later operating systems or in a different application.

This is the protocol for measuring behavior that the OS owns: on-device and server models, and
framework output such as OCR. Collection and receipts are in [evidence](evidence.md); model
statistics are in [model evaluation](model-evaluation.md).

## Fresh baselines per OS build

Platform models and OS-owned framework output cannot be pinned. On-device models are rebuilt
with OS releases and server models change on their own schedule, without announcement, so the
same code, corpus and thresholds give different numbers after an update. Between macOS 26 and
27, with no code change, one measured leak rate fell from about 29% to 0% and a new empty-answer
failure mode appeared.

- Establish a fresh baseline per OS build and compare within it. A configuration change made
  together with an OS change leaves two variables and no result.
- Record every result with its conditions: OS and model build, toolchain, backend, trials,
  retrieval depth, index, template, thresholds and options. Turning an option on is a different
  configuration, not a better number for the same one. Compare two records by diffing their
  sorted JSON:

  ```sh
  diff <(jq -S . A.jsonl) <(jq -S . B.jsonl)
  ```

- Run deterministic stages first. They generate nothing and run on any Mac, whatever its OS.
- Print coverage beside every rate. Mark a partial generative run void (for example, more than a
  quarter of rows without a verdict, or nothing produced) or thin (under half of attempts
  produced anything) instead of letting it read as a pass.
- Confirm the model route with a served positive control before attributing a change to the
  model; see [inference and evidence](../knowledge/ml/inference-and-evidence.md).
- Generative measurements run deliberately at the triggers below and are not build gates; see
  [model evaluation](model-evaluation.md).

## Triggers and tiers

| Trigger | Run |
| --- | --- |
| Every push | Tier 0 |
| Each OS beta | Tiers 0 and 1 |
| Each OS release, and a point release that ships a model update | Tiers 0, 1 and 2 |
| A toolchain change | Tier 0, plus a build with both toolchains |
| A server model | Tier 3 on a clock, and at once when its output looks different |

- **Tier 0, deterministic gates**: unit tests and deterministic retrieval and rule checks, with
  no model, network or metered allotment. A red Tier 0 is a hard stop; nothing below it means
  anything until it passes.
- **Tier 1, the tripwire**: the shipping configuration on device, multi-trial. Re-read the
  context budget too, because the context window and tokenizer are OS-owned and both move. A
  Tier 1 run needs the machine's model to itself.
- **Tier 2, recalibration**: re-derive threshold sweeps and the floors they rest on when Tier 1
  moves or on a release. Thresholds fitted to one model's score distribution are not
  automatically right for the next.
- **Tier 3, the metered or server tier**: Tier 1's shape against the server path. A server model
  has no version to watch, so it gets a clock, at a cadence the project chooses for cost, plus a
  run whenever its output looks different. A format habit can move numbers far: a server tier's
  fenced JSON envelope put one over-refusal rate about 59 points away from the on-device tier's.
  No change over time was observed under a fixed configuration on the recorded builds.

When an OS seed and a toolchain update land together, wait for both and measure once.

## Gate versus inform

Gate what the project controls and what is safety-critical; inform on what the platform controls
or what is still immature. A gate that is always red gets ignored, and one that is always green
detects nothing.

- Enforce bars on the target OS. A run on an older OS prints the same verdict as advisory, and a
  run whose OS was not recorded is enforced, never waived.
- Gate coverage alongside the rates it qualifies; a rate over a truncated run is vacuous.
- A gated measurement missing from a run fails it. Name the suite on the command line and never
  infer it from the artifact: the wrong suite fails as missing, and an unknown suite is an
  error. A partial run is read only for the gates it covers and must not pass by omission.
- Keep bars in one machine-checked file applied to recorded runs. The artifact never selects its
  own bars, and a copy in prose or another file is not a second source. Derive a perturbation
  test of every bar, in both directions, from that file, so a new bar is covered when it lands.
- Bars do not travel across corpus, tier, backend, verifier or transport. Scope each bar by
  them, so a run with another configuration reads missing instead of certifying against it, and
  never pool arms across an unmeasured transport difference.
- An informational metric becomes a bar only under a new policy version declared before the
  round that evaluates it.

Inform on latency shifts (unless the product becomes unusable), score bands drifting toward a
bar (the early warning that recalibration is due), new failure modes in the fallback
composition, server latency and quota behavior, and platform-owned safety layers: a build should
not fail because the OS grew more cautious. Count a decline as data and an environment failure
as an absence.

## Supported means measured

Record, per release, the OS versions each tier actually ran on, not the versions the manifest
permits. A version nobody measured is untested.

Derive a bar on the platform where it is enforced. A bar imported from another OS fails for a
platform difference rather than a defect: answer-correctness bars set just below figures
measured on macOS 26 failed the first macOS 27 baseline while every safety gate passed, because
the newer model declined more and cited more. Measure the platform first, then set the bar. A
bar set before its platform can be measured, or measured on a design too small to hold it, is
marked provisional, names what would sharpen it and is enforced exactly like any other.

## OS-owned values in deterministic gates

A deterministic gate can contain OS-owned output that is deterministic in its code and not in
its output. On macOS 27.0 (26A428), `RecognizeDocumentsRequest` read one page in several
distinct, individually stable ways from run to run with no source or product change, and each
reading moved downstream ranks and metrics (September 2026; details in
[framework execution identity](../knowledge/apple/framework-execution-identity.md)). An
authority that records one observation fails whichever run meets another, and regenerating it
only moves which run fails.

Treat each OS-owned value by whether it moves a measured outcome:

- **A value that moves outcomes is a declared state.** The authority holds the stable half equal
  to its frozen capture and declares every observed state from real captures. A capture passes
  when its OS-owned projection equals one declared state and fails on any other, naming the
  undeclared state's content-derived identifier. A red run on an unchanged tree is a new state,
  not a regression: confirm that the stable half passed, then rewrite the authority create-only
  from captures that include the new state. A state seen once and not since is latent, not gone.
- **OS-rendered bytes that move no outcome are recorded, not compared**, while their stable
  counterpart is still compared. Comparing them makes gates report stale receipts on an
  unchanged tree each time the OS redraws.
- **The host's OS version and build** say which build a record was qualified on. Compare them on
  the recorded build. On any other build compare every outcome and print a skipped-identity line
  that the lane summary repeats, so the skip is read rather than passed silently. Refuse a
  record or capture that omits its host identity. Do not keep one record per host build: every
  OS update would then need a new record to compare an identity that moves no outcome.

Evidence: [studywright measurements/audits/generalization-table-form-ocr-counterfactual-v4.json](https://github.com/vocaro/studywright/blob/f1d1178e03949b2a6fb20dc6d85618988c0d01b2/measurements/audits/generalization-table-form-ocr-counterfactual-v4.json).
