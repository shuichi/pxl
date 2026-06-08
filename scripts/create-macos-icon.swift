#!/usr/bin/env swift

import AppKit
import CoreGraphics
import Foundation
import ImageIO
import UniformTypeIdentifiers

private enum IconError: Error, CustomStringConvertible {
    case missingOutputPath
    case imageCreationFailed(Int)
    case pngDestinationFailed(URL)
    case pngWriteFailed(URL)
    case icnsWriteFailed(URL)

    var description: String {
        switch self {
        case .missingOutputPath:
            return "Usage: create-macos-icon.swift /path/to/AppIcon.icns"
        case .imageCreationFailed(let size):
            return "Could not create \(size)x\(size) icon image."
        case .pngDestinationFailed(let url):
            return "Could not create PNG destination: \(url.path)"
        case .pngWriteFailed(let url):
            return "Could not write PNG: \(url.path)"
        case .icnsWriteFailed(let url):
            return "Could not write ICNS: \(url.path)"
        }
    }
}

private struct IconsetEntry {
    let filename: String
    let pixels: Int
}

private struct ICNSEntry {
    let type: String
    let pixels: Int
}

private let iconsetEntries = [
    IconsetEntry(filename: "icon_16x16.png", pixels: 16),
    IconsetEntry(filename: "icon_16x16@2x.png", pixels: 32),
    IconsetEntry(filename: "icon_32x32.png", pixels: 32),
    IconsetEntry(filename: "icon_32x32@2x.png", pixels: 64),
    IconsetEntry(filename: "icon_128x128.png", pixels: 128),
    IconsetEntry(filename: "icon_128x128@2x.png", pixels: 256),
    IconsetEntry(filename: "icon_256x256.png", pixels: 256),
    IconsetEntry(filename: "icon_256x256@2x.png", pixels: 512),
    IconsetEntry(filename: "icon_512x512.png", pixels: 512),
    IconsetEntry(filename: "icon_512x512@2x.png", pixels: 1024),
]

private let icnsEntries = [
    ICNSEntry(type: "icp4", pixels: 16),
    ICNSEntry(type: "icp5", pixels: 32),
    ICNSEntry(type: "ic11", pixels: 32),
    ICNSEntry(type: "ic12", pixels: 64),
    ICNSEntry(type: "ic07", pixels: 128),
    ICNSEntry(type: "ic08", pixels: 256),
    ICNSEntry(type: "ic13", pixels: 256),
    ICNSEntry(type: "ic09", pixels: 512),
    ICNSEntry(type: "ic14", pixels: 512),
    ICNSEntry(type: "ic10", pixels: 1024),
]

private func color(_ hex: UInt32, alpha: CGFloat = 1.0) -> CGColor {
    let red = CGFloat((hex >> 16) & 0xff) / 255.0
    let green = CGFloat((hex >> 8) & 0xff) / 255.0
    let blue = CGFloat(hex & 0xff) / 255.0
    return CGColor(red: red, green: green, blue: blue, alpha: alpha)
}

private func makeIcon(size: Int) throws -> CGImage {
    let side = CGFloat(size)
    guard
        let context = CGContext(
            data: nil,
            width: size,
            height: size,
            bitsPerComponent: 8,
            bytesPerRow: 0,
            space: CGColorSpaceCreateDeviceRGB(),
            bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
        )
    else {
        throw IconError.imageCreationFailed(size)
    }

    context.clear(CGRect(x: 0, y: 0, width: side, height: side))
    context.translateBy(x: 0, y: side)
    context.scaleBy(x: 1, y: -1)
    context.setAllowsAntialiasing(true)
    context.setShouldAntialias(true)

    let baseInset = max(1, floor(side * 0.055))
    let baseRect = CGRect(
        x: baseInset,
        y: baseInset,
        width: side - (baseInset * 2),
        height: side - (baseInset * 2)
    )
    let baseRadius = max(4, floor(side * 0.22))
    let basePath = CGPath(
        roundedRect: baseRect,
        cornerWidth: baseRadius,
        cornerHeight: baseRadius,
        transform: nil
    )

    context.setShadow(
        offset: CGSize(width: 0, height: max(1, side * 0.018)),
        blur: max(1, side * 0.028),
        color: color(0x000000, alpha: 0.28)
    )
    context.addPath(basePath)
    context.setFillColor(color(0x10131d))
    context.fillPath()
    context.setShadow(offset: .zero, blur: 0, color: nil)

    let highlightHeight = max(1, floor(side * 0.022))
    context.setFillColor(color(0xffffff, alpha: 0.16))
    context.fill(
        CGRect(
            x: floor(side * 0.13),
            y: floor(side * 0.115),
            width: floor(side * 0.74),
            height: highlightHeight
        )
    )

    let palette: [Character: CGColor] = [
        "A": color(0x00d1ff),
        "B": color(0x3b82f6),
        "C": color(0x6366f1),
        "D": color(0xa855f7),
        "E": color(0xec4899),
        "F": color(0xf43f5e),
        "G": color(0xf97316),
        "H": color(0xfacc15),
        "I": color(0x84cc16),
        "J": color(0x22c55e),
        "K": color(0x14b8a6),
        "L": color(0xf8fafc),
        "M": color(0x38bdf8),
        "N": color(0xfb7185),
    ]
    let pixels = [
        "AABCDEF G".replacingOccurrences(of: " ", with: ""),
        "KABCDEGH",
        "KABLLDGH",
        "JKAHHDEG",
        "IJKBCDEF",
        "HIJKBCDE",
        "GHIJKABC",
        "NGHIJKAB",
    ]

    context.setAllowsAntialiasing(false)
    context.setShouldAntialias(false)

    let gridSize = 8
    let gap = max(0, floor(side / 42))
    let cell = max(1, floor((side * 0.72 - (gap * CGFloat(gridSize - 1))) / CGFloat(gridSize)))
    let gridPixels = (cell * CGFloat(gridSize)) + (gap * CGFloat(gridSize - 1))
    let start = floor((side - gridPixels) / 2)

    for (row, line) in pixels.enumerated() {
        for (column, key) in Array(line).enumerated() {
            guard let fill = palette[key] else {
                continue
            }

            context.setFillColor(fill)
            context.fill(
                CGRect(
                    x: start + (CGFloat(column) * (cell + gap)),
                    y: start + (CGFloat(row) * (cell + gap)),
                    width: cell,
                    height: cell
                )
            )
        }
    }

    context.setFillColor(color(0x000000, alpha: 0.28))
    context.fill(
        CGRect(
            x: start,
            y: start + gridPixels - max(1, floor(side * 0.018)),
            width: gridPixels,
            height: max(1, floor(side * 0.018))
        )
    )

    guard let image = context.makeImage() else {
        throw IconError.imageCreationFailed(size)
    }

    return image
}

private func pngData(for image: CGImage) throws -> Data {
    let data = NSMutableData()
    guard let destination = CGImageDestinationCreateWithData(
        data as CFMutableData,
        UTType.png.identifier as CFString,
        1,
        nil
    ) else {
        throw IconError.pngDestinationFailed(URL(fileURLWithPath: "<memory>"))
    }

    CGImageDestinationAddImage(destination, image, nil)
    if !CGImageDestinationFinalize(destination) {
        throw IconError.pngWriteFailed(URL(fileURLWithPath: "<memory>"))
    }

    return data as Data
}

private func writePNG(_ data: Data, to url: URL) throws {
    do {
        try data.write(to: url)
    } catch {
        throw IconError.pngWriteFailed(url)
    }
}

private func appendASCII(_ string: String, to data: inout Data) {
    data.append(string.data(using: .ascii)!)
}

private func appendUInt32BigEndian(_ value: UInt32, to data: inout Data) {
    var bigEndianValue = value.bigEndian
    withUnsafeBytes(of: &bigEndianValue) { bytes in
        data.append(contentsOf: bytes)
    }
}

private func writeICNS(_ pngsBySize: [Int: Data], to outputURL: URL) throws {
    var chunks = Data()

    for entry in icnsEntries {
        guard let png = pngsBySize[entry.pixels] else {
            continue
        }

        appendASCII(entry.type, to: &chunks)
        appendUInt32BigEndian(UInt32(8 + png.count), to: &chunks)
        chunks.append(png)
    }

    var icns = Data()
    appendASCII("icns", to: &icns)
    appendUInt32BigEndian(UInt32(8 + chunks.count), to: &icns)
    icns.append(chunks)

    do {
        try icns.write(to: outputURL)
    } catch {
        throw IconError.icnsWriteFailed(outputURL)
    }
}

private func main() throws {
    guard CommandLine.arguments.count == 2 else {
        throw IconError.missingOutputPath
    }

    let outputURL = URL(fileURLWithPath: CommandLine.arguments[1])
    let fileManager = FileManager.default
    let tempURL = fileManager.temporaryDirectory
        .appendingPathComponent("pxl-icon-\(UUID().uuidString)", isDirectory: true)
    let iconsetURL = tempURL.appendingPathComponent("AppIcon.iconset", isDirectory: true)
    let keepIconset = ProcessInfo.processInfo.environment["PXL_KEEP_ICONSET"] == "1"

    try fileManager.createDirectory(
        at: iconsetURL,
        withIntermediateDirectories: true
    )
    defer {
        if keepIconset {
            print("Kept \(iconsetURL.path)")
        } else {
            try? fileManager.removeItem(at: tempURL)
        }
    }

    try? fileManager.removeItem(at: outputURL)
    try fileManager.createDirectory(
        at: outputURL.deletingLastPathComponent(),
        withIntermediateDirectories: true
    )

    var pngsBySize: [Int: Data] = [:]
    for size in Set(iconsetEntries.map(\.pixels)).sorted() {
        let image = try makeIcon(size: size)
        pngsBySize[size] = try pngData(for: image)
    }

    for entry in iconsetEntries {
        guard let data = pngsBySize[entry.pixels] else {
            continue
        }

        try writePNG(
            data,
            to: iconsetURL.appendingPathComponent(entry.filename, isDirectory: false)
        )
    }

    try writeICNS(pngsBySize, to: outputURL)
    print("Wrote \(outputURL.path)")
}

do {
    try main()
} catch {
    fputs("error: \(error)\n", stderr)
    exit(1)
}
