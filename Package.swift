// swift-tools-version: 5.9

import PackageDescription

let package = Package(
    name: "Pxl",
    platforms: [
        .macOS(.v13)
    ],
    products: [
        .executable(name: "Pxl", targets: ["Pxl"])
    ],
    targets: [
        .executableTarget(
            name: "Pxl",
            path: "Sources/Pxl"
        )
    ]
)
