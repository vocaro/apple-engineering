# StoreKit environments and entitlements

These mechanisms and lessons apply when the stated capability is present. Original
measurements establish their recorded platform and workload; they do not establish
universal behavior on later operating systems or in a different application.

StoreKit answers from one of three environments: Xcode's local test environment, driven by a
StoreKit configuration file; Apple's sandbox, for development-signed and TestFlight builds; and
production. The [StoreKit testing guide](../../guides/storekit-testing.md) has the procedures.
The initial observations were made with Xcode 27.0 (27A266a) and 27.1 (27A9269), macOS 27.0
(26A428) on an Apple silicon MacBook Pro, iOS and iPadOS 27 simulators, and iPhone and iPad
devices on 27.0 (24A435), from 2026-09-30 to 2026-10-08.

## StoreKit request success does not prove update delivery

On the Mac, an app-hosted `SKTestSession` can load local products, report current
entitlements and complete purchases while `Transaction.updates` never yields the updates its
own actions generate: Ask to Buy approval, `buyProduct(identifier:options:)` (a purchase made
outside the app) and `refundTransaction(identifier:)`. The app's own purchases still produced
updates. The same tests passed on iOS 27 simulators, and a commit and Xcode that had passed on
the Mac failed the same way a week later, so such a failure establishes neither a source nor an
Xcode regression.

The unified log showed the cause on macOS 27.0 (26A428). storekitagent received each test push
for the `XcodeTest` environment, resolved the app's client to `Sandbox`, logged that it had no
client for the bundle ID in `XcodeTest`, and skipped the push; no `transactionsupdated`
notification followed. On the simulator, storekitd resolved the client to the local
configuration and the app checked for updates within milliseconds. Why the client resolved to
Sandbox is the environment switch described in the next section.

Separate service delivery from model handling with an independent listener: count the
product's updates on a second `Transaction.updates` task, outside the model under test. No
delivery at all is an environmental result; a delivery that did not change the model is a
model defect. Only the first may be recorded as an expected failure, with its reason, and only
where the limit is known (here, the Mac). Never add retries, delays or a sync call to a
shipping entitlement model to make such a test pass, and never weaken its verification.

[Pagepour measurements/storekit-lifetime/record.md](https://github.com/vocaro/Pagepour/blob/68f508d14c2a2133592027eb89806009bccf0326/measurements/storekit-lifetime/record.md#mac-transaction-updates-on-2026-10-08)

## Local session state, entitlement recovery and updates are separate observations

On macOS 27.0 (`26A428`) with Xcode 27.1 (`27A9275`), a local `SKTestSession` held a
purchased transaction while both unfiltered and product-filtered `Transaction.currentEntitlements`
were empty, and a bounded verified-entitlement wait failed. The app's test startup guards were
active before app-owned purchase startup. This result did not implicate the filtered API or an
early app-owned StoreKit request.

An authorized Run with the local configuration, debugging disabled and an isolated app fixture
changed the identical diagnostic from failure to pass. Immediate snapshots remained empty; the
existing bounded wait recovered the verified entitlement. The subsequent full plan recovered
entitlements, but independent probes still observed no Ask to Buy, external-purchase or refund
updates. A configured Run therefore does not by itself establish update delivery. The three
retained expected failures are not successful delivery qualifications, and their earlier
last-Run-with-None explanation does not fully explain this post-setup result.

Request routing is a separate observation too. A request-only log filter reported local
contexts while omitting Sandbox client initialization and dropped-update messages. Capture
background routing as the [runbook](../../guides/storekit-testing.md#the-mac-storekit-environment)
describes; neither local request contexts nor a session's purchased transaction establishes a
verified entitlement or a delivered update.

Source and evidence: Pagepour adoption `18f3f8d`, setup candidate `9cbab3f`, and
[follow-up results at `bd73ab0`](https://github.com/vocaro/Pagepour/blob/bd73ab0/measurements/storekit-support-adoption/followup.md).
The setup changed no shipping entitlement code or purchase-test assertions.

## A Mac keeps one StoreKit environment per bundle ID

Observed on macOS 27.0 (26A428) with Xcode 27.0 and 27.1, October 2026; this is a recorded
observation of one host, not a documented StoreKit contract.

- Every copy of an app with the same bundle ID on the Mac used the same StoreKit environment:
  other sessions' Debug builds, an archived Release build and a Finder launch alike.
- The environment followed the last Run from Xcode. A scheme whose Run action names a StoreKit
  configuration file switched it to the local environment (`XcodeTest` in storekitagent's
  log, "Environment: Xcode" in its dialogs). A Run with StoreKit Configuration: None switched
  it to Sandbox. Later Finder launches, archived builds and command-line UI tests stayed where
  the last Run left them.
- App-hosted tests whose test plan names a configuration had their own requests served by
  `XcodeTest`, but update delivery did not follow them; it stayed with the last Run, which is
  the failure in the previous section. The first push resolved to Sandbox came during a Run
  with StoreKit Configuration: None; the earlier log had expired, so that trigger is inferred
  from the timeline.
- Other sessions' local StoreKit work moved every copy: an archive check logged only
  `XcodeTest` requests after other sessions had run local purchase tests, until a Run with
  StoreKit Configuration: None restored Sandbox. Which of their actions made the switch was not
  isolated.
- LaunchServices' preferred copy did not decide it. Unregistering an installed TestFlight copy
  changed nothing, and storekitagent read the running test host's receipt path.

Consequences: one session's local purchase tests change what another session's archive or
sandbox check sees, so treat a bundle ID's StoreKit environment as a shared resource. Read it
from the unified log instead of assuming it: storekitagent logs each task's context as
`Running task with context: ([Client] BUNDLE_ID (NAME) Sandbox)` or `… XcodeTest`, and
entitlement queries as `Sandbox - TransactionQuery(…)`. Switching it back requires a Run from
Xcode's window, which is foreground use of the Mac. When scripting Xcode while two Xcode
versions run, address the selected one by path; `application id "com.apple.dt.Xcode"` can
reach the other.

## Local StoreKit on the Mac still shows dialogs

Observed with Xcode 27.1 (27A9269) on macOS 27.0 (26A428), 2026-10-08:

- The Mac's local environment ignores `SKTestSession.disableDialogs`. Buy and Restore wait on
  storeuid's simulated "Sign in with Apple Account" prompt, marked "[Environment: Xcode]". It
  takes no credentials, but a prompt left open by a failed run holds up the next run's
  entitlement check. The first storeuid query in a run took about a minute to attach.
- Buy from the app's UI opens Xcode's payment sheet. Its confirm control, drawn by PassKit's
  payment authorization extension, is withheld from screenshots and from the accessibility
  tree, so UI tests cannot press it. While UI automation runs, macOS withholds it from people
  too: a person watching saw no control, and a click where it belongs did nothing.
- A purchase or Restore requested by the app-hosted test process itself completed without any
  sheet or simulated prompt.
- Twice among one day's 36 app-hosted StoreKit sessions, each time the first purchase after a
  fresh build, storekitagent sent the session's purchase to Apple's sandbox server with the
  Mac's Sandbox Apple Account and opened the real payment sheet despite `disableDialogs`. A test
  time allowance turned that into a failed test instead of a held run.
- StoreKit logs that it added an `NSRemoteView` as a subview of SwiftUI's `NSHostingView` on
  every presentation of the Mac purchase sheet. The purchase still completed; the message is
  not a failure signal.

Mac Buy through the app's UI therefore needs a person: the Apple sandbox, with the owner
confirming. Automated Mac coverage presses the purchase controls from an app-hosted test
through in-process accessibility instead.

## StoreKitTest sessions are not the store's error and timing contract

Local test sessions differ from the store in ways tests must allow for without changing the
shipping model:

- Xcode 27 maps an injected `.generic(.userCancelled)` purchase error to
  `StoreKitError.unknown` (server error 907). Test the real cancellation contract, a
  `.userCancelled` result or a thrown `StoreKitError.userCancelled`, through a controlled
  store, and use the injected error only to show that no access is granted and a retry works.
- The Mac test service commits a purchase to its entitlement cache asynchronously. A fresh
  model's first `currentEntitlements` query can miss it, so poll with a deadline; do not call
  `AppStore.sync()`, which an ordinary launch does not do.
- A refund immediately after the purchase was delivered inconsistently. Separate the purchase
  and refund signing times by more than a second.
- An injected `loadProducts` network error shows that product availability is independent of
  cached access. It is not an airplane-mode measurement.
- On a fresh iPadOS 27 simulator (Xcode 27.0), the app's StoreKit context lacked the local
  configuration until an app-hosted purchase suite had run; the first UI test saw an
  unavailable product. Run the app-hosted suite on a new simulator before its UI suite.

## A passing toolchain comparison has limits

The unchanged Pagepour purchase plan passed all 17 test identities with Xcode 27.2 beta 3
(`27B5038j`) on both iOS 27.2 (`24B5110a`) and the original iOS 27.1 (`24A94401`)
simulator. Its earlier Xcode 27.1/iOS 27.1 Ask to Buy timeout remains a failed observation.
The later runs changed the build SDK and test toolchain and retained simulator state. They
establish a working local-test lane, not that the driver alone caused the timeout or that a
freshly erased simulator will pass. See the
[comparison and source receipts](https://github.com/vocaro/Pagepour/blob/bd73ab0/measurements/storekit-support-adoption/followup.md#subsequent-acceptance-checks).

When comparing local StoreKit results, hold source and test identities constant and name the
Xcode build, build SDK, runtime build, configuration and retained or reset simulator state.
Attribute a cause only when the comparison isolates it. A UI runner's successful build is
preparation evidence; it does not qualify UI execution.

## A verified entitlement, not a price or a flag, grants access

Use one entitlement model for every window and scene of the app. Its rules hold for any
non-consumable unlock, such as a lifetime purchase, and extend to other product types:

- Grant access only for a verified transaction with the expected product ID and product type
  and no revocation date. Never persist an unverified purchase flag; StoreKit's cached verified
  transactions establish access offline.
- Start one `Transaction.updates` listener before the first entitlement query and price
  request, and start it once however many scenes appear. Query
  `Transaction.currentEntitlements(for:)` at launch and when the app becomes active.
- Deliver a verified transaction's access before calling `finish()`. Leave an unverified
  transaction unfinished so StoreKit can deliver it again, and report verification failure.
- Let a newer update or query supersede an older one: a slow entitlement snapshot taken before
  a purchase must not undo it.
- Call `AppStore.sync()` only from an explicit Restore action, because it can ask the person to
  sign in. Launch, foreground and price checks never call it.
- Keep price separate from access. A missing product or failed price request leaves verified
  access intact and shows existing owners no unavailable-purchase warning; Restore stays
  available while locked even without a price. Display StoreKit's localized `displayPrice`;
  never hard-code an amount.
- Allow one payment at a time: disable Buy and Restore while either runs. Treat a pending
  result (Ask to Buy) as awaiting approval, with access arriving through updates. Treat
  cancellation, whether a result or a thrown error, as no change and no error message.
- A refund or revocation removes access. Which completed work stays usable is app policy.
- Hide Buy and Restore once unlocked. An existing owner's access returns at launch; Restore is
  for a device that has not yet seen the purchase. On the observed Mac, the first sign-in to
  the Sandbox Apple Account still needed an explicit Restore; the iPhone needed none.
- When the app hosts unit tests, do not start the app's own purchase model: the test creates
  its StoreKit test session before any request. UI tests still run the real model.

## Sandbox purchases need a Sandbox Apple Account

A normal Apple Account cannot buy in the sandbox. On iPadOS 27.0 (24A435), 2026-10-01, Apple
rejected such a purchase with an authorization error naming "Environment: Sandbox" and
delivered no entitlement.

- Create the account in App Store Connect under Users and Access, Sandbox (Apple's "Create a
  Sandbox Apple Account"). Its email must not belong to an existing Apple Account, and it must
  not be added as an App Store Connect team member.
- On iPhone and iPad, sign in under Settings, Developer, Sandbox Apple Account, keeping the
  device's main Apple Account signed in. On the Mac, the sandbox sign-in appears in App Store
  settings after the app first attempts an in-app purchase.
- A development-signed build, Debug or Release, without a local StoreKit configuration uses the
  sandbox. Apple's sheets then say "Environment: Sandbox" and that the purchase is a no-charge
  test.
- A non-consumable in a universal purchase (one App Store Connect app record with iOS and macOS
  platforms) unlocks every platform for the same account: purchased on iPad, it was recovered
  at launch on iPhone and restored on the Mac. Family Sharing is not involved for the
  purchaser's own devices. Record which platform purchased and which recovered; a restore on
  the purchasing device alone does not qualify the others.
- A newly created non-consumable still in Prepare for Submission was purchasable in the sandbox
  by development-signed builds the same day.
- Clearing a sandbox account's purchase history in App Store Connect is not immediate. On
  2026-10-08 a later purchase was offered as a download of the existing purchase.

Authentication belongs to a person. The iPad's sandbox password sheet was not exposed as an
XCTest alert. On the Mac, Computer Use keyboard entry did not reach the storeuid sign-in
field, LocalAuthentication returned "Not available" for PassKit's payment policy although
Touch ID was configured, and a sign-in helper stalled after a canceled verification prompt
and survived quitting Xcode. Keep sandbox credentials out of tests, logs, results and
documents; the owner enters them.

## TestFlight purchases do not reuse sandbox purchases

On macOS 27.0 (26A428), 2026-10-02, a TestFlight-installed build did not restore the purchase
made with the Sandbox Apple Account. Restore stayed at "Contacting the App Store…" and then
reported that it could not restore, and signing in alone did not establish the entitlement.
The ordinary TestFlight purchase, free for testers, unlocked it. The inferred reason is that
TestFlight purchases belong to the tester's own Apple Account rather than to a Sandbox Apple
Account. Plan a TestFlight purchase into TestFlight qualification. Distribution-signed builds
cannot be launched locally, so TestFlight is where the distributed candidate's purchases are
first exercised (see [packaging](../../guides/packaging.md)).

## Trial state and store entitlements have different lifetimes

A StoreKit entitlement belongs to the Apple Account: it survives deletion and reinstall and
reaches the account's other devices. State the app keeps itself, such as a free-use counter,
does not. On iPhone and iPad, deleting the app removes its data and offloading keeps it
([Apple](https://support.apple.com/en-ie/108429)). On the Mac, deleting or replacing the app
bundle normally leaves its container, so reinstalling alone does not reset the state; removing
the data does. Local state excluded from backup and kept out of the Keychain is a trial policy,
not an uninstall-resistant license. Keep such state separate from the entitlement and decide
its persistence as product policy.

## On-device verification keeps purchase data on the device

StoreKit 2 verifies transactions on the device, so an app needs no server to grant access, and
its only purchase traffic is StoreKit's own. A receipt-validation server or App Store Server
Notifications puts purchase data on the developer's server, which changes what the App Privacy
answers must declare.
