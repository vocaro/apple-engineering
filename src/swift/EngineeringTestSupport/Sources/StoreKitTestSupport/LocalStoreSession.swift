import Foundation
import StoreKitTest

/// A local StoreKit test session for app-hosted tests and UI-test runners.
///
/// One `SKTestSession` is created per StoreKit configuration file in a test process and reused;
/// each test starts it clean with `prepare()` or `run(_:)`. The configuration file belongs to the
/// test target as a resource, never to the app target. This is test support: link it only into
/// test bundles that exercise StoreKit, never into a shipping target.
///
/// `disableDialogs` is a request, not a guarantee. On macOS 27 local StoreKit was observed to
/// show its simulated sign-in prompt and payment sheet regardless, and an app-hosted session
/// occasionally reached Apple's sandbox. Give purchase test plans a test time allowance so a
/// stray sheet fails a test instead of holding the run.
///
/// ```swift
/// let url = try LocalStoreSession.configuration(named: "Example", in: Bundle(for: Self.self))
/// let store = try LocalStoreSession.shared(configuration: url)
/// try await store.run { session in
///     session.askToBuyEnabled = true
///     // Exercise the app's purchase model with real StoreKit 2 APIs.
/// }
/// ```
@MainActor
public final class LocalStoreSession {
    /// The standardized URL of the StoreKit configuration file.
    public let configuration: URL
    /// The underlying session, for actions this type does not wrap, such as
    /// `buyProduct(identifier:options:)`, `refundTransaction(identifier:)`,
    /// `approveAskToBuyTransaction(identifier:)` and `setSimulatedError(_:forAPI:)`.
    public let session: SKTestSession

    private static var sessions: [URL: LocalStoreSession] = [:]

    private init(configuration: URL, session: SKTestSession) {
        self.configuration = configuration
        self.session = session
    }

    /// The process's session for `configuration`, created on first use.
    public static func shared(configuration: URL) throws -> LocalStoreSession {
        let key = configuration.standardizedFileURL
        if let existing = sessions[key] { return existing }
        let created = LocalStoreSession(configuration: key, session: try SKTestSession(contentsOf: key))
        sessions[key] = created
        return created
    }

    /// The URL of `name.storekit` in `bundle`, normally the test bundle rather than the app.
    public static func configuration(named name: String, in bundle: Bundle) throws -> URL {
        guard let url = bundle.url(forResource: name, withExtension: "storekit") else {
            throw MissingConfiguration(name: name, bundle: bundle.bundleURL)
        }
        return url
    }

    /// Restores default settings, removes every transaction an earlier test left and asks
    /// StoreKit not to show dialogs. Call before the model under test makes a request.
    public func prepare() {
        session.resetToDefaultState()
        session.clearTransactions()
        session.disableDialogs = true
    }

    /// Removes this test's transactions and settings. Call from teardown.
    public func clean() {
        session.clearTransactions()
        session.resetToDefaultState()
    }

    /// Runs `body` between `prepare()` and `clean()`, cleaning up when `body` throws.
    public func run<T>(_ body: @MainActor (SKTestSession) async throws -> T) async rethrows -> T {
        prepare()
        defer { clean() }
        return try await body(session)
    }

    /// The configuration file is not a resource of the given bundle.
    public struct MissingConfiguration: Error, CustomStringConvertible {
        public let name: String
        public let bundle: URL
        public var description: String { "No \(name).storekit in \(bundle.path)" }
    }
}
