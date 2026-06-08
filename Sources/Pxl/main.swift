import AppKit
import Darwin
import Foundation

private enum LauncherError: Error, CustomStringConvertible {
    case missingResourcesDirectory
    case missingFile(URL)
    case cannotCreateLogDirectory(URL)
    case cannotOpenLog(URL, Int32)
    case cannotRedirectLog(URL, Int32)
    case execFailed(String, Int32)

    var description: String {
        switch self {
        case .missingResourcesDirectory:
            return "Could not locate the application Resources directory."
        case .missingFile(let url):
            return "Could not find required bundled file:\n\(url.path)"
        case .cannotCreateLogDirectory(let url):
            return "Could not create the launcher log directory:\n\(url.path)"
        case .cannotOpenLog(let url, let errorNumber):
            return "Could not open the launcher log:\n\(url.path)\n\n\(String(cString: strerror(errorNumber)))"
        case .cannotRedirectLog(let url, let errorNumber):
            return "Could not redirect launcher output to:\n\(url.path)\n\n\(String(cString: strerror(errorNumber)))"
        case .execFailed(let path, let errorNumber):
            return "Could not replace the launcher process with:\n\(path)\n\n\(String(cString: strerror(errorNumber)))"
        }
    }
}

private struct LaunchRequest {
    let executableURL: URL
    let arguments: [String]
    let environment: [String: String]
    let logURL: URL
}

private final class AppDelegate: NSObject, NSApplicationDelegate {
    private let noFileLaunchDelay: TimeInterval = 0.6
    private var didReceiveOpenFiles = false
    private var didStartPxl = false

    func applicationDidFinishLaunching(_ notification: Notification) {
        let commandLineArguments = CommandLine.arguments.dropFirst().filter { argument in
            !argument.hasPrefix("-psn_")
        }
        if !commandLineArguments.isEmpty {
            _ = startPxl(arguments: commandLineArguments)
            return
        }

        DispatchQueue.main.asyncAfter(deadline: .now() + noFileLaunchDelay) { [weak self] in
            guard let self else {
                return
            }

            if !self.didReceiveOpenFiles && !self.didStartPxl {
                _ = self.startPxl(arguments: [])
            }
        }
    }

    func application(_ sender: NSApplication, openFiles filenames: [String]) {
        didReceiveOpenFiles = true

        guard !filenames.isEmpty else {
            sender.reply(toOpenOrPrint: .failure)
            return
        }

        guard !didStartPxl else {
            sender.reply(toOpenOrPrint: .failure)
            showError(
                title: "pxl is already running",
                message: "Quit the current pxl session before opening another file set."
            )
            return
        }

        _ = startPxl(arguments: filenames, openFilesSender: sender)
    }

    @discardableResult
    private func startPxl(
        arguments: [String],
        openFilesSender: NSApplication? = nil
    ) -> Bool {
        do {
            let request = try prepareLaunch(arguments: arguments)
            openFilesSender?.reply(toOpenOrPrint: .success)
            try execLaunch(request)
        } catch {
            openFilesSender?.reply(toOpenOrPrint: .failure)
            showError(title: "Could not start pxl", message: "\(error)")
            NSApplication.shared.terminate(nil)
            return false
        }
    }

    private func prepareLaunch(arguments: [String]) throws -> LaunchRequest {
        didStartPxl = true

        guard let resourcesURL = Bundle.main.resourceURL else {
            throw LauncherError.missingResourcesDirectory
        }

        let uvURL = resourcesURL.appendingPathComponent("uv", isDirectory: false)
        let scriptURL = resourcesURL.appendingPathComponent("pxl.py", isDirectory: false)

        try requireExistingFile(uvURL)
        try requireExistingFile(scriptURL)

        let logURL = try prepareLogFile()
        let header = """
        pxl launcher exec at \(Date())
        uv: \(uvURL.path)
        script: \(scriptURL.path)
        arguments:
        \(arguments.map { "  \($0)" }.joined(separator: "\n"))

        """
        try writeHeader(header, to: logURL)

        var environment = ProcessInfo.processInfo.environment
        environment["PYTHONUNBUFFERED"] = "1"
        environment["PXL_MACOS_APP_BUNDLE"] = Bundle.main.bundleURL.path
        environment["PXL_MACOS_APP_NAME"] =
            Bundle.main.object(forInfoDictionaryKey: "CFBundleDisplayName") as? String ?? "Pxl"
        environment["UV_NO_PROGRESS"] = "1"

        let launcherName = Bundle.main.object(forInfoDictionaryKey: "CFBundleName") as? String ?? "Pxl"
        return LaunchRequest(
            executableURL: uvURL,
            arguments: [launcherName, "run", "--gui-script", scriptURL.path] + arguments,
            environment: environment,
            logURL: logURL
        )
    }

    private func prepareLogFile() throws -> URL {
        let fileManager = FileManager.default
        guard let cachesURL = fileManager.urls(for: .cachesDirectory, in: .userDomainMask).first else {
            throw LauncherError.cannotCreateLogDirectory(URL(fileURLWithPath: NSHomeDirectory()))
        }

        let logDirectory = cachesURL.appendingPathComponent("pxl", isDirectory: true)
        do {
            try fileManager.createDirectory(
                at: logDirectory,
                withIntermediateDirectories: true
            )
        } catch {
            throw LauncherError.cannotCreateLogDirectory(logDirectory)
        }

        let logURL = logDirectory.appendingPathComponent("pxl-launcher.log", isDirectory: false)
        fileManager.createFile(atPath: logURL.path, contents: nil)
        return logURL
    }

    private func writeHeader(_ header: String, to logURL: URL) throws {
        guard let data = header.data(using: .utf8) else {
            return
        }

        do {
            try data.write(to: logURL)
        } catch {
            throw LauncherError.cannotOpenLog(logURL, errno)
        }
    }

    private func redirectOutput(to logURL: URL) throws {
        let fileDescriptor = Darwin.open(
            logURL.path,
            O_WRONLY | O_CREAT | O_APPEND,
            S_IRUSR | S_IWUSR | S_IRGRP | S_IROTH
        )
        guard fileDescriptor >= 0 else {
            throw LauncherError.cannotOpenLog(logURL, errno)
        }

        if dup2(fileDescriptor, STDOUT_FILENO) < 0 {
            let errorNumber = errno
            close(fileDescriptor)
            throw LauncherError.cannotRedirectLog(logURL, errorNumber)
        }

        if dup2(fileDescriptor, STDERR_FILENO) < 0 {
            let errorNumber = errno
            close(fileDescriptor)
            throw LauncherError.cannotRedirectLog(logURL, errorNumber)
        }

        close(fileDescriptor)
    }

    private func execLaunch(_ request: LaunchRequest) throws -> Never {
        try redirectOutput(to: request.logURL)
        try execExecutable(
            at: request.executableURL.path,
            arguments: request.arguments,
            environment: request.environment
        )
    }

    private func execExecutable(
        at path: String,
        arguments: [String],
        environment: [String: String]
    ) throws -> Never {
        var argv: [UnsafeMutablePointer<CChar>?] = arguments.map { strdup($0) }
        argv.append(nil)
        defer {
            for pointer in argv {
                free(pointer)
            }
        }

        let environmentStrings = environment
            .map { "\($0.key)=\($0.value)" }
            .sorted()
        var envp: [UnsafeMutablePointer<CChar>?] = environmentStrings.map { strdup($0) }
        envp.append(nil)
        defer {
            for pointer in envp {
                free(pointer)
            }
        }

        try argv.withUnsafeMutableBufferPointer { argvBuffer in
            try envp.withUnsafeMutableBufferPointer { envBuffer in
                execve(path, argvBuffer.baseAddress, envBuffer.baseAddress)
                throw LauncherError.execFailed(path, errno)
            }
        }

        fatalError("execve unexpectedly returned without replacing the process.")
    }

    private func requireExistingFile(_ url: URL) throws {
        var isDirectory: ObjCBool = false
        let exists = FileManager.default.fileExists(atPath: url.path, isDirectory: &isDirectory)
        if !exists || isDirectory.boolValue {
            throw LauncherError.missingFile(url)
        }
    }

    private func showError(title: String, message: String) {
        NSApplication.shared.activate(ignoringOtherApps: true)

        let alert = NSAlert()
        alert.messageText = title
        alert.informativeText = message
        alert.alertStyle = .critical
        alert.addButton(withTitle: "OK")
        alert.runModal()
    }
}

private let application = NSApplication.shared
private let delegate = AppDelegate()
application.setActivationPolicy(.accessory)
application.delegate = delegate
application.finishLaunching()
application.run()
