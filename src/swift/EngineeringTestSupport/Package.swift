// swift-tools-version: 6.2
import PackageDescription

let package = Package(
    name: "EngineeringTestSupport",
    platforms: [.macOS("27.0"), .iOS("27.0")],
    products: [.library(name: "EngineeringTestSupport", targets: ["EngineeringTestSupport"])],
    targets: [
        .target(name: "EngineeringTestSupport"),
    ]
)
