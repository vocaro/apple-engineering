# Vocaro Apple engineering

Maintained engineering rules, tools, test support and cross-project technical knowledge for
EPUBLib, PDFReflowLib, StudyWright, Pagepour, MathMLLayout and new projects. This repository is
public and [MIT licensed](LICENSE). The shipping libraries BackgroundTaskLib, FileProtectionLib and FileHandoffLib have
separate private repositories and no dependency on this toolkit.

## Local use

Clone this repository beside a project as `apple-engineering` without credentials:

```sh
git clone https://github.com/vocaro/apple-engineering.git
```

From the project checkout, run:

```sh
python3 scripts/eng doctor
python3 scripts/eng instructions
python3 scripts/eng knowledge background
python3 scripts/eng run LANE
```

`engineering.json` selects capabilities, exceptions and argv-based lanes. Set
`VOCARO_ENGINEERING_ROOT` for another toolkit location. Local checkouts require no pin or
release tag. Record source identities when collecting evidence. Shipping package dependencies
are resolved by SwiftPM, independently of engineering.json.

Initialize a new project from this checkout:

```sh
python3 bin/eng --project ../NewProject init --capability simulator-disposable
```

Initialization adds only missing configuration, a launcher and agent entry points. It preserves
existing files and starts no build, simulator, model, download or hosted job. Edit the new
project's lanes and local rules for its product. Run `instructions` explicitly: a link to a
shared AGENTS.md is not automatic agent instruction loading.

See [adoption and maintenance](guides/adoption.md) for updates, rollback and new repositories.

## Source and knowledge ownership

- `agents/core.md` and `agents/capabilities/`: common operating rules and enabled methods.
- `policies/shared-host.md`: current operating policy; `eng policy refresh` fetches main and
  reads that exact document without executing newly fetched code.
- [Knowledge index](knowledge/README.md): 57 practices and technical lessons with original
  evidence, applicability and limits, grouped into 24 subject guides.
- `src/python/vocaro_engineering/`: standard-library-only engineering implementations.
- `src/swift/`: maintained Swift source, including the test-only EngineeringTestSupport package
  and VoiceOver observer utilities. Native simulator dispatch source is in `src/objc/`.
- `integrations/`: small project launchers and compatibility adapters.

App fixture generation, launch arguments, privacy retention profiles, corpus approvals and
acceptance matrices remain with their projects. Source support files are addressed through the
toolkit, independently of the app fixture's checkout. Existing command names remain adapters.

## Coordination and evidence

The resource coordinator honors `HEAVY_SLOT_DIR`/`HEAVY_SLOTS` and the StudyWright shlock/guard
namespace. Exclusive work holds all heavy slots. Nested calls validate inherited admission
descriptors. Unknown, dead or uncertain owners retain their guard for inspection; time passing
does not release them. Never remove an uncertain guard without checking its recorded owner
and descendants. [Shared host methods](guides/shared-host.md) describes the inherited rules.

Evidence checks reject zero selected tests, changed bytes and escaping manifest paths.
Swift Testing's positive result is distinct from its zero-test XCTest shim. The toolkit records
the actual application/toolkit source identities, including local changes, with lane results.
It does not claim that a test count establishes every required acceptance condition.

Hosted Mac VoiceOver remains manually dispatched on the allowed disposable runner. Queue
inspection spans configured repositories; only the current repository's runs count against its
branch cap. Public workflows check out this repository without a deploy key. Ordinary public
Swift package builds do not import this toolkit.

See [public access and evidence](guides/public-access.md) for contributor setup, local queue
enrollment and private evidence boundaries. Private source links are supplemental provenance;
using the toolkit requires no access to the private applications or production packages.

## Verification

```sh
python3 -m unittest discover -s tests -v
swift build --package-path src/swift/EngineeringTestSupport
```

Run the affected project adapter regression suites too. Native simulator guard changes retain
fingerprints, instruction guards, startup canaries and stock negative controls, and require
their platform qualification before adoption. Never run Mac speech or foreground UI tests on
the workstation merely to verify a refactor.
