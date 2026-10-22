# TextKit layout

These mechanisms and lessons apply when the stated capability is present. Original
measurements establish their recorded platform and workload; they do not establish
universal behavior on later operating systems or in a different application.

These lessons come from a reader app that lays out long texts with TextKit 2 in `UITextView` and
`NSTextView`, table cells with TextKit 1, and pages sliced from one layout. Unless a line says
otherwise they were observed with the macOS 27.0 and iOS 27.0 SDKs in unit tests and in the
apps, October 2026. Bidi, collation, font metrics and spoken language are in [text layout and
Unicode](text-layout-and-unicode.md); stack depth in layout recursion is in [stack and work
bounds](stack-and-work-bounds.md).

## Accessibility observation can change layout

TextKit 2 lays out only what is near the viewport and estimates where the rest of the text
stands. A query that asks where text is finishes that lazy layout, and the finished layout moves
what was placed by estimate. A diagnostic or assistive observer is therefore not passive.

- VoiceOver on iOS over UIKit's own paragraph elements, and a UI test's snapshot, ask where
  every paragraph is. Mac VoiceOver's insertion-point line query lays out all the text above the
  view (below). Either replaces the estimates the visible lines were placed by.
- UIKit goes on drawing the viewport's paragraphs where they were, over the place the finished
  layout gives other text. Read the visible range from the fragments the viewport laid out, once
  it has been laid out again where the view stands. Answer point hit tests for characters, links
  and images from those viewport fragments too, so that a tap answers for the text drawn there.
- AppKit would draw the finished layout at the old offset, a chapter away, at the next scroll.
  While the view has not moved since it was last read, scroll first by as much as the first
  visible line has moved.
- AppKit moves the view itself by a fraction of a point when it aligns the offset to the pixel
  grid at a scroll view's first display. Treat a view within a point of where it was last read
  as not moved.
- On the Mac the first wheel or trackpad event arrives before AppKit scrolls. Record the first
  line at that event and at each bounds change, not only when a throttled location report fires,
  so that a read straight after a scroll keeps the new line.
- Mac VoiceOver asks a text view which line its insertion point is on
  (`AXInsertionPointLineNumber`), and AppKit counts lines from the first, which lays out all the
  text above. After a link far below laid-out text was shown, the bounds VoiceOver asked for
  next put the shown row's paragraph 1,430 points below where the view drew it (macOS 27.0.1,
  hosted runner). Hold the view to its text before answering a client's questions about what is
  on screen and where (children, range bounds, an element's place), and answer a range's bounds
  a second time when answering is what moved the text.
- Straight after such a layout the document can still report its old height, which stops a
  scroll short of a line near its end. Scroll again once the viewport laid out where the scroll
  stopped has given the document its height.

A test can stand in for the reader with `firstRect(for:)` on UIKit and
`accessibilityFrame(for:)` on AppKit for every paragraph, which lays out the whole text. That is
stronger than VoiceOver's own line query, which establishes completed layout above the viewport
only.

## Lay out through a far target before scrolling to it

Far from what is laid out TextKit 2 only estimates where text is, and the viewport's layout
estimates differently. A long jump that scrolls to an estimated place can land on another line.

- From text before the target, lay out through the target in one run and scroll to its now exact
  line. From text past it, climb above it first.
- Check which line the top of the view shows after the scroll, in a bounded correction loop that
  allows a short last screen where scrolling is clamped. If estimates cannot align it, or
  TextKit 2 lays the line over other text, load the text afresh and show the position again.
- TextKit only estimates the height of the text above the viewport, so a line can be screens
  away from where a precomputed plan has it. Anything planned for the whole text (floats, boxes)
  must be applied from where each paragraph's own first line is laid out.
- The scroll view reports an offset change before the text is laid out at the new place. Look
  for what depends on the visible lines (mounted views, hit-test surfaces) again once the move
  has ended and the visible range is read from the layout as drawn.

## AppKit and UIKit text views scroll themselves

- `-[NSTextView viewDidEndLiveResize]` scrolls the paragraph under the clip view's top edge to
  that edge, from the paragraph's first line, whenever a live resize ends: a drag of the
  window's edge, `setFrame(_:display:animate:)` with animation, or a size set through the
  accessibility API (macOS 27.0). A text at its top moved down by its top margin, and one in
  mid-paragraph went back to the paragraph's start, further at each resize. AppKit tells a view
  that the resize has ended before it tells that view's subviews, so a container can record
  where the text stands before the text view scrolls and put it back straight after, before
  anything is drawn.
- A scroll AppKit makes while it lays the whole text out again, as after a change of text size,
  looks to the app like the person's.
- A legacy scroll bar appears once the text is longer than the window, which is after the text
  container's width was first set from the clip view. Measure the column from the scroll
  viewport's actual extent, including width a legacy scroll bar reserves, and lay the text out
  again at the narrower width before the first draw. A scroll bar preference change needs the
  same.
- Nothing lays out an AppKit text view when a window toolbar changes its scroll view's insets.
  UIKit reports the scrolling caused by an inset change, such as a bar hiding, once the change
  is over, while the text under it is still being laid out again.

## TextKit 2 redraws a fragment when its layout changes, not when its attributes do

Rendering attributes, such as search and highlight colors, never change the text. TextKit 2
redraws a laid-out fragment when its layout changes and not when a rendering attribute does, so
after changing them ask for the fragments on screen to be drawn again.

## TextKit 1 and TextKit 2 apply paragraph indents differently

- TextKit 2 on iOS has no `NSTextTable`. Tables drawn natively need their own cell layout, such
  as TextKit 1 inside an attachment.
- TextKit 1 applies a paragraph's indents itself. Where indents (a nested list's among them)
  take the whole column left inside a cell, it set each glyph on a line of its own past the
  column, and a cell measured its first line alone. Clamp exhausted indents so the paragraph
  keeps a column one glyph wide.
- A tab stop is a distance from the paragraph's leading edge in TextKit 1, the right edge in
  right-to-left text. TextKit 2, where it applies a right-to-left paragraph's indents itself,
  measured a stop from the first line's start less the tail indent, which set a list item's
  first line a first-line indent further along than its wrapped lines.
- When a text container supplies line rectangles (any container that is not a plain rectangle),
  TextKit wraps a line within its paragraph's indents but aligns and justifies it across the
  whole rectangle it was handed, as if the paragraph had none. Give such a container indent-free
  paragraphs and line rectangles that already leave out the head, first-line and tail indents.
  TextKit breaks a justified paragraph's lines a little differently there; their edges match.
- TextKit gives a paragraph its spacing before only between other paragraphs and after an empty
  one, and drops the spacing before a document's first paragraph. Measure paragraphs the way the
  text will lay them out, container included, or every later box and page moves by the
  difference.

## TextKit 2 sizes an attachment past a tab from the line's start

TextKit 2 asks an attachment for its size with
`attachmentBounds(for:location:textContainer:proposedLineFragment:position:)`. The proposed line
fragment was the whole container, with none of the paragraph's indents taken out, so an
attachment that fills the rest of its line works that out from `position`. Left to right
without a tab, the last call's `position.x` was where TextKit 2 then drew the attachment. Past a
tab it was not. When sizing, TextKit 2 measured the tab's stop from the line's start and added
the line's left indent. When drawing, it measured the stop from the paragraph's edge, as TextKit
1 did both times.

- Past a list marker's tab, in a paragraph whose first-line indent F is less than its head indent
  H and whose one stop is at H, the attachment was sized at F + H and drawn at H. The first-line
  indent was counted twice, so the rest of the line came out F narrower than the room it was
  drawn in: 22.14 points with F 22.14 and H 32. On a later line the head indent was counted
  twice instead.
- Taking the line's left indent off `position` corrects it only where the stop found from the
  line's start is the stop found from the paragraph's edge, as a marker's tab to the head indent
  is. Past a bare tab in a paragraph indented 40 on every line, at a default interval of 36, the
  attachment was sized at 76 and drawn at 72: 4 points off, not 40. Past a stop the marker had
  already passed, the position was short: sized at 22 and drawn at 48. At a default interval with
  F < H and a narrow marker, the two stops were the same and the position was again F too far.
  Recognize a marker's tab by its paragraph (F < H, one stop at H, a tab just before the
  attachment) rather than correcting past every tab.
- TextKit 2 called the method up to three times for each layout, the first at 0. Only the last
  call's `position` fits these rules.
- Right to left, TextKit 2 measured the stop from the line's start both when sizing and when
  drawing. It drew the stop from the first line's start less the tail indent T, as in [the entry
  above](#textkit-1-and-textkit-2-apply-paragraph-indents-differently). It gave `position.x` as
  T, the line's left indent there, plus the advance from the line's start. The room to the left
  of the attachment, taken as the container less F less `position`, matched the drawing without
  a tab and was T short past one. With F 10, H 40, T 22 and the stop at H, the attachment was
  drawn at 642…692, which leaves 670 points to the tail indent; 720 − 10 − 62 is 648. With T 0
  the two agreed.
- TextKit 1's `glyphPosition` was where it drew, the left edge left to right and the right edge
  right to left, except past a `.left` stop right to left (below).
- Two drawing differences appeared along the way. Left to right, TextKit 2 put the next stop
  past the last explicit one at that stop plus the default interval, where TextKit 1 put it at a
  multiple of the interval from the paragraph's edge. Right to left, a `.left` stop gave the same
  TextKit 2 numbers as a `.natural` one, while TextKit 1 set the attachment straight after the
  marker, 17.23 from the edge, instead of at the stop.

A place in the table is the attachment's left edge left to right, and its right edge measured
from the container's right edge right to left; `position.x` is as TextKit 2 passed it. The
default interval is 36 unless stated.

| Paragraph | Before it | TextKit 2 `position.x` | TextKit 2 drew | TextKit 1 drew |
| --- | --- | --- | --- | --- |
| F 22.14, H 32, one stop at H | `•\t` | 54.14 | 32 | 32 |
| F 10, H 40, one stop at H, T 0 or 22 | `•\t` | 50 | 40 | 40 |
| F 0, H 40, one stop at H | `•\t` | 40 | 40 | 40 |
| H 40, one stop at 80, on the second line | `\t` | 120 | 80 | 80 |
| F 10 or 18, H 40, no stops | `•\t` | 46 or 54 | 36 | 36 |
| F = H = 40, no stops | `\t` | 76 | 72 | 72 |
| F = H = 40, no stops, interval 30.89 | `\t` | 70.89 | 61.78 | 61.78 |
| F = H = 40, one stop at H | `•\t` | 80 | 76 | 72 |
| F = H = 50, one stop at 30 | `•\t` | 80 | 66 | 72 |
| F 10, H 40, one stop at 12 | `•\t` | 22 | 48 | 36 |
| F 10, H 40, one stop at H | nothing, or `ab` | 10, 28.03 | 10, 28.03 | 10, 28.03 |
| Right to left: F 10, H 40, one stop at H, T 0 | `•\t` | 40 | 50 | 40 |
| Right to left: the same with T 22 | `•\t` | 62 | 28 | 40 |
| Right to left: F = H = 40, no stops, T 0 or 22 | `\t` | 36 or 58 | 76 or 54 | 72 |
| Right to left: F 10, H 40, one stop at H, T 0 or 22 | nothing | 0 or 22 | 10 | 10 |

Measured 2026-10-22 on macOS 27.2 (26B5091g), Xcode 27.2 (27B5028f) and Swift 6.4 on a
MacBookPro18,2, with [a probe](../../src/swift/TextKit/textkit-tab-attachment-position.swift)
that needs no window: `swift textkit-tab-attachment-position.swift`, and `--calls` to list every
sizing call. It lays out one paragraph with `NSTextContentStorage`, `NSTextLayoutManager` and a
plain `NSTextContainer` 720 points wide with `lineFragmentPadding` 0. The paragraph is in the
16-point system font, with a 50-point attachment followed by text. The drawn place is the layout
fragment's frame plus `frameForTextAttachment(at:)`. It agreed with the line fragment's
`locationForCharacter(at:)`, and with a letter set in the attachment's place. Repeated runs
gave the same numbers. Not measured: iOS, other macOS releases, a text view,
`lineFragmentPadding` other than 0, center, right and decimal stops, a first-line indent greater
than the head indent, and a container that supplies its own line rectangles. The rules above
are inferred from these cases, not from Apple documentation.

A reader met this in list items. Where a table opened an item, its first row came out 22 points
narrower than the item left to right, and 58 right to left in a reader that also moves
right-to-left stops to undo the entry above
([EPUBLib#750](https://github.com/vocaro/EPUBLib/pull/750),
[verification](https://github.com/vocaro/EPUBLib/issues/376#issuecomment-6341970318)). Its first
fix took the left indent off past every tab. Review found that this put a full-width image past
an authored tab 18 points beyond the column, and the fix kept corrects only past a marker's tab.

## A non-rectangular container can ask for lines forever

TextKit keeps asking a text container that is not a plain rectangle for the next line down for
as long as it has set nothing on the line. Text it can set on no line kept it asking without
end: a tab with no stop after it and no default tab interval. Give every paragraph style a
default tab interval, and have the container answer an empty rectangle once it has been asked
for a line at one character some fixed number of times running, which ends the paragraph. In the
corpora such a reader lays out, TextKit asked for one character at most four times running.

## Core Text justification depends on the paragraph's length

Core Text justified a paragraph of up to 8,192 characters as a whole and a longer one line by
line. A slice of a paragraph laid out alone therefore breaks differently from the whole: a
justified slice is justified over the slice, and a continued paragraph starts a fresh line.
Lines before a U+2028 line break were set the same whatever followed the break, which was
checked on every justified paragraph with line breaks in the public book corpora the reader is
tested on and on generated ones; that is an observation, not a documented guarantee. Lines that
hold glyphs from a fallback font, such as CJK text among Latin, laid out differently when
sliced. Lay out each page as it will be shown, with a bounded lookahead, before committing its
boundary.

## A text view takes its layout stack when it is made

- `UITextView` takes its layout manager only when it is created, and an `NSTextView` that shows
  successive pages would have to swap its text container at every turn. A persistent text view
  per column, keeping its TextKit stack, is what preserves selection and VoiceOver's cursor
  across turns. A measured TextKit layout cost about 60 bytes per character, so keeping measured
  layouts for display costs memory in proportion to the text.
- There is no three-point font floor: a fitted 0.849-point font produced a one-point TextKit
  line and glyph box.
- UIKit has no vertical-layout API, but TextKit 2 on iOS lays text out vertically when a text
  container subclass reports vertical orientation, and `NSTextView` stays on TextKit 2 in
  vertical orientation on macOS (a spike, not a shipped path).
