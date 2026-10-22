import AppKit

// Where TextKit says an attachment past a tab stands when it asks for the attachment's bounds,
// and where it then draws it, in TextKit 2 and TextKit 1. No window or view is needed.
// Findings: knowledge/apple/textkit-layout.md#textkit-2-sizes-an-attachment-past-a-tab-from-the-lines-start
//
// Usage: swift textkit-tab-attachment-position.swift [--calls]
//
// TextKit 2 (NSTextContentStorage, NSTextLayoutManager and a plain NSTextContainer): the sizing
// position is what attachmentBounds(for:location:textContainer:proposedLineFragment:position:)
// is passed last; the drawn frame is the layout fragment's frame plus frameForTextAttachment(at:),
// checked against the line fragment's typographic bounds plus locationForCharacter(at:).
// TextKit 1 (NSLayoutManager): the sizing position is the glyphPosition passed to
// attachmentBounds(for:proposedLineFragment:glyphPosition:characterIndex:); the drawn frame is
// boundingRect(forGlyphRange:in:).
//
// Left to right a place is the attachment's left edge, x from the container's left. Right to
// left it is the attachment's right edge, as a distance from the container's right. The sizing
// position is printed as TextKit gives it.

let containerWidth: CGFloat = 720
let attachmentSize = CGSize(width: 50, height: 10)
let font = NSFont.systemFont(ofSize: 16)
let showCalls = CommandLine.arguments.contains("--calls")

final class Probe: NSTextAttachment {
    var textKit2Calls: [(proposed: CGRect, position: CGPoint)] = []
    var textKit1Calls: [(proposed: CGRect, position: CGPoint)] = []
    init() { super.init(data: nil, ofType: nil) }
    required init?(coder: NSCoder) { nil }
    override func attachmentBounds(for attributes: [NSAttributedString.Key: Any], location: any NSTextLocation,
                                   textContainer: NSTextContainer?, proposedLineFragment: CGRect,
                                   position: CGPoint) -> CGRect {
        textKit2Calls.append((proposedLineFragment, position))
        return CGRect(origin: .zero, size: attachmentSize)
    }
    override func attachmentBounds(for textContainer: NSTextContainer?, proposedLineFragment lineFrag: CGRect,
                                   glyphPosition position: CGPoint, characterIndex charIndex: Int) -> CGRect {
        textKit1Calls.append((lineFrag, position))
        return CGRect(origin: .zero, size: attachmentSize)
    }
    override func viewProvider(for parentView: NSView?, location: any NSTextLocation,
                               textContainer: NSTextContainer?) -> NSTextAttachmentViewProvider? { nil }
}

struct Case {
    var name: String
    var rtl = false
    var first: CGFloat              // firstLineHeadIndent, F
    var head: CGFloat               // headIndent, H
    var tail: CGFloat = 0           // the inset at the trailing edge, T (tailIndent = -T)
    var stops: [CGFloat] = []       // explicit tab stops; none leaves the default interval
    var interval: CGFloat = 36      // defaultTabInterval
    var alignment = NSTextAlignment.natural
    var prefix: String              // the text before the attachment
}

func paragraph(_ c: Case, attachment: NSTextAttachment?) -> (NSAttributedString, Int) {
    let style = NSMutableParagraphStyle()
    style.baseWritingDirection = c.rtl ? .rightToLeft : .leftToRight
    style.firstLineHeadIndent = c.first
    style.headIndent = c.head
    style.tailIndent = -c.tail
    style.tabStops = c.stops.map { NSTextTab(textAlignment: c.alignment, location: $0, options: [:]) }
    style.defaultTabInterval = c.interval
    let attributes: [NSAttributedString.Key: Any] = [.font: font, .paragraphStyle: style]
    let string = NSMutableAttributedString(string: c.prefix, attributes: attributes)
    let index = string.length
    // Without an attachment, a letter of the paragraph's own direction stands in its place.
    let item = attachment.map { NSMutableAttributedString(attachment: $0) } ?? NSMutableAttributedString(string: c.rtl ? "\u{5D0}" : "X")
    item.addAttributes(attributes, range: NSRange(location: 0, length: item.length))
    string.append(item)
    string.append(NSAttributedString(string: c.rtl ? " \u{5E1}\u{5D5}\u{5E3}" : " end", attributes: attributes))
    return (string, index)
}

/// TextKit 2's frame for the attachment at `index`, and the x of the character there by way of
/// its line fragment, both in container coordinates.
func textKit2(_ string: NSAttributedString, index: Int) -> (frame: CGRect, characterX: CGFloat) {
    let storage = NSTextContentStorage()
    let manager = NSTextLayoutManager()
    storage.addTextLayoutManager(manager)
    let container = NSTextContainer(size: CGSize(width: containerWidth, height: 1_000_000))
    container.lineFragmentPadding = 0
    manager.textContainer = container
    storage.attributedString = string
    manager.ensureLayout(for: manager.documentRange)
    let location = storage.location(storage.documentRange.location, offsetBy: index)!
    var frame = CGRect.null, characterX = CGFloat.nan
    manager.enumerateTextLayoutFragments(from: manager.documentRange.location, options: [.ensuresLayout]) { fragment in
        guard fragment.rangeInElement.contains(location) else { return true }
        let origin = fragment.layoutFragmentFrame.origin
        frame = fragment.frameForTextAttachment(at: location).offsetBy(dx: origin.x, dy: origin.y)
        let local = index - storage.offset(from: storage.documentRange.location, to: fragment.rangeInElement.location)
        for line in fragment.textLineFragments where NSLocationInRange(local, line.characterRange) {
            characterX = origin.x + line.typographicBounds.minX + line.locationForCharacter(at: local).x
        }
        return false
    }
    return (frame, characterX)
}

/// TextKit 1's frame for the glyph of the character at `index`, in container coordinates.
func textKit1(_ string: NSAttributedString, index: Int) -> CGRect {
    let storage = NSTextStorage(attributedString: string)
    let manager = NSLayoutManager()
    storage.addLayoutManager(manager)
    let container = NSTextContainer(size: CGSize(width: containerWidth, height: 1_000_000))
    container.lineFragmentPadding = 0
    manager.addTextContainer(container)
    manager.ensureLayout(for: container)
    let glyph = manager.glyphIndexForCharacter(at: index)
    return manager.boundingRect(forGlyphRange: NSRange(location: glyph, length: 1), in: container)
}

func f(_ v: CGFloat) -> String { v.isNaN ? "nan" : String(format: "%.2f", v) }
func r(_ rect: CGRect) -> String { "\(f(rect.minX))…\(f(rect.maxX))" }

let cases: [Case] = [
    Case(name: "marker tab: F 22.14 < H 32, one stop at H", first: 22.14, head: 32, stops: [32], prefix: "•\t"),
    Case(name: "marker tab: F 10 < H 40, one stop at H", first: 10, head: 40, stops: [40], prefix: "•\t"),
    Case(name: "marker tab: F 10 < H 40, one stop at H, T 22", first: 10, head: 40, tail: 22, stops: [40], prefix: "•\t"),
    Case(name: "marker tab: F 0 < H 40, one stop at H", first: 0, head: 40, stops: [40], prefix: "•\t"),
    Case(name: "second line (after U+2028): F 10, H 40, one stop at 80", first: 10, head: 40, stops: [80], prefix: "•\u{2028}\t"),
    Case(name: "default interval 36: F 10 < H 40, no stops", first: 10, head: 40, prefix: "•\t"),
    Case(name: "default interval 36: F 18 < H 40, no stops", first: 18, head: 40, prefix: "•\t"),
    Case(name: "default interval 36: F = H = 40, no stops", first: 40, head: 40, prefix: "\t"),
    Case(name: "default interval 30.89: F = H = 40, no stops", first: 40, head: 40, interval: 30.89, prefix: "\t"),
    Case(name: "F = H = 40, one stop at H", first: 40, head: 40, stops: [40], prefix: "•\t"),
    Case(name: "F = H = 50, one stop at 30, behind the marker", first: 50, head: 50, stops: [30], prefix: "•\t"),
    Case(name: "F 10 < H 40, one stop at 12, behind the marker", first: 10, head: 40, stops: [12], prefix: "•\t"),
    Case(name: "no tab: F 10, the attachment opens the line", first: 10, head: 40, stops: [40], prefix: ""),
    Case(name: "no tab: F 10, after \"ab\"", first: 10, head: 40, stops: [40], prefix: "ab"),
    Case(name: "rtl marker tab: F 10 < H 40, one stop at H", rtl: true, first: 10, head: 40, stops: [40], prefix: "•\t"),
    Case(name: "rtl marker tab: F 10 < H 40, one stop at H, left-aligned", rtl: true, first: 10, head: 40, stops: [40],
         alignment: .left, prefix: "•\t"),
    Case(name: "rtl marker tab: F 10 < H 40, one stop at H, T 22", rtl: true, first: 10, head: 40, tail: 22, stops: [40], prefix: "•\t"),
    Case(name: "rtl F = H = 40, one stop at H", rtl: true, first: 40, head: 40, stops: [40], prefix: "•\t"),
    Case(name: "rtl default interval 36: F 10 < H 40, no stops", rtl: true, first: 10, head: 40, prefix: "•\t"),
    Case(name: "rtl default interval 36: F = H = 40, no stops", rtl: true, first: 40, head: 40, prefix: "\t"),
    Case(name: "rtl default interval 36: F = H = 40, no stops, T 22", rtl: true, first: 40, head: 40, tail: 22, prefix: "\t"),
    Case(name: "rtl no tab: F 10, the attachment opens the line", rtl: true, first: 10, head: 40, stops: [40], prefix: ""),
    Case(name: "rtl no tab: F 10, T 22, the attachment opens the line", rtl: true, first: 10, head: 40, tail: 22, stops: [40], prefix: ""),
]

let bullet = ("•" as NSString).size(withAttributes: [.font: font]).width
print("macOS \(ProcessInfo.processInfo.operatingSystemVersionString); \(font.fontName) 16 pt, bullet \(f(bullet)) pt wide;"
      + " container \(f(containerWidth)) pt, lineFragmentPadding 0; attachment \(f(attachmentSize.width)) pt wide")
print("case | TK2 sizing position.x | TK2 drawn | TK1 sizing glyphPosition.x | TK1 drawn | TK2 frame, TK1 frame")
for c in cases {
    let probe = Probe()
    let (string, index) = paragraph(c, attachment: probe)
    let two = textKit2(string, index: index)
    let one = textKit1(string, index: index)
    let control = textKit2(paragraph(c, attachment: nil).0, index: index).characterX
    // The place each engine draws the attachment, by its leading edge.
    func place(_ frame: CGRect) -> CGFloat { c.rtl ? containerWidth - frame.maxX : frame.minX }
    let characterX = c.rtl ? containerWidth - two.characterX : two.characterX
    let sized = probe.textKit2Calls.last?.position.x ?? .nan
    print("\(c.name) | \(f(sized)) | \(f(place(two.frame))) | \(f(probe.textKit1Calls.last?.position.x ?? .nan))"
          + " | \(f(place(one))) | \(r(two.frame)), \(r(one))")
    if abs(characterX - place(two.frame)) > 0.01 { print("  line fragment disagrees: \(f(characterX))") }
    if showCalls {
        for call in probe.textKit2Calls { print("  TK2 call: proposed \(r(call.proposed)), position.x \(f(call.position.x))") }
        for call in probe.textKit1Calls { print("  TK1 call: proposed \(r(call.proposed)), glyphPosition.x \(f(call.position.x))") }
        print("  TK2 with a letter in place of the attachment: leading edge \(f(c.rtl ? containerWidth - control : control))")
    }
}
