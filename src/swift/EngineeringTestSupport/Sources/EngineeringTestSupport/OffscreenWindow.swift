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

/// Reads this process's accessibility tree. It grants no cross-process accessibility access.
@MainActor public enum AccessibilityRead {
    public static func attribute<T>(_ element: AXUIElement, _ name: String) -> T? {
        var value: CFTypeRef?
        guard AXUIElementCopyAttributeValue(element, name as CFString, &value) == .success else { return nil }
        return value as? T
    }
}
#endif
