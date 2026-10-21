# VoiceOver on the Mac

These mechanisms and lessons apply when the stated capability is present. Original
measurements establish their recorded platform and workload; they do not establish
universal behavior on later operating systems or in a different application.

These lessons come from a reader app whose text is AppKit's `NSTextView`, with TextKit 2 and
TextKit 1, and from AppKit's own text view beside it. Unless a line says otherwise they were
heard in October 2026 on GitHub-hosted macOS runners (image 20261006.0244.1, macOS 27.0.1
26A434, Xcode 27.0), with VoiceOver's link verbosity at its default, Speak. Nobody listened: the
record is VoiceOver's phrases and what it asked the app. How such sessions are run is in [Mac
VoiceOver](../../guides/voiceover-mac.md) and the [hosted runner](../../guides/hosted-runner.md)
guides. Tables are in [VoiceOver and
tables](voiceover-tables.md), role words in [accessibility](accessibility.md), and the layout an
accessibility query causes in [TextKit layout](textkit-layout.md).

A text view is one element to VoiceOver, a "text area", which it reads by line and by word
through the text's parameterized attributes. It meets other elements only as children of the
text or as the attachments of characters.

## VoiceOver enters a text view at its insertion point

- VoiceOver enters an `NSTextView` at its insertion point, even in a read-only view that draws
  none. Replacing a text view's text leaves the insertion point at its end. After a move the app
  makes itself (a position shown, a scroll step, new text) put the insertion point at the start
  of the line VoiceOver should enter at. Leave one that a click or VoiceOver placed.
- Once it has been in a text view, VoiceOver keeps a text cursor of its own there, so only a
  first entry shows where the insertion point takes it. Resting on a text view without
  interacting, it re-entered after a page change at its previous character offset, or on the
  last line of a shorter page, until Control-Option-Home. In a workstation session (macOS 27.0
  26A428) a window resize moved a resting cursor to the window's first control.
- Inside the text, VoiceOver follows a moved insertion point only once it has moved in the text
  itself. Straight after entering, it kept its line at AppKit's one `AXSelectedTextChanged`,
  then scrolled the view back to its line by setting the scroll bar's value, which undid the
  app's step. Posting the selection change a second time, before the layout change, brought it
  along (macOS 27.0.1). The logged sessions agree with VoiceOver passing over the first
  selection change after it sets keyboard focus on a text; that this is its rule was not
  established.
- Told that the insertion point moved, VoiceOver says the word beside the new place, 60 to 110
  ms after it began whatever it was saying, which cuts that off. So do not move the insertion
  point when VoiceOver's cursor has gone to an element that is already visible. Posting
  `AXTextSelectionChangedFocus` or `AXTextStateSync` (what WebKit posts), answering a new
  insertion point with no notification, or a layout change naming the text did not move its
  place without the word.
- Its own moves by line leave the insertion point at the end of the line it read, before the
  break, so the first move down from a place reads that line again. A move by line from the
  middle of a line goes to that line's end first. In workstation sessions (macOS 27.0) Read All
  moved the insertion point a sentence at a time.
- VoiceOver's own scrolls arrive as a set of the scroll bar's value, which an app cannot tell
  from a person's scroll.
- AppKit's visible character range counts whole paragraphs, and VoiceOver's first and last
  visible word and a cursor it brings back into view go by it.
- VoiceOver read a word broken across lines without a hyphen as one word (workstation, macOS
  27.0), where iOS reads each line's part (see [VoiceOver on iOS](voiceover-ios.md)).

## Post layout changes from the element that holds the text views

- After each move the app makes itself, post `NSAccessibility.Notification.layoutChanged` naming
  the text view. Without it VoiceOver, back in a text it had left, returned to its own previous
  cursor and scrolled the view there. At a layout change VoiceOver says the item under its
  cursor again, role first.
- With several text views on screen, as the columns of a two-page spread, post a value change
  for each whose text was replaced and a layout change naming the visible ones; without them
  VoiceOver can keep reading a column's previous page. Post the layout change from the nearest
  accessibility ancestor that holds the columns. Posted by the window, it left VoiceOver the
  text cursor it keeps for a column it had left, and it came back at the old offset (macOS
  27.0.1). SwiftUI's hosting view makes a group of a window's content, so a SwiftUI host has
  such an ancestor.
- VoiceOver follows keyboard focus between text views, and stays in the text view it is in when
  their contents change: after a turn made in the second column it read the new second column
  and passed over the first. Move keyboard focus to the column VoiceOver should read.
- VoiceOver gives keyboard focus to each text area it moves to and leaves it there when it comes
  back out. When the app removes that view, focus falls to the window and VoiceOver goes to the
  window's first button. Hand focus to the containing text view as the view leaves its
  superview.

## Links in an AppKit text view are children, not places

AppKit gives a text view's links to an assistive client itself: an element for each, as the link
of its characters in the accessibility string and as a child of the text (TextKit 1 and 2).

- Find Next Link and Find Previous Link move through the text's children and say each link's
  name and "hyperlink". Find Previous Link went forward (macOS 27.0.1), in AppKit's own text
  view as with custom elements. Control-Option-Space follows the link under the cursor, or a
  link on the line the cursor is in. There is no list of links in VoiceOver's rotor.
- Reading by word, by line or in Read All, VoiceOver says a link's words and nothing of the
  link. An element laid over a link's characters was not announced. VoiceOver does announce an
  element given as a character's attachment, so a picture or a hidden label inside a link needs
  a link element as its attachment to be said with "hyperlink".
- AppKit names a link by its characters, so a link that is a picture is named U+FFFC and is
  announced as "hyperlink" alone. A link without size, as over a label that takes no room, is
  not reached. Give link elements of your own in AppKit's place, with AppKit's link role, a name
  made of the link's words and its pictures' text, and a press that follows the link. An element
  that is a link cannot also be an image, so a picture link says "image" in its name, in the
  system's word for one.
- VoiceOver takes an element for a place only when it is among the children of its text. A
  scroll view's children are the links of the paragraphs on screen, so from the last of them
  Find Next Link begins again with the first or says "Last link". To let it go on, add the next
  link below the screen as the last child, as its own element kept by its place in the text.
  Past the last link in a document, beginning again is VoiceOver's own way with the children it
  is given.
- From a link VoiceOver goes on through the children of that link's parent, and from a place in
  the text it takes the first link child wherever its text cursor is. A link inside a nested
  text view, such as a table cell, is found from the page only if the page lists an element for
  it among its own children.
- With its cursor on a link element VoiceOver is not in the text: its next move by word or line
  starts where it last read. Its place in the text follows the insertion point when it is told
  that moved, and nothing else.
- A custom rotor of links puts a list in the rotor, and VoiceOver then uses it for Find Next
  Link as well. With the links' character ranges as results it said no "hyperlink" and found no
  previous link; with the link elements as results it said "Link not found". An answer that is
  not a child of the text was refused.

## VoiceOver focuses only an element that reports its focus

While cursor tracking is on (the default) VoiceOver focuses the element it moves to, and that is
all it tells the app of the move. It gives focus only to an element that answers whether it is
focused (`isAccessibilityFocused`); one that only accepted focus was never given it. An element
off screen can answer the focus by showing itself and putting the insertion point on it. With
cursor tracking off VoiceOver focuses nothing and scrolls to the element itself.

What a probe overrides can change this. A heading element that overrode `isAccessibilityFocused`
only to log it was focused, and overriding AppKit's legacy attribute methods on an
`NSAccessibilityElement` hid its `AXPress` action. Log on the view and leave the elements alone.

## Mac headings need a rotor, rich-text levels and child elements

- A text view has no element for a line, so mark each heading's characters with its level
  (`AXHeadingLevel`) in the rich text a client reads. VoiceOver reads the heading's words on
  arriving and was not heard to say that level; its rotor's Headings list shows it.
- Give each text view an `NSAccessibilityCustomRotor` for headings. VoiceOver's move to the next
  heading and its rotor's list go by it. A heading outside the view is an
  `NSAccessibilityElementLoading` token; VoiceOver asks for the token's element, and then its
  range, only when it moves to that heading, by the move or by a choice from the list. Show the
  heading then. VoiceOver walks the whole list when its rotor opens, so a search must show
  nothing.
- VoiceOver lists a rotor's items by asking for the one after an item that is nowhere (no
  element, no token, the first character and zero length), and then for the one after each item
  it is given. With its cursor resting on a text view it asks from that view at its first
  character and zero length: treat that as the top of the view, not as nowhere. Give each result
  a label, or the list reads every row as the text view's own text.
- With its cursor on a link, which is a child and no place in the text, VoiceOver asks no rotor.
  It looks through the text's children for an element with the heading role after the link, and
  past the last it begins again with the first. Give each heading an element among the children
  too, with AppKit's heading role, the heading's words as its label and its level as its value.
  VoiceOver then says "heading level" and the number before the words.
- VoiceOver opens its rotor on the menu it showed last, and that persists across VoiceOver
  sessions on the same Mac.

## Never offer VoiceOver the accessibility element search

AppKit serves `AXUIElementsForSearchPredicate` through the legacy attribute methods (named since
macOS 26). Offer it from no text view and no element of one:

- VoiceOver asked an element that offers it in place of looking at it, with a query such as
  `{AXDirection = AXDirectionNext; AXResultsLimit = 1; AXSearchKey = (AXHeadingSearchKey)}` and
  no start, then each child after it in turn. A text area that offers it is asked with
  `AXStartRange` or `AXStartElement`.
- A text area that offers it is asked for every kind of item VoiceOver looks for, from changes
  of font or style to plain text, links and graphics, and can answer only with elements.
  VoiceOver's quick-navigation moves then left the text.
- Searches it could not answer, for bold text and for a graphic, were asked thousands of times
  in half a minute until VoiceOver reported the app not responding and could not be turned off.

## Custom actions belong on the text area

VoiceOver's Actions menu (Control-Option-Command-Space) holds the actions of the item under its
cursor, and at every line and word inside a text view that item is the text area.

- Give a text view its commands as `NSAccessibilityCustomAction`s. The cost is "actions
  available" before VoiceOver's hint for the text area, once as it arrives or enters the text,
  and not after each move. A group's own menu lists every action its items offer.
- An item that takes VoiceOver's cursor by itself, as a link reached with Find Next Link, keeps
  its own menu without the text area's actions.
- Make the action's effect inside its handler. `AXPerformAction` returned -25200 when the
  handler returned false, and when the effect was deferred until after the handler returned. In
  a scroll view AppKit returned -25200 for an action whose handler returned true and that
  scrolled, logged as coming from `NSAccessibilityEntryPointPerformAction`; in a page's text
  view it returned 0. Read state after an action instead of trusting the status.
- SwiftUI's named and scroll actions on an `NSViewRepresentable` reach no element when the
  wrapped view is not an accessibility element (see [accessibility](accessibility.md)). A
  SwiftUI scroll view's scroll area has AppKit's four scroll-by-page actions.

## AppKit gives a client the text character for character

AppKit answers every range a client asks for, a line's and a frame's included, one character for
one, so what a client reads must match the text's characters exactly:

- Give each character that must not be read, as text that `visibility: hidden` hides, as a space
  in the value, the strings, the attributed string and the selected text. VoiceOver then passes
  over it by word and by line, and every range still matches.
- Answer the line of the offset after the last character, where the insertion point stands after
  the last word. While a text gave no line there, Read Line said nothing, moves to the line
  above and below did nothing, and VoiceOver counted -9,223,372,036,854,775,808 lines.
- VoiceOver stops at an attachment character (U+FFFC) whatever element the text gives there,
  none included, and at static text without words it stops in silence. To pass a line over, give
  its character and the break after it as spaces and make its line part of the next line. Made
  part of the line before, the line was passed over, but what ended that line could no longer be
  gone into: VoiceOver leaves its place at the end of a line it read and goes into what stands
  there. VoiceOver says of a line what comes before the line's first break.
- Keep the element given for each attachment for as long as its text stands, and give it the
  frame where its character is drawn. VoiceOver asks an element what it is after the read that
  produced it. With a new element made at every read, an element given a frame and not kept was
  read as nothing; kept elements without frames were read.
- The system speech synthesizer says nothing for U+FFFC: `say -o` wrote a phrase with it to a
  file as long as the phrase without it (macOS 27.0, default system voice).

## Compare with Safari and a stock text view before blaming the app

Two references tell VoiceOver's own behavior from an app's: AppKit's stock `NSTextView` (TextKit
1 and TextKit 2) for text, and Safari rendering the same markup for web content. Safari 27.0.1
on the hosted runner:

- VoiceOver reads a web page by items: a heading, a paragraph, a table and each of its cells,
  and "end of table" after the last. Its cursor is on what a cell holds, a text or a link, and
  not on the cell.
- VoiceOver has separate speech code for a table in a web page and for any other (`SCRWebTable`
  and `SCRTable` in the reports macOS wrote), so its phrasing differs between Safari and an app
  for the same structure. A difference there is not by itself the app's fault.
- WebKit gives an `hr` the splitter role with the `AXContentSeparator` subrole, and Safari's
  VoiceOver reads hidden words in a shown paragraph ([accessibility](accessibility.md)).
  WebKit's table accessibility and its faults are in [VoiceOver and
  tables](voiceover-tables.md).

## An in-process query does not see what VoiceOver is given

A test inside the app's process can establish labels, values, notifications and actions, not
what VoiceOver hears. Which host reads what is in [background Mac
testing](../../guides/background-mac-testing.md). Two limits shape VoiceOver-related tests in a
SwiftPM test process (macOS 27.0; the package's XCTest host in an iOS 27.0 simulator):

- SwiftUI built no accessibility tree for an in-process query, and its hosting view reported no
  accessibility children, so SwiftUI rows can be neither found nor activated there.
- A text view loads no text accessibility for an in-process query. Ask for each range's
  rectangle through `firstRect(for:)` on UIKit and `accessibilityFrame(for:)` on AppKit as a
  stand-in for what a screen reader asks; the stand-in lays out every paragraph, which is
  stronger than what VoiceOver was seen to ask for.

The iOS package host has no window scene and brings up no keyboard, so a test of behavior under
a keyboard posts UIKit's keyboard notifications itself.
