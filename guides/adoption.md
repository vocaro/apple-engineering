# Adoption and maintenance

Clone the public MIT-licensed `vocaro/vocaro-engineering` beside your projects with
`git clone https://github.com/vocaro/vocaro-engineering.git`. No GitHub credentials or private
repository access are needed for that checkout. No installation or network is
needed for normal local invocation. Python 3.9+ runs the source checkout directly; do not
install a wheel of the Python directory without the repository's policies and source resources.
Use `VOCARO_ENGINEERING_ROOT` when the checkout is elsewhere. Python guidance and knowledge
commands work offline; guarded shared-resource lanes refresh operating policy from the remote.
The existing StudyWright and Pagepour Swift test-support dependencies expect the sibling
checkout path, from a linked worktree too ([below](#locating-the-toolkit-from-a-worktree)). A
different Swift support location also requires updating those project manifests and their graph
contracts; the Python environment variable changes only tool lookup.

## Existing and new projects

Existing projects keep `engineering.json`, `scripts/eng`, small compatibility adapters and their
product rules. Run `python3 scripts/eng instructions` before work. Run `doctor` to validate the
configuration and prerequisites. A capability enables guidance; it does not grant permission to
use a device, screen, model, corpus or hosted runner.

For a new repository, run
`python3 /path/to/vocaro-engineering/bin/eng --project /path/to/NewRepo init`. Initialization is
additive and runs no work. It sets `toolkit.path` relative to the toolkit's main checkout, also
when run from a linked worktree of the toolkit, such as a session's, which is removed with its
session. A missing .gitignore is initialized for generated outputs; an
existing one is preserved. Existing projects must ignore .build/engineering so result logs do
not become source inputs in subsequent evidence records. Select the applicable capabilities and
add explicit argv-based lanes to engineering.json. Give each lane a `resource` of `light`,
`heavy` or `exclusive`: `eng run` refreshes the operating policy and admits heavy and exclusive
lanes through [heavy-work admission](shared-host.md#heavy-work-admission), writes the lane's log
and source receipt under `.build/engineering/LANE/`, and, with `minimumTests`, fails a
successful run that executed fewer tests. A lane whose log reports a test unmeasured, or whose
`timeout` stops it, exits 3 ([evidence commands](evidence.md#evidence-commands)).
`eng run LANE -- ARGUMENTS` appends arguments, such
as a test filter, to the lane's command; such a run needs at least one executed test in place
of `minimumTests`, or exactly N with `--expect N`. Other heavy work that no lane names goes
through `eng admit [--exclusive] -- COMMAND`. Mark a heavy or exclusive lane that needs no
simulator, device, screen (background Mac UI tests included) or timing measurement
`"buildHost": true`: `eng run` then sends it to
the owner's [build host](shared-host.md#build-host) first, and `eng remote run LANE` sends any
lane there. Either first runs the project's `provision` lane, when it has one, to provision the
ignored inputs of the build host's checkout. Give a project with a simulator, measurement or
VoiceOver capability heavy lanes for its tests and its gate, so the commands its agents run most
are admitted by name; `doctor` warns when it has none. Make a lane exclusive only for work that
needs the host to itself ([heavy-work admission](shared-host.md#heavy-work-admission)). Mark a
lane that takes the owner's screen, such as Mac XCUITest, `"foreground": true`: `eng run` then
refuses it unless `VOCARO_DEVICE_OWNER` names the session holding `mac-foreground`
([attended Mac sessions](shared-host.md#attended-mac-sessions)).
Disposable simulators and the approved reserved pool are separate capabilities and cannot both
be enabled. Conflicts or unknown fields fail validation. Existing AGENTS.md files are
preserved: add the explicit `scripts/eng instructions` entry yourself when adopting into a
repository that already has instructions. The CLAUDE.md that init writes imports AGENTS.md
(`@AGENTS.md`), which Claude Code loads at session start, where it may not follow a link; give
an existing CLAUDE.md the same import.

Use `eng knowledge QUERY` to find subject documents. Capture future findings with their source
commit, the original evidence link, applicability and limits; add an index entry. Runtime
mechanisms belong in a focused Swift package when a concrete consumer needs them. Test helpers
belong in src/swift and link only to test/tool targets. No production package imports the CLI.

## Locating the toolkit from a worktree

The launcher resolves `VOCARO_ENGINEERING_ROOT` first, then `toolkit.path` from
`engineering.json` (default `../vocaro-engineering`) relative to the checkout it runs in. A
linked worktree, such as a session's under `.claude/worktrees`, usually has no clone beside it,
so the launcher then tries the same relative path beside the repository's main checkout: a
linked worktree's `.git` is a file naming its private Git directory, whose `commondir` file
leads to the shared `.git`, whose parent is the main checkout. Reading those files needs no Git
command, so script tests that replace Git with fakes still work. A submodule's `.git` file has
no `commondir`, and a main checkout's `.git` is a directory; neither falls back. The adapter
passes the clone it found to every shared script it runs.

The toolkit was named `apple-engineering`. When the path is the default, whether configured or
not, and no `vocaro-engineering` clone is found in either place, the launcher tries
`../apple-engineering` in the same places, so a project can adopt the new adapter and default
before every clone is renamed. Any other configured path, `../apple-engineering` included, is
used as written.

The fallback serves the launcher alone. A Swift manifest that names a toolkit package by a
relative path, as Pagepour's `project.yml` and Xcode project and StudyWright's `app/project.yml`
name `src/swift/EngineeringTestSupport`, resolves that path from the checkout it is in, so in a
linked worktree with no toolkit beside it, package resolution fails with "cannot be accessed".
Keep a symbolic link to the toolkit's main checkout where that path leads. Codex keeps one beside
each of its worktrees; for the Claude app's session worktrees, one link in the repository's
`.claude/worktrees` folder serves them all, and the repository's exclude for that folder keeps
it out of status:

```sh
ln -s ~/Development/vocaro-engineering ~/Development/PROJECT/.claude/worktrees/vocaro-engineering
```

`doctor` warns when a tracked `Package.swift`, XcodeGen `project.yml` or Xcode project names a
toolkit package that does not resolve from the checkout, and prints the link to make. It makes
no link itself.

`toolkit_location` in `integrations/shared.py` implements this, and `integrations/eng.py`
imports it. `init` installs them as `scripts/_engineering.py` and `scripts/eng`; a project that
copied them earlier replaces both together, since the launcher needs the adapter's
`toolkit_location`.

## Updating and rolling back

The default is one maintained local checkout. Review its changes, update with `git pull
--ff-only`, and rerun the enabled consumer checks. All sibling projects see that update. To try
an older toolkit independently, create a separate checkout at its known commit and point just
the affected project at it with VOCARO_ENGINEERING_ROOT. Record that commit in test evidence.
Do not reset a checkout another session is using. The toolkit offers no mutable revision cache
or `eng upgrade` command; Git owns local checkout versions. Current operating policy is still
read from origin/main by `eng policy refresh`, even when tools use an older checkout, and
`eng instructions` notes when its checkout lacks commits of origin/main as last fetched. It
fetches nothing itself; `eng policy refresh`, heavy lanes and `eng admit` update that ref.

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
