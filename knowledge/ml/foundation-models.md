# FoundationModels and Private Cloud Compute

These mechanisms and lessons apply when the stated capability is present. Original measurements
establish their recorded platform and workload; they do not establish universal behavior on
later operating systems or in a different application.

Observed behavior of Apple's FoundationModels framework, its on-device model
(`SystemLanguageModel`), Private Cloud Compute (`PrivateCloudComputeLanguageModel`, PCC) and the
`fm` developer tool. Each observation names its build: macOS 27.0 betas 26A5388g through
26A5425a (July to September 2026), macOS 27.0 26A428, macOS 27.2 26B5091g, iPadOS 27.0 24A435,
iPadOS 27.2 24B5099f, the iOS 27.1 Simulator 24A94401 and Xcode 27.1 27A9269. None of it is an
API contract, and much of it changed between builds. The outcome and coverage vocabulary is
defined in [model evaluation](../../guides/model-evaluation.md).

## The framework's model types are not an app's inference interface

FoundationModels exports a top-level `LanguageModel` protocol and `LanguageModelError`. The
protocol is a session-coupled executor, not a prompt-to-answer interface, and it has no uniform
availability surface. Keep Apple's models behind an app-owned inference interface with another
name, so neither the types nor their errors leak into callers:

- Pass trusted instructions (persona, grounding stance) on a channel separate from the prompt,
  so a backend can route them to its native session instructions.
- Give each model its own availability check; the on-device model and PCC report availability
  differently.
- Keep `@Generable` and `GenerationSchema` out of that interface. Describe a structured request
  with an app schema and bridge it through `DynamicGenerationSchema` behind it.
- Observe the typed error before mapping it into the app's error type, which erases the payload.
- Fail over to another model only on availability-class errors (unavailable, rate limited, quota
  refused). A context overflow cannot fit a smaller window and never falls through to one.

## Context windows are small, OS-owned and read at runtime

`contextSize` read 4,096 tokens for the on-device model on macOS 27.0 betas 26A5388g through
26A5425a, against an announced 8,192; Apple's own sources disagreed. PCC read 32,768. Read the
window with `contextSize` and prompt sizes with `tokenCount(for:)` at runtime and never hardcode
them. The window and the tokenizer both belong to the OS, so re-read the prompt budget on every
OS seed. PCC has no token counter; an on-device `tokenCount(for:)` of a PCC prompt is a labelled
proxy, not its cost.

## Private Cloud Compute needs an entitled app bundle

`com.apple.developer.private-cloud-compute` is a restricted entitlement, so a provisioning
profile must authorize it, and a profile can only be embedded in a bundle. On 26A5416b a bare
executable claiming the key was killed at launch with SIGKILL (exit 137) under both ad hoc and
Apple Development signing. `swift run` cannot reach PCC, and neither can `swift test`, whose
tests are hosted by Apple's `xctest` binary. Only an entitled app bundle reaches the app-tier
route. A production-bundle profile cannot authorize a separate measurement host bundle; a device
host needs a development profile with PCC that lists the device. Build PCC code with a full
Xcode 27: the Command Line Tools ship the same Swift, so a Swift version check passes, but they
lack `coremlcompiler` and cannot build test targets. Detect them with `xcode-select -p` and
select Xcode with `DEVELOPER_DIR`.

An unentitled process fails without naming the entitlement. It reaches `respond` and throws
`LanguageModelError` code -1 wrapping `ModelManagerServices.ModelManagerError` code 1046, while
`availability` reports available and `quotaUsage` reports `belowLimit` throughout. No pre-flight
catches it, and an app layer that maps the throw to a generic generation failure keeps reporting
a healthy route while every generation fails. Only a served generation through the intended
bundle proves the route.

## Read typed errors before they cross the NSError bridge

On OS 27 builds, bridging these failures to `NSError` left `userInfo` empty, so a diagnosis
logged through the bridge is a diagnosis discarded. Cast to the typed error and read its
payload, checking the most specific type first:

| Typed error | Payload to keep | Outcome |
| --- | --- | --- |
| `GeneratedContent.ParsingError` with empty `rawContent` | the empty raw content | empty generation |
| `GeneratedContent.ParsingError` otherwise | `rawContent` | generation failure |
| `PrivateCloudComputeLanguageModel.Error.quotaLimitReached` | `resetDate` (or its absence) | quota refusal |
| `PrivateCloudComputeLanguageModel.Error` network failure or service unavailable | | unavailable |
| `LanguageModelError.contextSizeExceeded` | `contextSize`, `tokenCount` | context overflow |
| `LanguageModelError.rateLimited` | | rate limit |
| `LanguageModelError.guardrailViolation` | | safety-filter stop |
| `LanguageModelError.refusal` | | typed refusal |
| other `LanguageModelError` cases (timeout, unsupported capability) | | generation failure |

Keep `guardrailViolation` and `refusal` distinct in records even when the app shows both as one
fallback; only the code tells them apart. On 26A428 a PCC safety-filter stop arrived as
`guardrailViolation` with the description "Response may contain sensitive or unsafe content",
not as `refusal`. Reading a deprecated error family degrades typed failures to a generic
generation failure. An over-window tool registration throws a third error family that a mapping
built for sessions does not cover.

## Empty generation is intermittent and invisible to availability

The on-device model intermittently ends without content: a `GeneratedContent.ParsingError` whose
`rawContent` is `""`, described as "Session ended without producing a response". Every
availability signal (the `fm` model listing, `availability`, capabilities) keeps reporting
healthy during the fault. The fault persisted across macOS 27.0 betas; on 26A5425a it appeared
in 4 of 320 attempts, which bounds its presence, not its rate. Retry only this fault, at most
twice per call, from a declared reserve, and open every generative run with a text control that
must produce. A failing control is not alone proof the tier is down: `fm respond` once returned
the error 6 times in 6 while the same model answered 5 of 5 through `fm serve`, so cross-check
through another route before abandoning a measurement.

## A context overflow is either a prompt that never fit or a runaway

A prompt overflow reproduces exactly; a runaway generation that runs into the window clears on
resampling (13 of 20 identical calls succeeded in one screen on a macOS 27.0 beta). Distinguish
them by the overflow margin as a share of the window, not by a token count, because the windows
differ eightfold: observed runaway margins were 1 to 3 tokens and the observed prompt overflow
was 1,069, so a boundary at 1% of the window separates them. In doubt, read runaway: a wrong
prompt reading retires the input permanently, while a wrong runaway reading costs one bounded
resample. A repeated `tokenCount` is not evidence of a prompt overflow; runaway margins took
three values and repeated about 43% of the time. The numbers survive only in the typed
`contextSizeExceeded` payload.

On-device guided generation overflowed mid-generation in about 26% of calls on macOS 27.0 betas,
identically at 230 and 370 prompt words. A response-token cap does not fix it. Interleaved
on-device screens at 512 and 1,024 maximum response tokens replaced sampled overflows with
capped generation failures and reduced decoded, valid quiz objects (12 to 10 of 20, and 7 to 5
of 20). A screen of a cap must count decoded, structurally valid objects, never "did not
overflow".

## Rate limiting and quota refusal are distinguishable only on some routes and builds

The framework types them separately: `LanguageModelError.rateLimited` and
`PrivateCloudComputeLanguageModel.Error.quotaLimitReached`, which may carry a `resetDate`.
Whether a given refusal arrives as one or the other depends on route and build:

- **macOS 27.0 beta 26A5416b, app tier.** A prolonged block arrived as `rateLimited` while
  `quotaUsage` read `belowLimit`, not approaching, with a nil `resetDate`, on all 516 reads
  across a 41-minute block. It came after 786 generations over about five hours; a separate 501
  generations in 15 minutes met no refusal. Each refusal returned in about 230 ms.
- **macOS 27.0 beta 26A5421a, app tier, 2026-08-27.** The refusal arrived as `quotaLimitReached`
  with a `resetDate`, and `isLimitReached` became true within five minutes.
- **macOS 27.0 26A428, app tier.** The refusal arrived typed `quotaLimitReached` while the
  framework log named it `deniedDueToUserDeviceRateLimit`: the log's per-device rate limit is
  the quota refusal as the app sees it. The log line is printed for every refusal, including
  ones a pacer later retried successfully. The thrown `resetDate` was present on some refusals
  and nil on others. In the retained runs on this build, a pacer's rate-limit retry never fired.
- **The `fm serve` transport.** Every refusal string ("The allotted usage quota has been
  reached.", "Your quota has been reached. Please try again later." and "The session has been
  rate limited.") arrives in an HTTP body; a client that matches on "quota" folds them into one
  rate-limited outcome. Only a direct probe of the gateway distinguishes an exhausted allowance
  from a throttle.
- **An iOS host moved to the background.** On-device calls from a host that a lock or app switch
  sent to the background returned `rateLimited` for the rest of the run (iPadOS 27.0 24A435,
  September 2026). That is the foreground requirement, not quota.

Map by the typed error, record the build beside it, and treat the distinction as route- and
build-specific. A `rateLimited` refusal does not establish a short recovery. A nil `resetDate`
never means "now" or unused allowance, and a supplied date does not promise that a later batch
completes. Stop at the first refusal of either kind.

Evidence (studywright, private): [measurements/audits/os27-injection-release-pcc-mac-v4.md](https://github.com/vocaro/studywright/blob/f1d1178e03949b2a6fb20dc6d85618988c0d01b2/measurements/audits/os27-injection-release-pcc-mac-v4.md).

## Quota metadata lags the refusal and cannot see exhaustion

`quotaUsage` starts tracking when the model is initialized, populates asynchronously and gives a
rough standing, not a numeric budget. After a thrown quota refusal it still read `belowLimit`,
not approaching. Only a served generation proves one call is available on that device.

- **`isLimitReached`** is free to read and correct for a real limit, so a local pre-flight on it
  is worth keeping, but it cannot predict every refusal. The authoritative signal is the typed
  error from an attempted generation.
- **`isApproachingLimit`** never read true over 500 served generations on a macOS 27.0 beta
  before 2026-08-22. On 26A5421a it read true on 2026-08-27, at the refusal rather than before
  it. It cannot warn in time.
- **`limitIncreaseSuggestion`** was nil before the process first reached PCC and non-nil on
  every reading afterwards (1,001 of 1,001 on macOS 27.0 betas) while the status stayed
  `belowLimit`. Its presence is not an exhaustion signal.
- **`QuotaUsage`** has no public initializer, so map decomposed values in testable code.

Do not attempt PCC before a `resetDate` the refusal itself threw; take the date from the error,
because `quotaUsage` can read a nil date after a refusal. Hold the refusal locally until that
date, per device, and let a nil or past date, or a `rateLimited` refusal, hold nothing. Do not
invent a wait when no date is given. A passed date reopens attempts without restoring the
allowance: refill was gradual, and the first requests after a date could be refused again.

## Xcode's availability override does not simulate quota

`FOUNDATION_MODELS_AVAILABILITY_OVERRIDE` is an Xcode implementation setting, not a documented
public API, and can be placed in a scheme's run environment. It simulated `deviceNotEligible`
and `modelNotReady` on both model types without inference. Its quota values
(`approachingQuotaUsageLimit`, `quotaUsageLimitReached`) were not a substitute for a real quota
state on macOS 27.0 26A428 or the iOS 27.1 Simulator (24A94401) with Xcode 27.1 (27A9269):
metadata probes, including a profile-authorized Mac bundle, read `belowLimit`, false flags and
nil reset and suggestion. Xcode Run, newer runtimes, physical devices and the error path under
either setting remain unqualified. A generation under a simulated setting still spends normally.

## The app-tier quota and the fm allowance are separate per-device pools

**The app-tier quota** is what an entitled app spends. It is per Apple Account and per device,
and it is shared with every Apple Intelligence feature on that device, so use outside the
measurement draws on it unrecorded. A refusal holds only the device that incurred it; another
device on the same account keeps its own allowance, and an untested device's capacity is
unknown, not exhausted. The quota behaved as a trailing 24-hour window that refills gradually.
Refusals from a rested start fell near 470 calls in the preceding 24 hours on a Mac (macOS 27.0
26A428, September and October 2026) and on an iPad (iPadOS 27.2 24B5099f, 2026-10-10). That
figure is an observation, not a published limit. A refusal is the only observation of a full
window, so an estimate from recorded spend ranks devices and sizes batches but never verifies
capacity.

**The `fm` allowance** is what the `fm` developer tool spends through PCC, separate from the
app-tier pool; on 26A428 the tool had no PCC model at all. No API reports the allowance, and
`quotaUsage` does not move while it drains. On macOS 27.0 betas a full window was roughly 1,000
to 1,300 successful generations, but a session's refusal arrived anywhere from 188 to about 997
generations, because the window refills gradually and the amount already drawn is unobservable.
Recovery took from about 8 to about 24 hours, with no fixed reset at local or UTC midnight, and
waiting longer did not reliably buy more capacity. Budget against the smallest observed figure.

Each control proves only its own pool: a served `fm` call says nothing about the app's
entitlement, and a served app-tier probe says nothing about the `fm` allowance.

## Metered PCC work needs a ledger and a first-refusal stop

A spend is invisible to version control unless written down. Before a run that will spend PCC,
record an intent naming the pool, device, planned calls and purpose; afterwards record the
outcome: the served count, a quota refusal with its thrown `resetDate` or an explicit absence,
and the first served call after a refusal. Commit outcomes promptly, since an unrecorded spend
misleads every other session.

- **Key devices by an opaque, namespaced digest** of a stable hardware identifier (on a Mac, a
  SHA-256 of `IOPlatformUUID` under a project namespace; on iOS, of the hardware UDID). Never
  store the raw identifier, hostname or account, never substitute the controlling Mac's key or a
  CoreDevice UUID for the measured device, and fail rather than pool events whose device cannot
  be identified.
- **Recorded counts are history, not remaining capacity.** Two checkouts' append-only ledgers
  merge as the time-ordered union of both sides' lines, each side's order kept, with no line
  edited or dropped.
- **Stop at the first refusal.** Never poll a refused device for a trickle of capacity and never
  schedule a quota retry. Diagnose before the next attempt; a stop on one device does not
  prevent a separately prepared run on another.
- **Exhaust a device deliberately only when the refusal itself is the evidence**, such as
  verifying a quota defect on the current build. Exhaust the device other sessions need least,
  prepare any capture before the first call (a sysdiagnose taken while the block is live), stop
  at the first refusal and record its `resetDate`.

How much a project may spend, and on which devices, is the owning project's decision.

## The fm developer tool is a different route with its own gate and confounds

`/usr/bin/fm` serves the on-device model and, where the build has one, PCC under its own
allowance. It refuses PCC unless it has a `com.apple.Terminal` ancestor process, so it cannot be
launched for PCC from an editor, an IDE terminal or an agent shell. Never spawn Terminal (with
`osascript` or `open -a Terminal`) to satisfy that check: it circumvents a deliberate gate and
bills a slow-refilling allowance to the account holder. Starting `fm serve` from Terminal is the
owner's action; a harness only attaches to it.

- **No PCC model on 26A428.** On macOS 27.0 26A428, `fm serve` listed only `system` in `/health`
  and `/v1/models` even when launched from Terminal, answered a `pcc` request with HTTP 400
  ("Unknown model 'pcc'"), and listened on its default port 1976.
- **Listings differ by build; read lines, not exit status.** On 26A428, `fm available` listed
  only the system model and exited 0, and `fm models` was an unknown command that exited 1. On
  macOS 27.2 26B5091g, outside Terminal, both listed `system` available and `pcc` refused, and
  both exited 1. A refused `pcc` line is not a failed control for work that never touches PCC.
- **A preamble confounds the transport.** On macOS 27.0 betas `fm serve` injected a system
  preamble of about 189 tokens ahead of the caller's messages. Its effect depends on the axis:
  it measured near zero for prompt-injection compliance (17 of 60 through the gateway against 16
  of 60 natively) and was unmeasured for grounding. The on-device model behind the same gateway
  is the transport control: it should track the native on-device model, and any difference is
  the gateway. Re-confirm format-sensitive findings through the entitled app route.
- **Request details change outcomes.** `fm serve` streams unless the request body sets `stream`
  to `false`. An HTTP 200 with empty content is success to `curl` and an empty generation to a
  client that checks content. `/health` answers only on the port given to `fm serve --port`.
- **`/health` does not prove PCC can serve.** It reported availability during quota refusals;
  Apple developer technical support identified that as a defect, so treat it as a build-specific
  observation. Check served content before trusting a run.
- **A canary detects a shut window but cannot size an open one.** About 20 non-streamed calls
  that must each return non-empty content distinguish "a trickle has returned" from "the window
  is open", which one call cannot; a clean 20 of 20 has preceded a refusal 188 generations
  later. Pointing the canary at the on-device model separates exhaustion from a wedged gateway
  at no PCC cost.
- **`fm count-tokens --image` failed at every image size** on 26A5416b.

Evidence (studywright, private): [measurements/audits/os27-fm-pcc-transport-absent-26A428.md](https://github.com/vocaro/studywright/blob/f1d1178e03949b2a6fb20dc6d85618988c0d01b2/measurements/audits/os27-fm-pcc-transport-absent-26A428.md).

## Guardrail modes depend on tier and generation kind

`SystemLanguageModel(guardrails: .permissiveContentTransformations)` applies only to `String`
generation, where it stops throwing `guardrailViolation` but may return a refusal as a `String`.
Guided generation keeps the default guardrails, and `PrivateCloudComputeLanguageModel` has no
guardrail setting. On five book-length inputs on the on-device model (k = 8, 3 trials, macOS
27.0 26A428), the default guardrails produced 23 safety-filter stops in 180 answers and the
permissive mode none, with 21 of the 23 recovered answers correct. Run guardrail comparisons as
interleaved arms in one session so model or OS drift cannot read as an effect, and record each
failure's typed code. Safety-filter exposure measures Apple's safety layer, so it informs rather
than gates.

## Guided generation constrains shape, not meaning

A schema constrains the shape of each field, not its semantics. Asked through the `fm serve`
transport for a multiple-choice question whose answer field must copy one option verbatim, PCC
frequently put the whole rendered question into that field (every probe on one corpus and about
58% on another), while the on-device model through the same gateway returned a real option; a
suite that counted only rejections reported zero either way. Check what each field holds before
reading any rate.

- Every out-of-range answer index on record was 0, so in-range indices were silently mis-keyed,
  and where index and text disagreed the text was right. Check output instead of directing
  format in the prompt; prompt-side distractor hardening was a net loss on-device.
- Resolve exact option text before any forgiving matcher, so "MHz" cannot select "mHz".
- Structured on-device generation cost about 15 s per call against about 2.9 s for free text on
  macOS 27.0 betas; budget it at roughly five times free text.
- Encoded `GenerationSchema` JSON varied in object-key order between constructions (Xcode 27.1
  27A9269, macOS 27.0 26A428), so hash each construction's bytes or a canonical form, never
  assume byte stability.
- JSON can encode an integral `Double` as an integer-looking number; keep native kind tags when
  a decoded value's type matters.

## A native session transcript grows with every turn

A stateful `LanguageModelSession` keeps every turn's prompt in its transcript, including
retrieved passages. A retrieval-augmented session at k = 8 overflowed the 4,096-token on-device
window at turn 2 (2,240 tokens after turn 1, throwing at 4,238), while a stateless per-call
prompt of the same design stayed at 1,997 tokens. Keep conversation history as an app-owned
value, sliced to a token budget, never a turn count: one long answer (551 to 603 tokens)
consumed a 702-token history allowance alone. Never admit that history as grounding evidence;
see [inference and evidence](inference-and-evidence.md).

## Directing a refusal sentence makes the model refuse

On the macOS 26 on-device model (July 2026), every prompt wording that directed a fixed refusal
sentence, firm or friendly, made the model take that exit on about 17 to 30% of answerable
questions, while a wording that directed none over-refused near 0%. On macOS 27 the directing
template's refusal rate fell to about 5.6% with no code change, which is the drift a fresh
per-OS baseline exists to catch. Leave abstention to a deterministic grounding check rather than
the prompt. A self-containment instruction ("restate the subject") halved cross-turn
over-refusal on prose and reversed on question-and-answer material, so it is a per-corpus
measured choice.

## PCC output format can move scores by tens of points

PCC changes server-side with no version to watch, so the same code and inputs can produce
different numbers without an OS update. No change over time was observed under a fixed
configuration on the recorded builds, but that is an observation, not a guarantee, and a format
change is silent. PCC's habit of wrapping an answer in a fenced JSON envelope, a difference
between tiers rather than an observed drift, floored a sentence-level grounding check and
produced 59.4% over-refusal through the `fm serve` transport while the enclosed content was
grounded. A plain-prose format instruction removed the envelope on PCC but raised on-device
over-refusal from 1.9% to 7.5%, so per-tier prompt text was rejected in favor of unwrapping
envelopes in the checker. Re-measure PCC on a clock and immediately whenever its output looks
different; the trigger policy is in [OS and model drift](../../guides/os-drift.md).

## Images cost little and are priced only by displacement

On 26A5416b an image attachment fit at every size from 32 to 2,048 px. It displaced about 26
tokens of the on-device window at 32 to 128 px and about 143 at 512 px, and a flat ~18 tokens on
PCC from 32 to 1,024 px. `tokenCount(for:)` throws on any prompt carrying an attachment, so
measure image cost by displacement: fill the window with text until it overflows, with and
without the attachment. Legibility depends on label height, not image size: reading failed when
the smallest label fell below about 5 px. These costs were measured on solid two-colour bitmaps;
detailed figures are untested. On 26A428 PCC accepted an image `Attachment` in a
FoundationModels `Prompt` through an entitled bundle and read a nonce from a 128 px image; that
proves carriage, not cost.

## Tool registration and token counting are model work

Registering Apple's `SpotlightSearchTool` cost 12,784 tokens against the 4,096-token on-device
window on a macOS 27.0 beta, and the over-window registration threw its own error family. Never
issue a query from a measurement: the corpus that tool searches is the operator's own mail,
files, calendar and photos. A measurement that searches points at a synthetic index and says so.
`tokenCount(for:)` is itself a model call and slows under contention: 2 s cold and idle against
216 s straight after a full test suite.

## Latency is not a tier check

Under contention, short-output runs inverted the tiers: on 26A5416b PCC served at p50 1,208 ms
against an on-device control at 863 ms. On-device latency grows with prompt length and with
sustained use, so budget per corpus and route as [model
evaluation](../../guides/model-evaluation.md) describes. Spend the cheapest tier that can do the
work: deterministic code first, then the on-device model, which is not metered, then PCC, which
draws on the person's finite shared allowance.

## Generative results need hardware and the machine's model to itself

The model behind a Simulator is the host Mac's: an iOS 27 Simulator on a macOS 27 host reported
the model available and generated. Never report a simulated run as a device generative result;
generative measurements belong on hardware, and even there a single request is an anecdote. No
capability key gates installation on Apple Intelligence hardware, so degrade at runtime.

Run one model workload per machine. Two processes driving one Mac's on-device model both sat at
about 0% CPU with no output for many minutes, and concurrent Core ML and FoundationModels work
silently corrupted embeddings ([embedding correctness](embedding-correctness.md)). Before a run,
check for other test processes on the host, including other checkouts', and admit the run
through the shared heavy-work queue ([shared host](../../guides/shared-host.md)). During
on-device generation the test runner sits near idle while `TGOnDeviceInferenceProviderService`
and `modelmanagerd` burn CPU: idle daemons with a stale log is a hang, busy daemons with an
empty log is buffering. PCC generation shows about 0% local CPU, so check the connection to the
serving process instead. On iOS, keep the host app in the foreground with Auto-Lock off for the
whole run; [device testing](../../guides/device-testing.md) covers device hosts.

## Claim only the privacy behavior the app controls

An app that answers through PCC can verify only the destinations its own code contacts. State
what stays on the device and what is sent (the question and the passages retrieved for it go to
PCC), and report Apple's PCC commitments as Apple's, citing Apple's PCC security documentation
and its model documentation separately rather than merging them. Any surface that claims
on-device retrieval discloses cloud answering on the same surface; split across screens, each
clause can look defensible while the whole becomes false. Unscoped phrasings such as "nothing
leaves your device" or "works offline" applied to answering are false whenever passages are
sent. The quota is the person's Apple Intelligence allowance, not the app's, and copy never
implies the app has one of its own.
