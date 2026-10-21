// swift-tools-version: 6.2
import PackageDescription

let package = Package(
    name: "EngineeringTestSupport",
    platforms: [.macOS("27.0"), .iOS("27.0")],
    products: [
        .library(name: "EngineeringTestSupport", targets: ["EngineeringTestSupport"]),
        // Separate so that test bundles which do not exercise StoreKit never link StoreKitTest.
        .library(name: "StoreKitTestSupport", targets: ["StoreKitTestSupport"]),
    ],
    targets: [
        .target(name: "EngineeringTestSupport"),
        .target(name: "StoreKitTestSupport"),
    ]
)
