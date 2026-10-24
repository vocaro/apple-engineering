import SimulatorSmoke
import Testing
import XCTest

// One XCTest and one Swift Testing test, so a run counts both frameworks' totals.
final class SmokeXCTests: XCTestCase {
    func testDoubling() { XCTAssertEqual(doubled(2), 4) }
}

@Test func doublingInSwiftTesting() { #expect(doubled(3) == 6) }
