# VoiceOver on iOS and iPadOS

These mechanisms and lessons apply when the stated capability is present. Original
measurements establish their recorded platform and workload; they do not establish
universal behavior on later operating systems or in a different application.

These lessons come from a reader app that gives VoiceOver accessibility elements of its own for
the lines, links, pictures and table cells of a long text. They were observed in October 2026 in
iOS 27.0 simulators (Xcode 27.0) through XCTest's VoiceOver service, with VoiceOver's own `vot`
log, and on a physical iPad (iPadOS 27.2) and iPhone (iOS 27.2). Nobody listened: the record is
VoiceOver's phrases and log. Each lesson says where it was seen. A simulator's VoiceOver reads
as a device's does but activates nothing; the [VoiceOver guide](../../guides/voiceover.md) says
which lane establishes what, and [simulator VoiceOver](../../guides/voiceover-simulator.md) how
to record speech and read the `vot` log. Tables are in [VoiceOver and
tables](voiceover-tables.md), and role words in [accessibility](accessibility.md).

## VoiceOver moves through a cache of the items around its cursor

VoiceOver does not walk the app's tree at each move. It asks UIKit for the items after and
before the item under its cursor, keeps them, and moves through what it holds:

- When its cursor lands on an item, by a touch or by being set there, it asks for two items each
  side. At each move after that it asks for one more beyond those it holds.
- At its first move while it holds nothing, as after a screen change or a menu closing, it asks
  for fifty items each way and moves through them without asking again (iOS 27.0 simulator and
  iPadOS 27.2). One iPad session asked for ten after a menu.
- An item it holds that its cursor has not been on is checked at the move and replaced if it is
  gone. An item its cursor has been on is taken as it is and read from what VoiceOver kept of
  it. VoiceOver finds it gone only at the next move, and then sets its cursor on the item it was
  last touched on.
- An empty answer is the end of the list as VoiceOver holds it. A move to that side ends at a
  boundary and says the same item again.
- With its cursor on a line it asks for the item before the line two above it, so keep at least
  three items listed above the cursor.

Nothing tells VoiceOver that the view has moved under it. After a move it did not make itself (a
key on a hardware keyboard, the host's own command, the app's scroll step, page turn or rebuilt
text) it reads what it held. With its cursor on a line it said nothing, and its next move read
the line after the old one, where UIKit scrolled the view back: the step was undone. On a device
VoiceOver asks again by itself after it activates an item: after its own double tap on a scroll
button an iPad read on from the right place, and after one on a link it went to the link's
target. A simulator's VoiceOver receives its double tap as a plain touch that it knows nothing
of, so it asks nothing again. A stale read after a simulated activation is not evidence of a
device fault.

## A layout change makes VoiceOver drop its cache about 0.8 s later

Post `UIAccessibility.Notification.layoutChanged` after every move of the app's own. VoiceOver
acts on it about 0.8 s after it arrives, and only if its cursor has stayed put: five layout
changes that arrived while it moved every half second were followed by nothing. It then throws
away everything it holds and asks for two items each way from its cursor (iOS 27.0 simulator,
from its log).

- With no element, the cursor stays where it is and nothing is said. Use this when the cursor is
  outside the moved content: its next move into the content meets the items listed now.
- With an element, VoiceOver moves its cursor there and reads it, traits included. Use this when
  the cursor was on content that moved: name the item that now holds the position shown. Given
  no element in that case, a simulator's VoiceOver went to whichever item was drawn where its
  cursor had stood.
- If the item listed under the cursor is another object than the one VoiceOver held, it sets its
  cursor on the new object without a word, and its rotor returns to its default there.
- Post nothing while VoiceOver's rotor moves the content, since VoiceOver takes its cursor to
  the item the rotor gives it, and nothing for scrolls it or a finger made.
- A screen change also empties the cache, with VoiceOver's sound for a new screen. After a page
  turn under the cursor it said nothing and kept the rotor's place.
- A page-scrolled notification posted by the app made VoiceOver skip lines in one trial.
  VoiceOver's own three-finger scroll is announced through UIKit's page-scrolled notification.
  After the app turned a page itself, posting the page announcement first and then the layout
  change that names the item read both; the other order read the item alone (iOS 27.0
  simulator).

An earlier layout change posted while a menu closes, as when a chapter chosen from a menu is
shown, fills the cache with two items each side before VoiceOver's first move, so it does not
ask for fifty. A simulator then read on into the shown text; an iPad still went to the control
before the text on a move back past the line it came in at.

## UIKit's own text view elements are every paragraph

VoiceOver walks a text view's accessibility elements and, moving in from a control, takes the
first. `UITextView`'s own elements are every paragraph of its text, so VoiceOver took the first
paragraph of a long text and UIKit scrolled the view back to its start. Give VoiceOver elements
of your own, through `accessibilityElements` or the container methods:

- List the lines on screen, each framed by the part of it inside the area the insets leave and
  clear of the scroll indicator, and enough lines beyond the screen for VoiceOver's largest
  request (fifty) in the direction it reads. Moving back into the text from below, VoiceOver
  takes the last item listed.
- Give each link and attachment in a line an element of its own after the line's words.
- Keep each element object for as long as it is listed or under the cursor. New objects for the
  same lines once the cursor had moved on lost VoiceOver's place.
- `index(ofAccessibilityElement:)` must find an element by its place in the document. Matched by
  its character offset within the current page, an element kept from the page before stood for
  whichever line of the new page had the same offsets.
- Track the cursor with `accessibilityElementDidBecomeFocused()` and
  `accessibilityElementDidLoseFocus()` and UIKit's focus notification. A line left is told so
  before the next is told it has the cursor; taking either for the cursor leaving shrank the
  list for a moment, and VoiceOver stopped at a line above the screen.
- Listing must not scroll, select or lay out more than the lines it lists. UIKit's hit test of
  the text view and XCTest's snapshot read every listed element, twice at each move. Some 120
  lines took about 11 ms to list on an iPad and 5 ms in a simulator, in debug builds.
- UIKit scrolls the item VoiceOver moves to until the area inside the insets holds its frame,
  and then 40 points further, so that it rests about 40 points below the top or 120 above the
  bottom. A first line cut by the top inset, listed with its whole frame, scrolled the view as
  VoiceOver came in.
- Each line is its own item, so a word hyphenated across two lines is read as two fragments.

A view that is merely not an accessibility element still offers UIKit's elements for what it
holds. Text views mounted inside the text for touch handling (over table cells, say) gave
VoiceOver every cell's text before the page's first line until they were hidden with
`accessibilityElementsHidden`. VoiceOver also searches inside an element that is a container
before taking its own items, so views left visible inside a text view given that way are read
ahead of its lines. List columns in source order: by their frames alone a column lowered by top
spacing, or the first column of a right-to-left spread, would be read second. A note's popover
built on `UITextView` keeps UIKit's own elements.

## The scroll indicator is a supplementary header that breaks reading order

UIKit keeps a scroll view's vertical indicator among the views it calls the view's supplementary
headers (`_accessibilitySupplementaryHeaderViews`, private). From a header, the item after is
the first element the scroll view lists and the item before is whatever precedes the scroll
view. `index(ofAccessibilityElement:)` answers `NSNotFound` for it and is not asked on that
path. So VoiceOver read on from the last line to the indicator and then down the screen a second
time, and went back from the indicator to the control before the text (iOS 27.0 simulator,
iPadOS 27.2).

- The indicator's accessibility frame is as tall as the scroll view, so the top inset cuts it,
  and UIKit scrolled the view back by the inset and 40 points more as VoiceOver came to it. It
  is 30 points wide for touch, ten times what is drawn, so a touch near the edge found a line
  whose frame ran under the indicator.
- Hidden with `accessibilityElementsHidden`, the indicator is no header and UIKit gives it to
  nobody. A replacement element listed after the last line, which asks the hidden indicator for
  its label, value and hint and forwards increment and decrement to it, keeps reading order
  whichever way VoiceOver reaches it, a touch included. Place it inside the area the insets
  leave, so that nothing scrolls as the cursor comes to it.
- Adjusting the indicator moves the view a tenth of the content at once
  (`accessibilityScrollIndicator:addProgress:`, private) and posts only a visual update. The
  items VoiceOver held are then screens away and gone. It asked for an item before one UIKit no
  longer knew, was given nothing, and stopped at that false end at every move back, on the
  simulator and on the iPad. After an adjustment, post a layout change that names the
  replacement element: VoiceOver drops its cache, asks again around it, and says nothing more
  than the new value.

## The rotor keeps its place only on the same element object

VoiceOver keeps its cursor on the element object it was given. When content under the cursor
changes, as when a page turns, the cursor stays on an object that is no longer shown, and its
next move goes by that object. What is chosen in the rotor belongs to the object.

- To carry the cursor with the content, make the object under the cursor become the element of
  the line that now holds the position: it takes that line's place in the list and everything a
  new element for the line would have, its words, frame, traits and actions. Then post a layout
  change that names it. VoiceOver reads it and the rotor's choice stands: with Next Page chosen,
  each double tap turned another page (iPadOS 27.2).
- Given a new object for the line, VoiceOver read the same words with its rotor back at its
  default. Told of the change with no element named, it kept the rotor and said nothing. An
  announcement of the line's words is the app's string and not the element: it carries no
  traits, so VoiceOver does not say that the item is a heading, a link or an image.
- When the same content is shown again in place (a new appearance, text built again), carry the
  object under the cursor over to its line's new element before posting a layout change with no
  element. Otherwise VoiceOver sets its cursor on the new object at the forced update and its
  rotor resets (iOS 27.0 simulator). Keep a data table's container object too: with the cell
  kept and a new table object, the cell was read without its row and column.
- UIKit treats an element as a data table cell when it conforms to
  `UIAccessibilityContainerDataTableCell`. One class can answer conformance, row and column by
  what the element is at the time, so that the same object is a line on one page and a cell on
  the next. VoiceOver says the row and column of an element its cursor comes to, and of the
  element already under its cursor only when that element was not a cell before. From a cell to
  a cell, give the new cell's own object; the rotor then starts again there.
- Two layout changes posted together, one with no element and one naming the cursor's item, left
  reading and the rotor as they were in nine sessions of ten; in the tenth the line was read
  some seconds late.

## Read All turns a page only after an item with causesPageTurn

In Read All (two-finger swipe down), VoiceOver scrolls `.next` after reading an item that has
`UIAccessibilityTraits.causesPageTurn`, and goes on reading after UIKit's page-scrolled
notification. Observed in an iOS 27.0 simulator through VoiceOver's Read All key; no device has
run it.

- Put the trait on the last item of a page alone. On every line VoiceOver turned the page after
  the first; in a spread give it to the last item of the page read second.
- Where `.next` fails VoiceOver scrolls a page to the right as well, which in a left-to-right
  book is the previous page. Give no item the trait on the last page, nor while a selection
  blocks the scroll.
- After the turn VoiceOver looks among the app's first ten items for one with the trait and
  reads on from the first it finds. A two-line page's last line found there was read alone and
  turned the page again. Withhold the trait from every other item until the cursor leaves the
  item the turn left it on.
- VoiceOver reads an item's traits before its cursor comes to it, so the trait cannot wait for
  the cursor to arrive. Answer it when asked, not as a stored property of an item that can
  become another line.

## UIKit offers the actions of every element that contains the item

The Actions rotor lists the item's custom actions and then those of each element that contains
it. Observed in iOS 27.0 simulators and on an iPhone (iOS 27.2):

- `UITextView` offers one action for each run of its text that is a link, named by the link's
  characters, with U+FFFC for a link that holds only a picture or a hidden label. Given to a
  scroll view that holds a whole book, that is every link of the book on every line.
- SwiftUI attaches `accessibilityAction(named:)` to the view it hosts (see
  [accessibility](accessibility.md)).
- So offer each action on the item that does it, and none on a container. A line offers what is
  in it; a text view that lists its lines offers nothing itself.
- In paged text give each line the page turn (Next Page, Previous Page) as actions of its own. A
  turn chosen in the rotor is an explicit command: let it act where a gesture is held back, as
  while text is selected, and fail it at either end of the document.
- VoiceOver says "Actions available" after an item only where its actions differ from the
  previous item's, so the phrase comes and goes along a page. The rotor's list ends with
  "Activate Default" and wraps. A custom rotor is not an action.
- To find who supplies an action, prefix each action name with its supplier in a throwaway build
  and read the rotor.

## VoiceOver keeps an item's traits and actions as it found them

When its cursor arrives on an item, VoiceOver reads what the item says and offers, and keeps it.
After an action it says nothing of its own. An iPad's rotor went on offering an action that no
longer applied through 36 steps after it had been performed (iPadOS 27.2).

- After an action changes an item's traits or actions, post a layout change that names the item.
  VoiceOver reads it again, for example "selected" in its own language for the `.selected`
  trait, and takes its actions as they now are.
- VoiceOver does not read an accessibility value again when it changes under its cursor. Post an
  announcement for a change the listener needs, such as a search step; announcements queue
  behind current speech.
- UIKit draws a text view's selection and its handles only while the view is first responder. A
  selection set in code is held, reported and copied from, and nothing shows it. Paint it in the
  view yourself when UIKit is not drawing it, rather than taking first responder, which would
  close a keyboard elsewhere in the window. No edit menu comes up for a selection set in code,
  so offer its commands, such as Copy and Deselect, as the item's actions.

## A custom heading rotor must give the same answer twice

VoiceOver's built-in Headings rotor moves only among the elements it is given, and a screen
holds few of a long text's headings. Give each text view a `UIAccessibilityCustomRotor` of the
system heading type that searches the whole document and shows the result.

- VoiceOver asks twice for one move, the second time from the same item, though the first answer
  may have turned the page that item was on. It says "Heading not found" unless both answers
  agree. Search by a place in the document that each element keeps, not by the page it was on
  (iPadOS 27.2 and iOS 27.0 simulators).
- Give a heading one element with the header trait, however many lines it takes. A label that
  ends with the paragraph's line break was read without VoiceOver's word "Heading"; end the
  label at the heading's last word.
- Post nothing for the rotor's move.

XCTest's two-finger rotate did not turn VoiceOver's rotor on a physical iPhone (iOS 27.2), so a
move by heading there was not made by automation.

## Links and pictures in custom text need an element to stand on

- A link in a line is an element with the link trait, named by its words, with the text of each
  picture in its place and decoration left out. A link that is a picture without words is an
  image link without a name, never an omitted one.
- VoiceOver turns a page or reads on only from an element of the text. A page or a screen that
  holds nothing but decoration still lists its decoration as images without a name, or the
  listener has no place to turn the page from.
- A rule (`hr`) needs a stop, since UIKit has no separator trait; see
  [accessibility](accessibility.md) for its word.
- An image without words is an element with the image trait and no label; VoiceOver says its own
  word for it.
