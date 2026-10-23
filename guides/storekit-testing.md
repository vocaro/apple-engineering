# StoreKit testing

These mechanisms and lessons apply when the stated capability is present. Original
measurements establish their recorded platform and workload; they do not establish
universal behavior on later operating systems or in a different application.

This guide covers testing in-app purchases with StoreKit 2: which layer establishes what, how to
configure local StoreKit tests, and how to qualify purchases against Apple's sandbox and
TestFlight. The platform behavior it relies on, with its recorded builds, is in
[StoreKit environments and entitlements](../knowledge/apple/storekit-environments.md), which
also states the entitlement model the tests check. Reusable test code is the
`StoreKitTestSupport` product of
[src/swift/EngineeringTestSupport](../src/swift/EngineeringTestSupport/Package.swift).

## Test layers

Each layer establishes something the others cannot. Report each separately; a pass in one is
not evidence for another.

| Layer | Environment | Establishes | Does not establish |
| --- | --- | --- | --- |
| Controlled store | None; an injected stand-in | Access rules, races, messages, the real cancellation contract | Any StoreKit behavior |
| App-hosted StoreKitTest | Local, from a `.storekit` file | Real StoreKit 2 calls with Xcode-signed transactions: purchase, restore, Ask to Buy, refunds, injected errors, updates | Apple's servers, accounts or sheets |
| Purchase UI tests | Local | The app's purchase UI and relaunch on iOS | A Mac Buy (its confirm control is hidden from automation) |
| Mac view tests | Local | The Mac purchase pane through in-process accessibility | Menus that need focus, system sheets |
| Apple sandbox | Sandbox, development-signed build | The App Store Connect product and price, the Sandbox Apple Account, native sheets, cross-device recovery | TestFlight or production delivery |
| Archive smoke | Sandbox | The archived build recovers its entitlement with no local environment leaking in | A purchase |
| TestFlight | TestFlight, tester's account | The distributed candidate's purchase and access | Production |

Production purchases are not a test layer. Record the Xcode, OS and device for every run, and
whether each passed, failed, was skipped or was unmeasured.

## Configuration files, schemes and test plans

- Create the StoreKit configuration file with Xcode. Keep it out of the app target and add it
  as a resource of the purchase test bundles only, so a test finds it in its own bundle.
- Put StoreKit tests in their own test targets and schemes. Ordinary suites have no StoreKit
  configuration, create no `SKTestSession`, inject a stand-in store, and therefore never move
  the Mac's StoreKit environment. Link the `StoreKitTestSupport` product into the purchase test
  targets only; other test bundles then never link StoreKitTest.
- In a purchase scheme, name the configuration in both the Run action (Options, StoreKit
  Configuration; XcodeGen `run: storeKitConfiguration:`) and the test plan
  (`storeKitConfigurationFileReference`). The app scheme used for archives and sandbox checks
  keeps StoreKit Configuration: None.
- In the purchase test plan, turn off parallelization and enable test timeouts with a short
  allowance (60 seconds was enough), so an unexpected payment sheet fails one test instead of
  holding the run.
- Guard test-only launch arguments, fixtures and reset hooks with `#if DEBUG`, and check that
  Release binaries lack them (see [packaging](packaging.md)).
- When the app is the host of a unit-test bundle (XCTest is loaded), skip starting the app's
  own purchase model so the test can create its session before any StoreKit request. A launch
  argument lets UI tests keep the real model.

## Controlled-store tests

Put StoreKit behind a small protocol that the entitlement model owns: product lookup, purchase,
current entitlements, an updates stream and sync. In the shipping app only the StoreKit adapter
constructs a verified transaction value. A test stand-in has settable results and errors, counts
purchases, syncs, finishes and listeners, and can suspend a call on a continuation to stage a
race. Check at least:

- Only a verified, unrevoked transaction of the expected product and type unlocks; an
  ordinary entitlement check never calls sync.
- A verified purchase unlocks before `finish()` runs. Canceled, pending and unverified results
  grant nothing and are not finished; pending shows awaiting approval.
- A thrown `StoreKitError.userCancelled` shows no message; another error shows one; both allow
  a retry that succeeds.
- Restore finds an entitlement, reports none, and a failed restore keeps verified access.
- A missing product or failed price request keeps verified access and shows no warning; a
  later price load succeeds. With no product, Buy is unavailable and Restore still works.
- Starting the listener twice installs one listener. Updates unlock, revoke and ignore other
  products.
- An entitlement snapshot taken before a purchase and returned after it does not undo the
  purchase. A second Buy or a Restore during a payment starts nothing.

## App-hosted StoreKitTest tests

Run these inside the app host with the configuration bundled in the test target. They use real
StoreKit 2 APIs against transactions Xcode signs locally; no Apple account, payment or App Store
Connect product is involved.

1. Reuse one `SKTestSession` per configuration file in a test process. Before each test call
   `resetToDefaultState()`, `clearTransactions()` and set `disableDialogs`; afterwards clear and
   reset again. `LocalStoreSession` does this.
2. Construct the app's real model, start it, and wait with a deadline until it has checked
   entitlements and loaded the product. A new model instance stands in for a relaunch; it is
   not a process relaunch.
3. Wait with deadlines (15 seconds, polling every 20 to 50 ms), and fail at the caller's line
   with what was awaited.
4. Count updates on a separate listener (`TransactionUpdateProbe`). On a timeout, classify it
   (`StoreKitWait.update`): no delivery is an environmental result, which on the Mac may be an
   expected failure (`XCTExpectFailure`, or `withKnownIssue` in Swift Testing) with its reason;
   a delivery without effect is always a failure. iOS has no expectation.

Cover these cases:

- Purchase: access is granted, the transaction is purchased, and a fresh model recovers it from
  `currentEntitlements` without sync (`StoreKitWait.verifiedEntitlement` polls the Mac's
  asynchronous cache).
- Ask to Buy: set `askToBuyEnabled`, buy, expect pending, then
  `approveAskToBuyTransaction(identifier:)` and expect the update to unlock.
- Refund: after a purchase, wait more than a second, `refundTransaction(identifier:)`, and
  expect access to go away in the running model and in a fresh one.
- External purchase: `buyProduct(identifier:options:)` while the model runs; expect the update.
- Injected purchase errors with `setSimulatedError(_:forAPI:)`, then clear the error and
  expect a retry to succeed. An injected cancellation arrives as `.unknown`; the real
  cancellation contract belongs to the controlled-store tests.
- Verification failure (`.verification(.invalidSignature)` for the verification API) never
  unlocks; after clearing it, Restore recovers access.
- An existing entitlement with a `loadProducts` network error stays unlocked with no product.

## Purchase UI tests

On iOS, create the session in the UI-test runner from the configuration bundled in the UI-test
target, launch the app with arguments that isolate its state, and drive Buy, Restore, dismissal
and a real terminate-and-relaunch. Attach screenshots for review. Run the app-hosted suite
first on a newly created or erased simulator, pass the simulator's explicit uppercase UDID, and
run through heavy-work admission:

```sh
python3 scripts/eng run LANE
# Without a configured lane:
python3 scripts/eng admit -- \
  xcodebuild test -project APP.xcodeproj -scheme PURCHASE_UI_SCHEME \
  -destination 'platform=iOS Simulator,id=UDID' -parallel-testing-enabled NO
```

On the Mac, do not automate a local Buy through UI tests: the confirm control of Xcode's
payment sheet is hidden from automation and, while automation runs, from people. Test the Mac
purchase pane from the app-hosted suite instead: host the real view in an offscreen window that
never becomes key and read and press its controls through in-process accessibility (see
[background Mac testing](background-mac-testing.md)). Find the window by accessibility
identifier, not title. A menu command is enabled only while its window is key, so check its
title and place and drive the binding it sets.

Mac UI tests take the pointer and keyboard. On the owner's Mac they are a method only for a
session the owner has explicitly authorized. In such a session use `click()`, since touch-style
`tap()` did not open the purchase sheet. If a test must pass storeuid's simulated sign-in,
accept only a prompt that says it simulates authenticating and is marked "[Environment:
Xcode]", never an ordinary Apple Account dialog.

## The Mac StoreKit environment

Treat each bundle ID's StoreKit environment on the Mac as a shared resource: local purchase
suites and Xcode Runs with a configuration move it to `XcodeTest`, and sandbox and archive
checks need `Sandbox`.

1. Before either kind of run, find other sessions' copies of the app and planned StoreKit
   runs (list running copies' paths with `ps`), and agree an order with those sessions.
2. Read request contexts and background routing from storekitagent's log over the run:

   ```sh
   started="$(date '+%Y-%m-%d %H:%M:%S')"
   # Run the check here.
   /usr/bin/log show --start "$started" --info --style compact \
     --predicate 'process == "storekitagent" AND (eventMessage CONTAINS "BUNDLE_ID" OR eventMessage CONTAINS "TransactionQuery" OR eventMessage CONTAINS "transactionsupdated")' \
     > storekit-environment.txt
   rg -n 'Sandbox|XcodeTest|No client|Initializing client' storekit-environment.txt
   ```

   Replace BUNDLE_ID with the app's bundle identifier. Keep raw service logs private: they
   can include account identifiers. TransactionQuery and update lines can concern another app,
   so correlate them with the bundle's adjacent task context before attributing them. A filter
   restricted to `[Client] BUNDLE_ID (` omits client initialization and dropped-update messages;
   local request contexts alone do not establish the route used by synchronization or delivery.
   Record verified entitlement recovery and observed updates separately from request routing.
3. To change it, Run a scheme from Xcode once (Product > Run): StoreKit Configuration: None
   selects Sandbox, a scheme with the configuration selects the local environment. That uses
   Xcode's window, so it is the owner's step or an authorized session's. If two Xcode versions
   run, address the selected Xcode by path. For environment setup, disable debugging and verify
   the active scheme and destination before launching. Once the app is built under admission,
   Product > Perform Action > Run Without Building performs the setup without another build.
4. Record the environment you leave and tell the sessions that share the Mac.

## Apple sandbox qualification

Sandbox runs use Apple's servers, the App Store Connect product and a Sandbox Apple Account on a
development-signed build. They are opt-in qualification, never part of an ordinary suite.

- Prepare: the product exists in App Store Connect; the device is signed into the Sandbox Apple
  Account; the build is development signed (Release is fine) from a scheme with no StoreKit
  configuration and no test session. Agree a window with the owner before using a physical
  iPhone or iPad and take a real reservation and handoff; approval covers installing and
  launching, not operating the device by hand.
- Gate every sandbox test on an environment variable so it skips visibly otherwise. Pass the
  variable with xcodebuild's `TEST_RUNNER_` prefix, which xcodebuild strips before the variable
  reaches every test runner process; here the test reads `SANDBOX_RESTORE`:

  ```sh
  TEST_RUNNER_SANDBOX_RESTORE=1 python3 scripts/eng admit -- xcodebuild test-without-building \
    -xctestrun MANIFEST.xctestrun -destination 'platform=iOS,id=DEVICE_ID' \
    -only-testing:UI_TESTS/SandboxPurchaseUITests/testRestoreAndRelaunch \
    -parallel-testing-enabled NO
  ```

- Never enter credentials or accept Apple's dialogs from an interruption handler. A probe may
  press Buy and then wait (five minutes was enough) for the owner to authenticate and confirm.
  A test may press Purchase in Apple's sheet only after finding, in the same UI host, its
  explicit notice that the purchase is for testing and will not be charged; the owner still
  enters the password.
- Separate probes: price lookup and the purchase prompt; purchase; restore and relaunch. A price
  probe establishes product availability and the entry point, not a transaction. The restore
  probe records whether launch already recovered access (and that Restore is then hidden) or
  Restore was needed, then terminates and relaunches.
- Record which device and platform purchased and which recovered. Qualify each platform of a
  universal purchase on its own device.
- A Mac sandbox run needs the bundle ID's environment at Sandbox (previous section), the owner
  signed in, and, for Buy, the owner at the keyboard.
- Keep result bundles and screenshots private; they can show account details.

## TestFlight and production

A distribution-signed build cannot be launched locally, so TestFlight is the first place the
distributed candidate's purchases run. TestFlight purchases are free and belong to the tester's
account; on the observed Mac a purchase made with a Sandbox Apple Account did not restore
there. Make the TestFlight purchase before any TestFlight check that needs access, and treat a
failed Restore as no evidence that purchase history was read. Production behavior is observed
only after release.

## Offline and recovery checks

- Automated: a fresh model recovers access from `currentEntitlements`; an injected
  `loadProducts` network error leaves existing access unlocked with no misleading warning; a
  real relaunch keeps access with Buy and Restore hidden.
- On a device, the owner checks offline access by hand: turn off networking, force-quit, reopen
  and open the purchase view. Disabling Wi-Fi disconnects network-attached automation, so record
  the owner's report as the evidence; a screenshot taken after reconnecting does not show the
  network state at the time.
- After a correction to recovery or messages, rerun the device's access-and-relaunch probe on
  the corrected build; it does not replace the earlier offline check.

## Archive smoke check

An archived development-signed build should recover its entitlement from the sandbox with no
trace of the local environment:

1. Coordinate the Mac's StoreKit environment and set it to Sandbox. Sign the Mac into the
   Sandbox Apple Account that owns the purchase.
2. Refuse a distribution-signed candidate (an Apple Distribution or 3rd Party Mac Developer
   Application signing authority); it is for upload, not local launch.
3. Hash the executables and code-signature seals, launch the archive in the background, and
   drive it through accessibility without the pointer or keyboard
   (see [background Mac testing](background-mac-testing.md)).
4. Require verified access at launch with Buy and Restore hidden. Never buy: macOS hides the
   payment confirmation from automation.
5. Save storekitagent's lines for the run and fail unless the app made at least one Sandbox
   request and no XcodeTest request (the commands above).
6. Re-hash, re-verify the signature strictly, and record the counts with the result.
