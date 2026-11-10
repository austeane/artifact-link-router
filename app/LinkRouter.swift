// Claude Link Router: a default-browser stand-in.
//
// It receives every http(s) link macOS opens. claude.ai artifact links go to
// ~/.local/bin/claude-artifact-router, which opens them in the browser profile signed in to the
// Claude account that owns them. Every other link, and any artifact link the script cannot place,
// is handed to the real browser unchanged.
//
// Build and install with build.sh in this folder.

import Cocoa

let script = FileManager.default.homeDirectoryForCurrentUser
    .appendingPathComponent(".local/bin/claude-artifact-router").path
let fallbackBrowsers = [
    UserDefaults.standard.string(forKey: "FallbackBrowser") ?? "com.google.Chrome",
    "com.apple.Safari",
]

func isArtifactLink(_ url: URL) -> Bool {
    url.host?.lowercased() == "claude.ai" && url.path.contains("/artifact/")
}

/// True when the script opened the link itself.
func routed(_ url: URL) -> Bool {
    guard FileManager.default.isExecutableFile(atPath: script) else { return false }
    let p = Process()
    p.executableURL = URL(fileURLWithPath: script)
    p.arguments = ["route", url.absoluteString]
    p.standardOutput = FileHandle.nullDevice
    p.standardError = FileHandle.nullDevice
    do { try p.run() } catch { return false }
    let deadline = Date().addingTimeInterval(5)
    while p.isRunning && Date() < deadline { usleep(20_000) }
    if p.isRunning {
        p.terminate()
        return false
    }
    return p.terminationStatus == 0
}

func passThrough(_ urls: [URL]) {
    let ws = NSWorkspace.shared
    let me = Bundle.main.bundleIdentifier
    for id in fallbackBrowsers where id != me {
        if let app = ws.urlForApplication(withBundleIdentifier: id) {
            ws.open(urls, withApplicationAt: app, configuration: NSWorkspace.OpenConfiguration(), completionHandler: nil)
            return
        }
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate {
    var quitTimer: Timer?

    func applicationDidFinishLaunching(_ note: Notification) { quitWhenIdle() }

    func application(_ application: NSApplication, open urls: [URL]) {
        let rest = urls.filter { !(isArtifactLink($0) && routed($0)) }
        if !rest.isEmpty { passThrough(rest) }
        quitWhenIdle()
    }

    /// Stay up briefly so a burst of clicks is fast, then leave nothing running.
    func quitWhenIdle() {
        quitTimer?.invalidate()
        quitTimer = Timer.scheduledTimer(withTimeInterval: 30, repeats: false) { _ in NSApp.terminate(nil) }
    }
}

// ---- command line: default-browser switch ---------------------------------

func currentDefault() -> String {
    let app = NSWorkspace.shared.urlForApplication(toOpen: URL(string: "https://example.com/")!)
    return app.flatMap { Bundle(url: $0)?.bundleIdentifier } ?? "unknown"
}

/// macOS asks the person to confirm an http/https handler change; this waits for their answer.
func makeDefault(_ app: URL) -> Bool {
    var failed = false
    for scheme in ["http", "https"] {
        var done = false
        NSWorkspace.shared.setDefaultApplication(at: app, toOpenURLsWithScheme: scheme) { error in
            if error != nil { failed = true }
            done = true
        }
        let deadline = Date().addingTimeInterval(120)
        while !done && Date() < deadline { RunLoop.current.run(until: Date().addingTimeInterval(0.1)) }
        if !done { failed = true }
    }
    return !failed
}

let args = CommandLine.arguments
if args.contains("--default-status") {
    print(currentDefault())
    exit(0)
}
if args.contains("--make-default") {
    // Remember the browser being replaced: ordinary links keep going to it, and --restore returns to it.
    let previous = currentDefault()
    if previous != "unknown" && previous != Bundle.main.bundleIdentifier {
        UserDefaults.standard.set(previous, forKey: "FallbackBrowser")
        UserDefaults.standard.synchronize()
    }
    let ok = makeDefault(Bundle.main.bundleURL)
    print("default browser: \(currentDefault())")
    exit(ok && currentDefault() == Bundle.main.bundleIdentifier ? 0 : 1)
}
if let i = args.firstIndex(of: "--restore") {
    let id = i + 1 < args.count ? args[i + 1] : fallbackBrowsers[0]
    guard let app = NSWorkspace.shared.urlForApplication(withBundleIdentifier: id) else {
        print("no app with bundle id \(id)")
        exit(2)
    }
    let ok = makeDefault(app)
    print("default browser: \(currentDefault())")
    exit(ok && currentDefault() == id ? 0 : 1)
}

let delegate = AppDelegate()
NSApplication.shared.delegate = delegate
NSApplication.shared.run()
