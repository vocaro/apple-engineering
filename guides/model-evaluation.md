# Model evaluation

These mechanisms and lessons apply when the stated capability is present. Original measurements
establish their recorded platform and workload; they do not establish universal behavior on
later operating systems or in a different application.

This guide covers measuring generated answers, model judges, structured generation and embedding
retrieval. Observed FoundationModels and Private Cloud Compute (PCC) behavior is in
[FoundationModels and Private Cloud Compute](../knowledge/ml/foundation-models.md),
prompt-injection methods are in [prompt-injection
measurement](../knowledge/ml/prompt-injection-measurement.md), the drift protocol is in [OS and
model drift](os-drift.md), and device hosting is in [device testing](device-testing.md).
Numbers quoted as examples come from on-device and PCC runs on macOS 27.0 builds, July to
October 2026; they illustrate the methods and are not platform constants.

## Vocabulary

An **item** is one keyed question, probe or input, and it is the unit of replication. A
**trial** is one draw of one item. An **attempt** is a trial the harness dispatched. An **arm**
is one configuration (model route, prompt, checker, retrieval options) run over one fixture. A
**fixture** is the committed set of items with its keys.

Every attempt ends in exactly one of these outcomes:

- **Answer**: the model returned non-empty text or a decoded structured value that is not
  refusal-shaped.
- **Refusal-shaped response**: non-empty text whose normalized form is one of a closed list of
  declining forms (below).
- **Typed refusal**: the framework threw a refusal error (FoundationModels `refusal`).
- **Safety-filter stop**: the platform's safety layer stopped the generation (FoundationModels
  `guardrailViolation`).
- **Empty generation**: the framework ended without content (FoundationModels: a parsing error
  whose raw content is empty).
- **Context overflow**: the prompt or the generation exceeded the context window.
- **Environment failure**: a rate limit, quota refusal, unavailable model, untyped failure or a
  host the OS moved to the background. The attempt reached no model decision and is unmeasured,
  in the outcome vocabulary of [evidence](evidence.md).

An answer or a refusal-shaped response is a **response**. A **refusal marker** count, a broader
list of declining phrases found among wrong answers, is a diagnostic. It never redefines any
outcome above. Keep each typed code even when the app maps several of them to one fallback.

Three coverage quantities share one denominator, attempts:

- **Reach**: attempts with a model outcome (everything except environment failure). A model that
  declines or is stopped is data; an environment that fails is absence.
- **Coverage**: responses over attempts. Unqualified, "coverage" in these documents means this.
- **Answered**: answers over attempts.

Answered ≤ coverage ≤ reach on every arm by construction; a computation that reports otherwise
is wrong and must not be published. Never count an environment failure, or a fallback the app
substituted for a model answer, as a response: a harness that does so reads full coverage over
items with no generations at all.

A refusal-shaped response is decided mechanically. Lowercase the text, drop every character that
is not a letter or a space, collapse whitespace and trim, then match the result exactly against
the closed list (for example `dont know`, `do not know`, `i dont know`, `i do not know`). Keep
the list tiny and exact: it holds the forms the models were observed to emit, and a wider or
heuristic rule reclassifies real short answers such as "Twenty-seven (27) [1]." Extend it only
by a documented amendment that quotes the newly observed strings; never loosen it into a
classifier.

## Deterministic checks gate; model qualification informs

Gate what the project controls and what is safety-critical, using checks that need no model:
fixture self-checks, span-keyed retrieval, reference answers scored through the grounding or
correctness check, and exact calibration replays. They are fast, replayable on any OS and fit a
pre-push hook.

Generative measurements are slow, nondeterministic and need a served model. Run them
deliberately, per OS seed and whenever prompts, chunking, retrieval, thresholds or the checker
change. They qualify and inform; they are not build gates, and their app-hosted execution does
not make them push gates. A green unit suite is not evidence that any of them ran.

Metrics the platform owns, such as latency, quota behavior and safety-filter exposure, inform
rather than gate: a build that fails because the OS's safety layer grew more cautious fails for
something no commit can fix. The trigger, tier and gate-versus-inform policy is in [OS and model
drift](os-drift.md).

## Deterministic stages come first

Score the corpus's own known-correct answers against the passages retrieved for their questions,
with no generation, alongside synthetic fabrication probes. This separates "the check is
mis-calibrated" from "the model is wrong" in seconds. Score each surface bare and framed (behind
"According to the material,"), and fail the run when a probe rejected bare survives framed.
Count checker failures as their own rate beside the verdicts; never drop them.

Make threshold sweeps exact: one pass that records every input the decision rule consumes lets
the rule replay arithmetically over any threshold grid, so a candidate checkpoint or threshold
pair is priced without another model call. A candidate still behind at its own optimum is
settled cheaply.

Measure at the product's k and with the product's retrieval options; turning an option on is a
different configuration, not a better number for the same one. Before any device or metered run,
score retrieval for the exact input and keys. A run whose keyed spans are not retrieved measures
retrieval, not generation.

## Positive controls and the shipped path

Open every generative run with a positive control that must produce on the intended route: a
short text request with a one-word answer. Availability flags, model listings and a configured
entitlement are not positive controls. A failed required control voids the run. A control proves
only its own route and quota pool; see [FoundationModels and Private Cloud
Compute](../knowledge/ml/foundation-models.md).

Measure the shipped path. Drive the product's own composition (its factory, prompt, retrieval,
checks and fallbacks) rather than a re-implementation in the harness: a boundary re-implemented
in a harness is a different program. An ad hoc harness prompt once produced no free text in 40
tries where the shipped template produced 8 of 12. Obtain every suite's backend from the one
factory that honors the backend selection; a suite that constructs a backend directly cannot see
the shipped tier.

A fail-open path needs a loud capability probe. A query expander that returns the original query
when structured generation fails reports "nothing expanded", a plausible negative result, on a
backend that cannot generate structured output at all. Probe the capability once and fail the
suite when it is missing.

Observe a fail-closed check without changing the measured configuration. Wrap the checker in a
transparent recorder that sees each candidate text and verdict before the fail-closed path
replaces it, and passes the verdict through unchanged. A unit test proves a predicate; only a
product-path run proves the product asks it. A zero-cost audit over every served answer (for
example, a question-echo check that must read zero) proves the wiring.

## Predeclaration

Before the first generation, commit the fixture and scorer identities with their digests, the
prompt template's identity and content digest, the artifact identity, the trial count, the bars
and their sidedness, the route and transport, the call ceiling, the stop rules, the
denominators, the controlled-context keys a replicate must match, the expected design effect and
the decision rule. A route or transport change starts a new baseline; results from the old route
do not qualify the new producer.

- Commit the gold set before any model runs. Its labels are the divisor.
- Freeze keys before computing any rank. Sample key slots by a deterministic stratified rule
  over the eligible passages (slot *i* of *n* takes passage ⌊(*i* + 0.5)·*N*/*n*⌋), have the
  author write each question in their own words with a verbatim retrieval span, and keep the
  hard slots. A requalification after a product change uses a new key set sampled at a different
  offset.
- Hold out whole sources. Fit on a calibration partition, evaluate frozen candidate identities
  on validation against a no-filter control, and keep the test partition closed until
  replication and a predeclared decision rule exist.
- Record every selector that narrows a fixture (a class, a list of item ids) in the record's
  context, so a subset is never read as a class rate. Refuse unknown ids rather than narrowing
  quietly.
- Reject unknown or incoherent record schemas. Results scored under different scorer schemas or
  rule vocabularies never form a delta.
- Fork paired policy arms from one shared sample, such as the same observed failure, rather than
  from two independent draws. Alternate which arm runs first, fix the sample size, and allow no
  outcome-dependent stop or top-up. Give both arms equal analytical allowance without spending
  dummy calls.

## Call plans and budgets

Derive a hard call ceiling from the committed fixtures before the first call, without building,
generating or reading quota state. The ceiling is the logical calls (controls plus items ×
trials × calls per trial) plus a bounded retry reserve, for example 10% rounded up. Meter
physical calls and refuse any call past the ceiling. Let every raw row carry its own attempt and
judge counts, so a stopped run's spend can be recovered from its rows.

- **Count retries.** A generator that retries a rejected candidate up to three times costs all
  three exactly when candidates are failing. When only each item's last rejection is reported,
  *n* failing items is neither *n* attempts nor *n* failures of one kind.
- **Count multipliers.** A judge per answer doubles a run; scoring three answer surfaces triples
  it.
- **A reservation is not a call.** Journal a reservation and a terminal result around each call.
  An interrupted reservation carries an explicit lower and upper call bound, never a fabricated
  served or failed count.
- **Test the plan.** A dry run over a backend that rejects every call with the retryable empty
  generation must land exactly on the ceiling.
- **Fit a budget by dropping items, never trials.** A candidate arm is readable only against a
  baseline at the same trial count.
- **Order the queue decision-critical first.** A quota refusal lands mid-run without warning:
  the first run has a result and the next is void. "Control first" means the arm not already in
  hand; when a complete control is archived, the owed arm goes first.
- **A partial arm is void, not a discount.** Items run in fixture order, so an early stop prints
  complete-looking rates for early classes and nothing for later ones. Mark it incomplete,
  compute rates over produced trials only, and retain it under a void name.
- **Record the session's total metered spend in the commit**, including probes and diagnostics.

Budget from the measured per-call cost of this corpus and route, not one smoke figure. On-device
latency scales with prompt length: about 3.2 s per call for a short retrieval prompt against
11.6 s for a ~2,000-token prompt on macOS 27.0 betas (July–August 2026), so budgeting the long
corpus at a ~2.9 s smoke-test figure under-reserves it fourfold.

Per-job rates from short spans are not scheduling keys. On one phone, rates from ~25-row jobs
moved in both directions by large factors when re-measured over 48–104 rows, and the spread did
not collapse. Budget from row counts and a wide rate band, re-derive rather than extrapolate
when the trial count changes, and state the ordering key in the receipt. Derive a rate from the
span of a job's row timestamps, never from queue-state update gaps, which include scoring time.
Treat an overrun as variance until the job's logged per-call latencies are summed against its
span. A per-job timeout inherited from a shorter arm fails jobs on volume alone when trials
increase. When a harness emits rows only at job end, a slow job and a nearly finished one look
identical; do not diagnose an overrun before the job lands.

Wall-clock results are stamped as they happen: a filled result looks the same however long it
took. Report "not reached" with what was produced when a deadline arrives, never a number the
run did not get. One run of one input is an observation, not a rate. Sustained on-device
inference slowed about twofold over ~15 minutes and stayed slow into the next run on macOS 27.0
betas, so compare arms by counts or leave the machine idle between them, and take a process
listing during the run.

## Stop rules

A run stops at the first trial boundary after any of these:

- a quota refusal;
- a rate limit that outlasts the declared pacing and backoff;
- an unavailable primary model;
- an untyped generation failure;
- a generation served on a route other than the declared one;
- the call ceiling;
- loss of foreground, or a row that could not be persisted.

A stopped run keeps its raw rows, writes no aggregate and is not evidence. No retry, resumption
or replacement draw follows until the stop is diagnosed. Resume only from a validated prefix:
recompute the next coordinate, the spend and the failure clusters from the retained rows, and
reject reordered work, invalid terminal rows or changed input hashes. Never resume from an
offset supplied by hand.

Retry only the known retryable fault, the typed empty generation, a bounded number of times per
call and from the declared reserve. Never retry a decline, a judge failure or a safety-filter
stop. On a quota refusal, stop: do not poll for returning capacity and do not schedule a quota
retry.

Watch the harness's own stop marker. A platform log can print a refusal line for every refusal,
including the ones a pacer retries successfully. A served output the scorer cannot classify,
such as a new wording of a supported answer, is recorded for review before the bar is read; it
does not stop the run.

## Same-session and null controls

Run the control arm in the same session as the candidate and never substitute an archived one.
An archive can differ in OS build, in fixture, and in whether it carries per-item rows at all. A
shipped prompt re-measured in session read 4.6% over-refusal against its archived record's
26.5%; differencing a candidate against the archive would have credited the candidate with the
archive going stale.

Byte-identical arms still differ by sampling. Read such a difference as sampling, not treatment,
and keep both artifacts so the equality premise stays auditable.

Run both arms in one process, interleaved per item, alternating which arm leads, because a long
on-device run drifts. Carry a null control: items the treatment does not change run a
byte-identical prompt on both arms, so any difference there is the harness's own noise. In one
reranking comparison the null subset moved +9.1 points against +5.5 on the subset reranking
changed; the floor exceeded the effect. For a retrieval change, also assert the invariant that
makes adoption safe (for example, recall at every k at or beyond the rerank depth is
bit-identical between arms).

An arm's identity includes every input that can move its result: the index and its digest, the
extraction arm, the chunk count, k, and the selection fraction (effective k over chunk count). A
source exposed entirely at the product k proves that keys survive extraction, not that ranking
discriminates. Paired deltas survive a stale index because both arms score the same one;
absolute figures do not. Do not compare across OS builds; establish a fresh baseline per build
([OS and model drift](os-drift.md)).

## Paired comparisons

Pair two arms from per-item rows retained in the artifacts, never from aggregates or scrollback:
a rate cannot be un-averaged. Refuse to pair, rather than report "no disagreements", when:

- either record has no per-item rows;
- the corpus or item-set identity differs (index, index digest, fixture and fixture digest must
  be equal, or absent from both records), or a key the replicate declared as controlled is
  missing or unequal;
- the arms did not do comparable work: the lower response coverage is under 0.9 of the higher
  (min/max < 0.9). The tolerance admits a trial or two lost to empty generation; it refuses a
  truncated arm whose zeros are absence, not agreement.

Waive a context key only by naming it. Declare a replicate's controlled keys explicitly (route,
index and digest, fixture and digest, k, trials, prompt digest, checker, OS and build) instead
of relying on inspection.

Read the discordant counts and an exact two-sided McNemar p before any rate; only the items on
which the arms disagree carry information. A paired arm's sample size is its discordant count,
not its row count. With every discordance in one direction, five give a p of 0.0625 and six a p
of 0.031, so fewer than about six discordant items cannot reach p < 0.05 however many rows were
collected. Trials past the first per item buy precision on that item, not replication: power a
comparison with more items, a second device or an independent session. One discordant pair is a
point estimate; an adoption condition met in form by 1 against 0 is a null result.

Power the design before running it. Compute the smallest detectable change against the baseline
rate of the corpus and check actually being run: 160 trials per arm detect only a ~5.7-point
change in a rate near 1%. A zero-event arm gives a rule-of-three ceiling (0 of 64 bounds the
rate at ≤ 4.7%), never a parity claim. An unresolved interval is not parity, and an underpowered
null is not evidence of no effect. On saturating sets, read median gold rank beside hit@k: hit@k
stops moving long before the ranking does.

## Clustering and variance

Trials of one item are correlated. The design effect is 1 + (*m* − 1)·ICC for *m* trials per
item, and the effective sample is attempts divided by the design effect. At 32 items × 3 trials
and ICC 0.72–0.75, 96 attempts are an effective ~38, and the smallest change detectable at 80%
power is about 24 points: a few points between two such runs is not a result in either
direction. Concentration matters as much as the mean. When 3 of 20 items carry every conversion,
a ~3× design effect turns a per-attempt p of 0.0002 into about 0.02–0.07.

Quote an item-clustered test, never the per-trial one. A simple exact rule: per item, take the
sign of the difference between arms, drop ties, and apply the exact sign test. One arm read a p
of 0.09 per trial and 0.375 clustered.

Run-to-run variance is usually the larger axis on-device, and no within-run p sees it. One
on-device configuration drawn three times read 31.7%, 64.1% and 50.0% over-refusal on the same
fixture; two PCC draws of the same arm moved every quoted figure by at most 6.2 points. A single
run of a generative arm is not quotable: run the same arm twice before quoting either p. A
cross-tier comparison inherits the noisier tier's spread, so two tight draws outside a wide
range do not establish a tier gap. Variance belongs to an arm, not to a tier: an arm whose
answers restate their source reproduced to a tenth of a point while its conversational sibling
moved 15 points.

Aggregates cannot be paired and cannot support a bar. A replicate can match the rate and still
disagree on the fitted bar, because the spread estimate rests on the few items that convert;
compare per-item vectors, not aggregates. Keep the per-item rows, the per-trial outcomes with
their text, and the run log next to each record.

Keep statistics parity fixtures that two independent implementations recompute, for example the
Swift harness and scipy, for McNemar, Fisher and percentile cases. Percentile tie conventions
differ between implementations (nearest rank against numpy's ties-to-even); pin which one a
descriptive statistic uses.

## Denominators

Name the denominator with every rate: per attempt, per response, or per question asked.

Read coverage before any rate, because a prompt can move it. A rate over responses improves when
the model goes silent more often: in one arm, answers served verified and cited over answerable
attempts fell from 90.6% to 80.6% while per-response over-refusal appeared to improve. Report
the per-attempt complement beside the per-response rate and read them together. The per-attempt
form is often the steadier, because silence and conversions trade off inside a fixed
denominator.

Tier and cross-configuration claims cite answered, never coverage alone. Coverage is not
tier-neutral: a tier that emits an empty string on an ungrounded question loses coverage, while
a tier that emits "Don't know." keeps it, for identical grounding. On one keyed fixture,
coverage ranked PCC ahead in every pairing and answered ranked the on-device model ahead in
every pairing. A tier-gap claim that quotes coverage without answered is inadmissible.

- **Safety-filter stops are read apart.** Compute coverage over the attempts the platform's
  safety filter did not stop, and give the stop rate its own clause (for example, injected stops
  at most 10 points above clean). Counting a platform stop as the app's silence fails a clause
  the app cannot affect; ignoring it lets an attack that provokes the filter pass.
- **Multi-turn rates name the turn.** A failed first turn leaves the second unasked. Rates per
  attempt, per ask and per produced answer coincide only when every first turn answered.
- **Citation denominators differ.** Answer coverage divides by attempts. Citation presence
  divides cited by cited plus uncited assertions in generated answers. Citation precision
  (faithful, misattributed, unsupported) is exhaustive only within cited assertions. Never quote
  precision without generated-answer coverage: one faithful assertion can rest on one generated
  answer in 243 attempts.
- **A denominator exists only when its field was recorded.** Unobserved is not zero. A legacy
  summary's zero counter does not establish a field its schema never recorded.
- **Correctness and trust tier are separate axes.** An answer served at a lower trust tier is
  not therefore wrong. Refusal-marker counts are a mechanical subset of incorrect answers, not
  adjudication, and an empty generation is not a refusal.
- **Summarize per source, never weighted by attempts.** Give each complete source equal weight
  within its material profile, and each profile equal weight in the summary, so no volume from
  one source masks another's failure. Completeness (comparable and auditable) is not passing.
- **Clusters are inventory.** Cross-artifact totals and per-shape clusters describe; they never
  select a threshold or form a gate. Never pool heterogeneous arms, tiers or transports.
- **A zero needs its events.** A leak rate of zero over no marked answers and a zero over twenty
  differ; print the event count beside the rate.

## Fitted regression bars

A gate guards one direction, its failure direction. A floor guards a metric that should be high
(correctness, coverage, answered, yield) and a ceiling one that should be low (over-refusal,
leaks, misattribution). No gate is a band. Compute the opposite bound too and report a result
beyond it as a non-gating anomaly flag: an out-of-band good result signals an instrument defect,
such as a broken join, a leaked key, the wrong denominator or a fixture that got easier.
Investigate it; it never blocks and never becomes a bar. Predeclare each metric's direction, the
multiplier (z = 1.96 here, kept for comparability) and the anomaly flag before the data exists;
choosing sidedness after seeing the tail is choosing a bar from the result.

Fit a bar as an item-level bound over item clusters:

- Take each cluster's rate over the trials it produced, not over attempts. Under attempts, an
  item that generated nothing scores a clean zero and tightens the bar, which rewards silence.
  An item that produced nothing has no rate on that axis; it leaves the mean and spread, and the
  derivation names it as omitted.
- Bound at mean + z·SE (a ceiling) or mean − z·SE (a floor), with SE from the cluster spread
  over √*n*, where *n* is the item count a future arm averages, and round outward.
- Fit on two arms where available, pooling both arms' clusters for the spread while keeping one
  arm's √*n*: one arm's spread rests on the two or three clusters that convert. Fewer than two
  remaining cluster rates derive no bar.

The fitted tolerance is the gate, with no second selection step; that is what makes it a bar
rather than a number someone liked. Its meaning is regression protection: the system still
behaves as it did when the bar was fitted. It is not a quality claim, and its rationale says so.
Whether the measured level is good enough is a product decision.

- A metric whose fitted floor rounds to zero gets no gate, with the reason recorded: a zero
  floor passes a total regression. A bar no run can satisfy is the mirror defect. A permanently
  red gate gets ignored as surely as a permanently green one gets trusted.
- Hold a metric back from gating, and flag it, when it trips the anomaly flag or a half-width
  guard: z·SE under 1 point flaps on ordinary noise, and over 15 points protects almost nothing
  and signals too few clusters.
- Never fit a bar on the results that motivated the metric. Derivation arms never qualify the
  configuration they fitted. A later complete arm, predeclared after the bars land, is judged
  against them and never refits them. A new OS build, or a change to the scoring rules, owes a
  new predeclared pair.

Scoping bars by corpus, tier, checker and transport, gating coverage beside the rates it
qualifies, and deriving a bar on the platform that enforces it are in [OS and model
drift](os-drift.md).

## Scoring

Key retrieval by a text span the grounding passage must contain, never by chunk id, so
re-chunking cannot invalidate a key and one key scores every retrieval mode and producer. Report
keys never extracted separately from keys ranked badly.

Score answer correctness lexically as a floor: an answer is correct when enough accept-groups
have a variant present, token-bounded, with light stemming on both sides. The floor is
deterministic, replays across OS releases and avoids a model grading a model. Add a variant only
when an answer is correct and grounded in the corpus, never because a model produced it, and
re-derive keys from the corpus in tests. A model judge is not the correctness scorer: it answers
a grounding question, a same-tier judge would grade itself, and it costs a call per row. Use a
judge on the classes lexical rules cannot see, with the key withheld from its prompt, its
failures counted, controls in the same run and the deterministic arm paired beside it. Humans
write keys and adjudicate disagreements; they never score runs.

Probe design makes the numbers mean anything, and its self-checks run on every test pass with no
model:

- A leak marker is lowercase and absent from the corpus and from its own question, so a refusal
  or an echo can never score as a leak.
- Every answerable probe carries a span present in the corpus and retrieves it at the
  measurement's k, so over-refusal is a grounding signal and not a retrieval miss. A retrieved
  span does not prove the retrieved context answers the question.

Read the cause before the score. Rules have a precedence: an unsupported numeral fails a
sentence outright, so a digit swap that cosine similarity cannot see surfaces at a high score,
and reading the score first sends a diagnosis after the wrong defect. Test the cause
classification both ways; a wrong cause is a wrong diagnosis with a number attached.

- **Compare against the degenerate strategy**, such as answering the majority class to
  everything, not only against the baseline.
- **A collapsed arm needs a second rubric arm.** One degenerate arm cannot distinguish a model's
  limit from a rubric's.
- **Price a family of deterministic rules in both directions.** Target corpora supply failures a
  rule must reject; price corpora supply correct answers it must not break. A checker is one
  rule for every input, so admissibility is a property of the intersection of targets: a sweep
  can falsify a rule but never confirm one. Commit negative results, and fail the measurement
  when a member becomes admissible so the policy it would change is reopened.
- **Calibrate a classifier in both directions** so the margin, not a crossing, fails the test. A
  sweep refuses to run without the corpus that binds it, and declared scope limits are asserted
  as non-detections.
- **A changed check scopes its own requalification.** Before any generation, replay retained
  outputs through the check at both revisions, with a positive control on the text it reads
  differently, and requalify only what moves.
- **Mechanical membership is not key correctness.** A repaired structured answer that names a
  valid option is not thereby the right option.

## Human reading

Three roles stay separate: the person who drafts keys, the reviewer who confirms each gold
answer against its source, and the reader who reads model answers against the keys. A checker
validates identities, digests and joins; it does not establish that a gold answer is true.

Read every retained answer against its key and gold span, one verdict per item × trial: correct
(it gives the keyed answer), wrong (it asserts another answer, or claims the material does not
say what it says) or declined (a grounded fallback, or a declining reply without an asserted
answer). Bind the reading to the raw record and keys by digest, name its reviewer, method and
date, and attach a note to every verdict that differs from the lexical matcher. Lexical matchers
err in both directions, so floors are judged on the reading. A genuinely disputable verdict
takes the stricter reading. When it decides a bar, the owner rules, and the ruling or the
owner's delegation is recorded in the row's note and in the commit that applies it.

Raw rows keep correctness unset until read; an in-run scoring callback is not an independent
reading. Read rescued answers verbatim, never by their count: in one comparison 48% of what a
change rescued into the cited tier was a refusal or a non-answer. Dump every trial's text for a
candidate arm; a dump that prints only when a rule fires leaves no text behind the arm that
appears improved ([prompt-injection
measurement](../knowledge/ml/prompt-injection-measurement.md)).
