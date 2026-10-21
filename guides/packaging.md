# Packaging

These mechanisms and lessons apply when the stated capability is present. Original
measurements establish their recorded platform and workload; they do not establish
universal behavior on later operating systems or in a different application.

## Swift package distribution checks

A local-path app build accepts what a revision-based consumer rejects, such as a root manifest
with `.package(path:)` dependencies. Verify a package through the route its consumers use:

1. Snapshot the current package inputs into an immutable temporary Git repository. Set
   `gc.auto 0` and `maintenance.auto false` in it before committing, then `git repack -a -d`, so
   detached maintenance cannot race SwiftPM's clone.
2. Resolve and build a client that depends on that repository by revision, never by path. Once
   the change is integrated, point the client at the real remote URL and commit instead.
3. For each separately usable core, add a negative control that reinstates a local dependency
   and requires SwiftPM's specific refusal of it, not merely any failure.

This is a package-resolution and compilation check; behavior and model quality need their own
measurements.

Hold each product's dependency closure exactly. Read `swift package dump-package` and assert the
product-to-target sets and each target's dependency set as equalities, not as minimums. A client
product that an app links without the library must reach none of the library's targets and
import none of them, and headless targets import no UI framework (SwiftUI, WebKit, PDFKit and
the like). The toolkit's `packaging.py` (`target_dependencies`, `target_closure`) computes
closures from `dump-package` output and rejects non-canonical dependency forms in a portable
core. When a module moves, update the declared contract explicitly, keep one canonical provider
per module in the graph, and keep the negative controls: they are the boundary the move must
preserve.

To check an app's policy code without launching the app, compile its actual policy sources and
their tests in an isolated SwiftPM package at the app's resolved dependency revision, and record
the source and dependency identities. Acceptance of what needs the app host (queues, App Groups,
extension lifetime) stays with the app-hosted suites.

## Explicit imports and package identity

Build with `--explicit-target-dependency-import-check error`, which fails a target that imports
a module neither it nor its dependencies declare, including targets of local packages the build
reaches. SwiftPM makes the check only when it compiles a target and does not repeat it for one
already built, even one that failed it, so a warm build misses an import an earlier build
compiled. Build each package into an empty scratch directory, through admission on the shared
host, and delete it afterwards:

```sh
PYTHONPATH="$VOCARO_ENGINEERING_ROOT/src/python" python3 -m vocaro_engineering.resources -- \
  swift build --package-path PACKAGE --scratch-path "$SCRATCH/PACKAGE" \
  --explicit-target-dependency-import-check error
```

Build Release as well: Release strips every `#if DEBUG` region, so a scene, preview or fixture
that a Release compile still names fails there rather than at archive time.

SwiftPM and Xcode build the root package under its identity: the checkout directory's name,
lowercased and mangled to a C99 identifier. Application targets that use the root package's
`package` declarations derive the same `-package-name` from the checkout directory, which keeps
the public API unexpanded from a checkout of any name. A local package is built under its own
identity, so what another package or the app uses of it must be `public`. A suite compiled into
an app-hosted test bundle sits outside its package, so a `package` declaration it names fails
only there; compile that bundle in a gate.

## Generated Xcode projects

With XcodeGen, `project.yml` is the source and the `.xcodeproj` is generated; change targets and
settings in the spec and regenerate. Observed with XcodeGen 2.46.0 and Xcode 27 (October 2026):

- An open Xcode rewrites the generated project in its own format when files change or the
  project is regenerated (`platformFilter`, `explicitFileTypes`). Discard that rewrite rather
  than committing it.
- Root groups that share a name are written in a different order on each run, so regenerating an
  unchanged spec still shows a diff. The reordering changes nothing.
- Regeneration deletes a scheme added by hand that the spec does not declare.
- XcodeGen cannot express a `LaunchAction`-only scheme element, and `xcodebuild build` followed
  by `devicectl` never consumes a `LaunchAction`
  ([background assets](../knowledge/apple/background-assets.md) has the case that matters).
- A multiplatform target gets only the iOS runpath
  ([app extensions](../knowledge/apple/app-extensions.md) has the macOS fix).
- `xcodegen generate --use-cache` regenerates only when the spec or its inputs changed.

When an app and its app-hosted test bundle both link a package, Xcode builds the package as a
separate framework whose signature a sandboxed, hardened app refuses to load, and the app aborts
at launch. Keep client products static, so a build's `PackageFrameworks` stays empty
([app extensions](../knowledge/apple/app-extensions.md) has the extension side).

When one source list feeds several platforms, build every platform in the gate: an iOS-shaped
edit behind `#if os(iOS)` can break the Mac build without touching a macOS file. String Catalog
extraction differs by platform for the same reason; build each platform, merge the strings both
builds extracted, and fail when the committed catalog is stale.

Debug-only code must stay out of Release. A region counts as Debug-only only when its `#if`
condition is a conjunction with a `DEBUG` term and no `||`: `#if DEBUG && os(iOS) || os(macOS)`
compiles into a macOS Release build. Exclude Debug-only files per configuration
(`EXCLUDED_SOURCE_FILE_NAMES` selected by `$(CONFIGURATION)`), and scan every archived Release
product for the symbols, trigger keys and fixtures that must be absent, after proving on the
Debug product that the scan sees them. An archive made another way, such as from Xcode's
Organizer, needs the same scan before distribution.

Build-side traps to account for in gates (Xcode 27, 2026):

- Installing a simulator build on a device fails only on hardware, as a signature error; resolve
  the built product for the SDK being installed to.
- An incremental Debug build can leave stale app-hosted `.xctest` bundles in the product.
  Exclude them from shipped-content scans; they are not shipped.
- Launch Services protects a launched Mac UI-test runner's executable from the incremental
  linker, so rebuild the generated runner before each test run.

## Distribution artifact inspection

Validate the built archive or exported app, not a development launch. Local validation is not
server acceptance, and a development launch does not establish store acceptance.

**Signatures and entitlements.** Run `codesign --verify --deep --strict --verbose=2` on the app
and on each nested executable bundle, and read `codesign -d --verbose=4` for the authority
chain, the team and the `(runtime)` flag of the hardened runtime. Read effective entitlements
through the Security framework (`SecStaticCodeCreateWithPath`, then
`SecCodeCopySigningInformation` with `kSecCSSigningInformation`, then
`kSecCodeInfoEntitlementsDict`): `codesign`'s legacy XML output can be empty for a valid
DER-only signature. Check the sandbox entitlement, the absence of `get-task-allow`, the exact
App Group list and each expected file-access entitlement; a group spelled differently in the
Info.plist, the entitlements or the code is silently not shared
([app extensions](../knowledge/apple/app-extensions.md)).

**Privacy manifests.** A SwiftPM target that declares `PrivacyInfo.xcprivacy` as a resource
builds it into its resource bundle, and Xcode embeds that bundle in the app. Require each
expected manifest at its path in each executable that embeds the dependency; a count of
manifests proves nothing. A binary distribution, such as an XCFramework with a dependency linked
in, loses that dependency's bundle and must carry the declaration in its own manifest. Fail on
unexpected tracking or collected-data declarations.

To audit required-reason APIs, list the undefined symbols of each shipping release object with
`nm -u` and match the spellings each API compiles to:

- C functions by underscored name, with the x86_64 `$INODE64` variants and deprecated `64`
  spellings (`_stat`, `_stat$INODE64`, `_lstat`, `_getattrlist`);
- Foundation constants (`_NSURLCreationDateKey`, `_NSFileModificationDate`);
- classes (`_OBJC_CLASS_$_NSUserDefaults`);
- Swift members by the mangled prefix their accessors share (`URLResourceValues.creationDate`);
- Objective-C messages by the selector stub Swift and clang emit (`_objc_msgSend$systemUptime`).

A message sent through plain `objc_msgSend` names no selector in `nm -u`, so treat an object
that uses it as unreadable and fail. Check an object that ships no manifest against an empty
declaration set. The audit cannot see a call the build did not compile, such as one in an
iOS-only branch of a macOS object, or an API reached by name at run time (`NSClassFromString`,
`dlsym`, key-value coding); audit those by hand. Record the date Apple's list was read, and
retake it when Apple revises it:
[required reason API](https://developer.apple.com/documentation/bundleresources/describing-use-of-required-reason-api).
File-timestamp reasons on that list include `3B52.1` (a file the user chose), `C617.1` (a file
in the app's container) and `0A2A.1` (an SDK wrapping the API for the app), as read in September
2026.

**Resource bundles and products.** A resource-only SwiftPM bundle needs no executable signature
of its own; the enclosing bundle's strict verification checks its sealed resources. Check that
each expected bundle is in the executable that uses it and absent from the others, and that no
product expected to link statically was built as a framework.

**Development hooks.** Scan the shipped binaries for test launch arguments, debug menu titles
and other hooks, after proving on a Debug build that the scan finds them.

**Bundle contents.** Refuse a bundle holding a property list with unexpanded `$(…)` build
settings: App Store Connect rejects it as an invalid nested bundle. Scan for files that must not
ship (fixtures, development tools, documents of a fixture type) through nested bundles, without
following directory symlinks, failing closed on traversal errors. Check the compiled icon, each
icon slot's pixel size against its point size and scale, and that the iOS (universal) icon is
opaque (PNG colour type 2).

**Provisioning profile.** Decode it with `security cms -D -i embedded.provisionprofile` and
check that it has not expired, lists no devices, is not provisioned for all devices, and names
the expected platform, team and application identifier, matching the signed entitlement.

**Identity.** Signing embeds the signing time, so identify an executable by its unsigned
compile, and hash a Debug product's `EXECUTABLE.debug.dylib` as well as its small launcher.
[Device testing](device-testing.md) covers how re-signing changes digests between runs. Read
provenance from the running process where possible: its code signature (Security's `SecCode` on
the Mac), `kern.osversion` and the hardware model.

Exercise the archived app itself, not a rebuild: launch the archive without re-signing or
injecting anything, check the executable and resource seal hashes before and after, and verify
the signature again ([background Mac testing](background-mac-testing.md) covers driving it
without the pointer or keyboard).

## Mac App Store export and TestFlight upload

Export with `xcodebuild -exportArchive` and an options file setting `method` to
`app-store-connect` and `destination` to `export` for a local package or `upload` to send it to
App Store Connect. Either preserves the archive's version and build number; neither submits the
app for review. Verify an exported installer and its payload:

```sh
pkgutil --check-signature EXPORT/APP.pkg
pkgutil --expand-full EXPORT/APP.pkg FRESH_DIRECTORY
```

Then validate the expanded app as above with distribution requirements: an App Store signing
authority (`Apple Distribution:` or `3rd Party Mac Developer Application:`) and a current Mac
App Store profile matching the app and team. Use a fresh expansion directory each time.

Distribution-signed App Store code is intended for upload and is not supported for local
execution ([Apple's explanation](https://developer.apple.com/forums/thread/707043)). Test the
development-signed archive locally and qualify Apple's distributed build through TestFlight; any
code, resource or signing change repeats the relevant qualification.

Accounts and keys (observed with Xcode 27, October 2026):

- A browser session signed in to App Store Connect does not supply an Xcode account.
- An App Store Connect API key with the App Manager role is refused cloud-managed distribution
  signing ("Cloud signing permission error"); archiving and exporting with cloud signing need a
  team key with the Admin role. Keep each `.p8` private key outside every repository with mode
  600, and pass its key ID through the environment rather than committing it.
- When `xcodebuild` cannot load the Xcode account's keychain credentials ("Invalid credentials
  in keychain"), Xcode's saved account list is emptied while its Accounts settings go on listing
  the account, and every later export reports "No Accounts". Authenticate with an API key
  instead.

App Store Connect accepts each build number once per version and platform. Choose the next
number above every uploaded build (a date-based `YYYYMMDDNN` works), stamp it at build time
rather than editing the spec, and reserve the numbers failed local runs used across worktrees so
another checkout cannot reuse them. Declaring `ITSAppUsesNonExemptEncryption` as `NO` skips the
export compliance question; revisit it when the app adds encryption beyond the operating
system's.

An upload command that names its build:

1. Refuses a tree with uncommitted tracked changes, so every build names its exact commit, and
   notes when that commit is not yet on `origin/main`.
2. Archives, scans the bundle's property lists, checks the signed entitlements, exports with the
   chosen options and uploads with the API key.
3. Waits for processing, then hands the build to its tester group; a failure on one platform
   does not strand the other platform's build.
4. Writes a receipt with the commit, the build number, each package's SHA-256 and, once
   processed, the App Store Connect build identifier and tester-group outcome, and keeps it
   after a partial failure.

Observed with TestFlight on macOS 27 (October 2026): a TestFlight install replaces the app in
`/Applications` and shares its data with a development build of the same bundle identifier.
Apple-hosted Background Assets packs reach only TestFlight and App Store builds
([background assets](../knowledge/apple/background-assets.md)).

StoreKit environments and purchase testing are in [StoreKit testing](storekit-testing.md).

## Deployment floor assessment

To assess a lower deployment floor:

1. Lower `platforms` and build the library, tools and tests for every destination
   (`swift build`, and `xcodebuild build-for-testing` for `generic/platform=iOS Simulator`),
   through admission. The availability errors are what needs the newer OS. Swift Testing on
   Xcode 27.0 rejected `@available` on a `@Suite` type, so mark individual `@Test` functions.
2. Read each binary's `LC_BUILD_VERSION` (`xcrun vtool -show-build BINARY`): the linked SDK
   selects the frameworks' compatibility behavior.
3. Compare outputs of the lower-floor build and the current build on the current OS, byte for
   byte. Equality shows that lowering the floor changes nothing for current-OS users; it says
   nothing about the older OS.
4. Run on the older OS. Install its simulator runtime beside the current one, create a simulator
   on each, and run the suite and the release command-line tool in each
   (`xcrun simctl spawn UDID TOOL ARGUMENTS`). An older macOS needs a virtual machine or a
   second Mac; whether a framework such as Vision works inside a macOS virtual machine must
   itself be measured, and tests it cannot serve are unmeasured.
5. Triage each difference as a version-specific rule, an accepted difference or a reason to keep
   the floor.

A package that built cleanly at a lower floor still behaved differently there. On iOS 26.5
(23F73) simulators against iOS 27.0 (24A434), September 2026, PDFKit's text spacing differed
across most of a document corpus (letter-spaced headings, split kerned capitals, combining marks
spaced from their letters), and Vision recognized about a third of a Hindi document's text.
Vision's `RecognizeDocumentsRequest` requires OS 26. A build that compiles at a floor is no
evidence that it behaves there.

## Dependency licence gates

Enforce licences with gates over the pinned, fully resolved dependency graph, not by hand. Pin
everything (`Package.resolved`, `uv.lock`), so dependencies change only when a lockfile changes,
which is the review checkpoint.

- Gate the shipping closure, the runtime dependency graph, not development extras: audit tooling
  drags in copyleft transitives that never ship, and a gate that reports them is one people
  learn to ignore.
- Classify Python licences across all three declaration mechanisms (PEP 639
  `License-Expression`, OSI classifiers and the legacy free-text field), on word tokens rather
  than substrings, checking forbidden patterns first so a compound naming one copyleft operand
  fails whole. Fail an unclassifiable licence. Plant GPL, LGPL, AGPL, proprietary and undeclared
  fixtures as negative controls. A distribution that points at a bundled licence file passes
  only after a dated review.
- For Swift, enumerate the transitive graph (`swift package show-dependencies`) and fail any
  resolved identity missing from a register that records its licence, read from the package's
  own `LICENSE` file. A test asserts the resolved closure equals the register exactly.
- A binary outside SwiftPM's graph, such as a static library with Rust components, needs its own
  verified inventory: the pinned upstream lockfile, binary and source identities and the
  retained licence texts.
- Code a dependency ported into its own sources is in no graph. Check the dependency's own
  third-party notices against yours, and that no copied code or web resource ships.
- Derive the third-party notices from the graphs, with a `--check` that fails when they are
  stale. Omit versions there: attribution identifies a component and its licence, and versions
  belong in the SBOM.
- An SBOM (CycloneDX, for example) snapshots the whole build environment, development tooling
  included; the gates and notices cover the shipping closure. Replace a release's SBOM only
  after the new one validates.
- Apache-2.0 §4 requires redistributing the licence text and any `NOTICE` file; listing the
  component in the notices does not discharge that.
- A shipped model's weights must permit commercial use and redistribution. Review its
  training-data provenance in its papers and appendices, not only its card, because a card-level
  check rewards non-disclosure; disclose known restrictions rather than presenting them as
  cleared.
- Keep GPL and AGPL tools as separately installed development or comparison tools, never linked
  or bundled into a closed-source App Store app. Fixtures stay out of app bundles too. This is
  engineering policy, not legal advice.

## Core ML model resources

Ship a compiled `.mlmodelc`. Compiling a `.mlpackage` at load with `MLModel.compileModel(at:)`
costs on every model construction (about a third of one macOS suite's wall clock) and never
returned on the iOS Simulator (Xcode 27, 2026). Compile offline with `coremlcompiler`, which
ships inside Xcode and is macOS-only, and hold the compiled model's outputs to the package's
with a parity test; they were bit-identical.

Xcode 27's SwiftPM runs Core ML code generation on any resource declared by an `.mlpackage` path
and fails in a package context ("No predominant language detected", Xcode 27A266a). Declare a
plain wrapper folder instead, such as `.copy("Resources/Model")` holding the model.

`coremlcompiler` is not byte-deterministic: compiling one unchanged package rewrites
`coremldata.bin` and `analytics/coremldata.bin` with different bytes each time and writes
`metadata.json`'s keys in either order (macOS 27.0 26A428, Xcode 27A266a). Only `model.mil` and
`weights/weight.bin` were stable, so pin those two as a compiled model's identity and compile
afresh rather than restoring a canonical compiled artifact.
