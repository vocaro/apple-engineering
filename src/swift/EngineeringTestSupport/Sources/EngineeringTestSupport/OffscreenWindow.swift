#if os(macOS)
import AppKit
import ApplicationServices

/// In-process test hosting that does not constrain a window back onto a visible screen.
/// This is development/test support and must not be linked into a shipping app target.
@MainActor public final class OffscreenWindow: NSWindow {
    public static let origin = CGPoint(x: -30_000, y: -30_000)
    public static var offscreen: CGPoint { origin }

    public override func constrainFrameRect(_ frameRect: NSRect, to screen: NSScreen?) -> NSRect {
        frameRect
    }

    public override func beginSheet(_ sheetWindow: NSWindow,
        completionHandler handler: ((NSApplication.ModalResponse) -> Void)? = nil) {
        sheetWindow.alphaValue = 0
        sheetWindow.ignoresMouseEvents = true
        super.beginSheet(sheetWindow, completionHandler: handler)
    }
}

/// Reads this process's own accessibility tree from an app-hosted test bundle. In a plain
/// SwiftPM test process the same call returned `kAXErrorNotImplemented` (macOS 27.0), so there
/// `attribute` returns nil; see guides/background-mac-testing.md#test-hosts-and-what-they-reach.
/// It grants no cross-process accessibility access.
@MainActor public enum AccessibilityRead {
    public static func attribute<T>(_ element: AXUIElement, _ name: String) -> T? {
        var value: CFTypeRef?
        guard AXUIElementCopyAttributeValue(element, name as CFString, &value) == .success else { return nil }
        return value as? T
    }
}
#endif
