import Foundation
import StoreKit

/// Counts the transaction updates StoreKit delivers for chosen products, independently of the
/// model under test.
///
/// Create the probe before the action that should produce an update (an Ask to Buy approval,
/// an external purchase or a refund). When the model's wait times out, `deliveries`
/// distinguishes a service that delivered nothing from a model that received an update and
/// did not act on it. Only the first can be an environmental expected failure.
@MainActor
public final class TransactionUpdateProbe {
    /// The product identifiers whose updates are counted.
    public let productIDs: Set<String>
    /// Updates delivered for `productIDs`, verified or not.
    public private(set) var deliveries = 0
    /// Updates delivered for `productIDs` that StoreKit verified.
    public private(set) var verifiedDeliveries = 0

    private var task: Task<Void, Never>?

    /// Starts listening to `Transaction.updates` at once.
    public init(productIDs: Set<String>) {
        self.productIDs = productIDs
        let wanted = productIDs
        task = Task { [weak self] in
            for await update in Transaction.updates where wanted.contains(update.unsafePayloadValue.productID) {
                guard let self else { return }
                deliveries += 1
                if case .verified = update { verifiedDeliveries += 1 }
            }
        }
    }

    /// Stops counting. Leaving the probe has the same effect.
    public func stop() {
        task?.cancel()
        task = nil
    }

    deinit { task?.cancel() }
}

/// Bounded waits for asynchronous StoreKit results in tests.
public enum StoreKitWait {
    /// How a wait for a transaction update ended.
    public enum UpdateOutcome: Sendable, Equatable {
        /// The condition held before the deadline.
        case satisfied
        /// StoreKit delivered no update for the probe's products before the deadline.
        case notDelivered
        /// StoreKit delivered this many updates, but the condition still did not hold.
        case deliveredWithoutEffect(Int)
    }

    /// Polls `condition` on the main actor until it holds or `timeout` elapses, and returns
    /// its final value.
    @MainActor
    public static func until(timeout: Duration = .seconds(15), interval: Duration = .milliseconds(20),
                             _ condition: () -> Bool) async throws -> Bool {
        let deadline = ContinuousClock.now + timeout
        while !condition(), ContinuousClock.now < deadline { try await Task.sleep(for: interval) }
        return condition()
    }

    /// Waits for `condition`, which an update seen by `probe` should make true.
    ///
    /// Treat `.notDelivered` as an expected failure only where it is a recorded environmental
    /// limit (for example `XCTExpectFailure` or `withKnownIssue` on a Mac whose StoreKit
    /// environment does not deliver test-session updates), and record the reason.
    /// `.deliveredWithoutEffect` is always a failure of the model under test.
    @MainActor
    public static func update(seenBy probe: TransactionUpdateProbe, timeout: Duration = .seconds(15),
                              interval: Duration = .milliseconds(20),
                              until condition: () -> Bool) async throws -> UpdateOutcome {
        if try await until(timeout: timeout, interval: interval, condition) { return .satisfied }
        return probe.deliveries == 0 ? .notDelivered : .deliveredWithoutEffect(probe.deliveries)
    }

    /// Polls `Transaction.currentEntitlements(for:)` until it reports a verified transaction for
    /// `productID` without a revocation date, or `timeout` elapses.
    ///
    /// A local test service can commit a purchase to its entitlement cache after the purchase
    /// returns, so a fresh model's first query may miss it. Polling avoids `AppStore.sync()`,
    /// which can ask for a sign-in and is not what an ordinary launch does.
    public static func verifiedEntitlement(for productID: String, timeout: Duration = .seconds(15),
                                           interval: Duration = .milliseconds(50)) async throws -> Transaction? {
        let deadline = ContinuousClock.now + timeout
        repeat {
            for await result in Transaction.currentEntitlements(for: productID) {
                if case .verified(let transaction) = result, transaction.productID == productID,
                   transaction.revocationDate == nil {
                    return transaction
                }
            }
            try await Task.sleep(for: interval)
        } while ContinuousClock.now < deadline
        return nil
    }
}
