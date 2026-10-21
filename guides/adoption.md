# Adoption and maintenance

Clone `vocaro/apple-engineering` privately beside your projects. No installation or network is
needed for normal local invocation. Python 3.9+ runs the source checkout directly; do not
install a wheel of the Python directory without the repository's policies and source resources.
Use `VOCARO_ENGINEERING_ROOT` when the checkout is elsewhere. Python guidance and knowledge
commands work offline; guarded shared-resource lanes refresh operating policy from the remote.
The existing StudyWright and Pagepour Swift test-support dependencies expect the sibling
checkout path. A different Swift support location also requires updating those project
manifests and their graph contracts; the Python environment variable changes only tool lookup.

## Existing and new projects

Existing projects keep `engineering.json`, `scripts/eng`, small compatibility adapters and their
product rules. Run `python3 scripts/eng instructions` before work. Run `doctor` to validate the
configuration and prerequisites. A capability enables guidance; it does not grant permission to
use a device, screen, model, corpus or hosted runner.

For a new repository, run `python3 /path/to/apple-engineering/bin/eng --project /path/to/NewRepo
init`. Initialization is additive and runs no work. Select the applicable capabilities and add
explicit argv-based lanes to engineering.json. Disposable simulators and the approved reserved
pool are separate capabilities and cannot both be enabled. Conflicts or unknown fields fail
validation. Existing AGENTS.md files are preserved: add the explicit `scripts/eng instructions`
entry yourself when adopting into a repository that already has instructions.

Use `eng knowledge QUERY` to find subject documents. Capture future findings with their source
commit, the original evidence link, applicability and limits; add an index entry. Runtime
mechanisms belong in a focused Swift package when a concrete consumer needs them. Test helpers
belong in src/swift and link only to test/tool targets. No production package imports the CLI.

## Updating and rolling back

The default is one maintained local checkout. Review its changes, update with `git pull
--ff-only`, and rerun the enabled consumer checks. All sibling projects see that update. To try
an older toolkit independently, create a separate checkout at its known commit and point just
the affected project at it with VOCARO_ENGINEERING_ROOT. Record that commit in test evidence.
Do not reset a checkout another session is using. The toolkit offers no mutable revision cache
or `eng upgrade` command; Git owns local checkout versions. Current operating policy is still
read from origin/main by `eng policy refresh`, even when tools use an older checkout.

Runtime package updates are independent. Git consumers use SwiftPM's resolved dependency file;
local path consumers use their checkout's current files. Both are supported; tags and pins are
optional. Use one canonical module provider in the graph. After a runtime update, run its own
suite and each affected app's integration checks. Revert the consumer's requirement/resolution
to the previously verified commit to roll back, retaining the evidence for both outcomes.

## Verification boundaries

The original projects retain their qualified fixtures, acceptance matrices and historical
results. Shared Python regression tests exercise wrappers without taking over a simulator or
the screen. Native VoiceOver changes need the original fingerprint, negative controls and
runtime-specific qualification. Relocation preserves the native guard bytes; it does not
broaden the platforms or actions that an earlier qualification established.
