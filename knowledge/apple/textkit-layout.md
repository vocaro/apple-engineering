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
