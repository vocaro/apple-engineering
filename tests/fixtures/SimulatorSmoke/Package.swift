// swift-tools-version:6.0
// The smallest package eng simulator-tests can build once and test on several simulators: the
// positive control for a real run (guides/parallel-tests.md).
import PackageDescription

let package = Package(
    name: "SimulatorSmoke",
    platforms: [.iOS(.v17), .macOS(.v14)],
    targets: [
        .target(name: "SimulatorSmoke"),
        .testTarget(name: "SimulatorSmokeTests", dependencies: ["SimulatorSmoke"]),
    ]
)
