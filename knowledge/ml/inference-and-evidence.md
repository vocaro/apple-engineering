# Inference and evidence

These mechanisms and lessons apply when the stated capability is present. Original measurements
establish their recorded platform and workload; they do not establish universal behavior on
later operating systems or in a different application.

## Inference availability must be tested through the real execution path

An entitled signed app, a command-line process, a test runner and a simulator can reach
different models. A restricted entitlement works only inside a bundle whose profile authorizes
it, so a bare executable or a test hosted by Apple's `xctest` never reaches the entitled route
at any signing effort, and a simulator's model is its host Mac's. An unentitled call can fail
with an untyped error while availability and quota metadata read healthy. Availability flags,
model listings and a configured entitlement are therefore not evidence of served inference: only
a generation served through the intended route is, and a successful control must use that route.
Measure the shipped path before concluding a tier cannot do something; an invented harness
prompt can fail where the product's own prompt succeeds.

Preserve typed errors before an `NSError` bridge empties their payloads, and keep the outcomes
distinct: empty generation, rate limit, quota refusal, safety-filter stop, typed refusal and
context overflow. Rate limiting and quota refusal are distinguishable only on some routes and
builds. On macOS 27.0 26A428 the app tier's per-device rate limit arrived typed as a quota
refusal; on the 26A5416b beta a prolonged app-tier block arrived typed as a rate limit while
quota metadata read healthy; and the `fm serve` transport folds every refusal string into one
outcome. Record the build with every refusal and read the typed error, not a mapped category.
The observations, error table and quota signals are in [FoundationModels and Private Cloud
Compute](foundation-models.md). How much a project may spend on a metered tier is the owning
project's decision.

## Retrieval, attribution and truth are different checks

Factual assessment and source attribution answer different questions. A passage can faithfully
support an outdated claim, and a correct adjacent claim can have no supporting passage in the
imported material. Retrieval similarity, source repetition, a generator's stated confidence and
agreement among repeated generations establish neither factual correctness nor citation
entailment. Agreement across draws cannot separate a stable answer from a stable mistake: a
three-trial majority-vote judge bought no defense over one trial at three times the calls, so
repeated draws stay a measurement tool, not a runtime confidence signal.

- **Attribution is claim-specific.** Give every substantive claim an identity and an origin
  (from the material, or additional context). A separate check binds the exact claim text to the
  exact passage number and text it cites, and a changed claim or passage needs another check. A
  citation the generator was asked to produce is not such a check.
- **Citation markers come from validated claim-to-passage edges**, never from numeric brackets
  in free text. Unknown, empty or invalid passage references fail structural review.
- **A source-conflict report is a report.** A claim that states what the material says does not
  assert that the material is right; an unresolved apparent conflict belongs in uncertainty
  review, not in an established-conflict category.
- **Structural validity is not semantic qualification.** A validator checks that the fields are
  present and consistent, not that reasons are adequate or the rendering accessible.
- **A grounding verdict is not an injection verdict.** An answer that repeats an injected
  sentence is grounded by construction, because the sentence is in the passage. Never word a
  grounded verdict as a safety verdict, and do not loosen the checker so injected spans stop
  counting as support; see [prompt-injection measurement](prompt-injection-measurement.md).

Several of these structures were experimental and uncalibrated when recorded; their contracts
describe representation boundaries, not shipped or calibrated factual verification.

## Admitted conversation history validates its own claims

Admitting the conversation transcript as grounding evidence makes every earlier claim
self-supporting: a restatement is supported by construction against a transcript that contains
it. In an August 2026 replay with the transcript admitted, 32 of 32 answers the shipped
grounding check had rejected were served as cited, and per-sentence source classes did not
repair it, because every non-similarity signal reads the evidence as a bag of text. Keep
conversation history as prompt context only and verify against the retrieved material alone. A
native `LanguageModelSession` transcript has the same shape and also grows past small context
windows ([FoundationModels and Private Cloud Compute](foundation-models.md)).

## An independent check is defined by what it could see

Independence means separation of information and process. Another call to the same model is a
correlated signal, not an independent truth oracle. Shown the retrieved passages, both Apple
tiers (on-device and PCC, macOS 27.0 beta 26A5425a, September 2026) judged whether a passage
supports a claim instead of whether the claim is true, so a factual check sees the claim
identities and exact claim texts only, never the retrieved passages and never the generator's
draft. Even then it licenses a category only through held-out calibration.

Each check protocol records the generator, the check method and the information available to it,
the stability trial count, the tier, source shape, knowledge origin, exact prompt and
implementation identities, expected calls and stopping rules. Missing, failed or contradictory
checks stay explicit observations; they never count as agreement.

| Observation | What it can establish | What it cannot establish alone |
| --- | --- | --- |
| Claim-to-passage check | Whether the material supports the claim | Whether the claim is factually right |
| Independent factual check | Agreement with the claim under its declared method | Calibrated correctness from one agreement |
| Answer stability | Consistency across predeclared draws | Truth of a consistently repeated error |
| Source-conflict check | Whether the source report and the factual assessment disagree | Which side is right, without factual adjudication |
| Held-out outcomes | Reliability and coverage of a frozen policy in its tested conditions | Transfer to an unmeasured tier, source shape or origin |

## Calibrate a factual policy on held-out sources

Hold out whole sources, and separate development, calibration and final acceptance. Include
supported claims, correct adjacent claims, established and unresolved conflicts, plausible wrong
claims and answerable cases that invite over-refusal. Adjudicate factual correctness,
attribution correctness and ambiguity independently, and resolve disagreements before scores
carry authority. The generator never supplies its own answer key. Before final acceptance opens,
freeze the category rules, risk bars, minimum coverage, uncertainty limits, source partitions
and any escalation budget.

Report denominators, generated and served coverage, wrong confident answers, falsely supporting
citations, correct answers withheld or unnecessarily labeled, the quality of tentative answers,
and conflicts assessed correctly. Report every tier, source shape and origin separately, so
pooled success cannot hide a failing group. The general methods for pairing, clustering and bars
are in [model evaluation](../../guides/model-evaluation.md).
