# VoiceOver and tables

These mechanisms and lessons apply when the stated capability is present. Original
measurements establish their recorded platform and workload; they do not establish
universal behavior on later operating systems or in a different application.

These lessons come from a reader app that draws HTML tables natively and gives VoiceOver
elements of its own for them, compared with Safari reading the same markup. iOS observations
were made in iOS 27.0 simulators (Xcode 27.0) and on a physical iPad (iPadOS 27.2); Mac
observations on GitHub-hosted runners (macOS 27.0.1 26A434, Safari 27.0.1), October 2026. Nobody
listened. Line and element lessons that are not about tables are in [VoiceOver on iOS and
iPadOS](voiceover-ios.md) and [VoiceOver on the Mac](voiceover-mac.md).

## Decide whether a table holds data as WebKit does

HTML has no element that says a table is there for layout. WebKit decides from what it builds
and draws (`AXTableHelpers` in WebKit's source, read on 2026-10-12), and an app that renders
HTML tables should decide the same way unless it states why not:

- A `role` on the table settles it: `presentation` or `none` is layout; `table`, `grid` or
  `treegrid` is data.
- Otherwise a table is data when it has a caption, a `summary`, a `thead` or `tfoot`, a `col` or
  `colgroup`, or `rules`; when a row or cell has a table role, or a cell has `headers`, `scope`,
  `abbr` or `axis`; when it has twenty rows or twenty cells in a row; when ten cells are ruled
  above and below or on both sides; or when half its cells are ruled so, or on any one side. The
  table's `border` attribute rules every cell; a border around the table alone rules none.
- WebKit also counts header cells only in a first row or first column, and counts cell
  backgrounds and alternating row backgrounds. A renderer whose dark appearance drops authored
  backgrounds should not let them decide, or a table is a different thing to a listener in each
  appearance.

Each cell of a data table is a stop. A table of forty rows and three columns is 123 moves where
it was 41 as rows, and VoiceOver adds row, column and header words to what the markup says. That
is the point for a table of figures and noise for a ruled box of two things;
`role="presentation"` is how markup says so.

## On iOS a data table is a container among the lines

Give a data table as one `UIAccessibilityContainerDataTable` where its rows stand among the
lines, not a stop itself, with each cell an element inside it that says which rows and columns
it covers:

- A cell that spans is one element, read where it starts, that answers for every slot it covers.
  An empty cell is a stop: it has a place in the grid, and VoiceOver says its headers and
  column.
- At each cell VoiceOver says its header cells, whether the cell is itself a row or column
  header, the row when it changes and the column. It says "Table start" with the whole table's
  count of rows and columns at the first cell listed and "Table end" at the last, whatever their
  numbers. Keep row numbers table-wide when a page shows the middle of a table, so that the
  second page starts at its real row. The first cell VoiceOver comes to in a table is said
  without its header cells.
- The Rows rotor setting moves down and up a column.
- A cell offers what it can do itself, such as selecting its text, following each of its links
  and inspecting each picture. A double tap follows the link of a cell whose words are one link.
  Actions that come from a view mounted over the cell exist only once that view is mounted,
  which is once the cell is on screen.
- A table that is not data reads well as one element per row, its cells' words in column order,
  with actions for its cells. Hide any views mounted over its cells from assistive technology.

In a scrolling view VoiceOver asks the table for its next cell before it asks the containing
view for anything. Make the table list its rows again, for where the cursor is now, whenever it
is asked. Answered from the rows listed for the previous cell, the table ended at the last of
those. Keep one table element while any cell of it is listed, and each cell its own, so that
VoiceOver reads through a table longer than the screen and the Rows rotor moves past the screen.

## UIKit asks for the headers of a row and of a column, not of a cell

UIKit asks a data table for the header cells of a row and of a column, and VoiceOver says them
before the cell it comes to, leaving out the cell itself and any it said for the cell before. A
header cell over a second row of header cells would then be read under their names. Answer with
the header cells above and before the cell last asked for, which is the cell VoiceOver has come
to. UIKit has no way to give one cell headers of its own, so an HTML `headers` attribute cannot
be followed. A column's header cell on another page is still named before the cells it heads
when the table answers with an element that has the header's words.

## On the Mac VoiceOver meets a table only at an attachment character

Mac VoiceOver reads a text view by line and by word, and meets a table drawn in the text only as
the element the text gives at an attachment's character. What it does with that element decided
the shape (macOS 27.0.1, hosted runner):

- Given the row (`AXRow`) at a row's character, with the table as its parent, it said "table
  row" and took no table command: it was in a row, not a table.
- Given one table at every row's character, it read the whole table at each. A label stopped
  that only with selected cells among the attributes too.
- It comes into a table at its selected row, or failing that at the first row on screen.

What works is AppKit's table (`AXTable`) at each row's character: the whole table, with
`AXRows`, `AXVisibleRows`, `AXSelectedRows` (the row it stands at), `AXColumns`,
`AXVisibleCells`, `AXColumnHeaderUIElements`, `AXRowHeaderUIElements`, `AXRowCount` and
`AXColumnCount`, each cell with `AXRowIndexRange` and `AXColumnIndexRange`. Label each row's
table with that row's words. VoiceOver then reads a row's words and "table" by line and by word,
and Control-Option-Shift-Down goes into the table at that row, where its own table navigation
and its column and row header commands work. The costs: a table says a row is selected that
nobody selected, and "table" follows every row.

After VoiceOver leaves a table, a move by line and going in again enters the table it left, not
the one on the new line; a move by word first enters the new one.

## A cell that names its own header cells makes Mac VoiceOver quit

AppKit lets a cell name its own header cells, as HTML and WebKit do. Given that, VoiceOver quit
with an exception in `-[SCRCell columnHeaderDescription]` under
`-[SCRTable _columnHeaderDescriptionForCellElement:headerIndex:]`, from
`__CFStringCheckAndReplace`, at a move to a cell under a header or at Control-Option-C. The
method appends the first header's description without checking it, and the description came
back nil now and then, whatever the header was. Safari's cells name theirs, and VoiceOver quit
the same way there, in `-[SCRWebTableCell columnHeaderDescription]`, in three of ten Safari
sessions that pressed the key (macOS 27.0.1, Safari 27.0.1, hosted runner).

Give the headers from the table instead, as AppKit's own tables do: one header element for each
column and for each row of the whole table. VoiceOver takes the one at a cell's column and row,
says the same headers and did not quit. The fault can be shown with Safari and an HTML table
alone.

## Mac VoiceOver reads a header cell by what it holds

- VoiceOver reads a header cell, before each cell it heads, by what each thing it holds is
  called: a text area by its value, a link by its title. It does not read a cell under itself. A
  header cell that holds a link whose title is empty leaves the cells it heads without their
  header.
- Where the header is not the cell itself (static text standing for several header cells, for a
  header on another page or far off screen), it is read under its own name: a header cell given
  that way had its name said before the cell itself.
- Where nothing heads a column or row, give an element without words; VoiceOver then says the
  number, "column 2 of 3".
- One header per column means a header cell under another is read under the column's whole
  header, its own words among them.

## A Mac cell is read by what it holds, not by what it says it is

At a cell VoiceOver says what the cell holds and nothing of what the cell says it is:

- It reads a text area by its characters, and a picture's character is U+FFFC. A label on the
  cell is said after what the cell holds, so a cell's words come twice. A subrole, a role
  description or a value on the cell changed nothing on arrival.
- A cell that shows only pictures should hold an `AXImage` for each, labeled by the picture's
  words, in place of a text area, as a web view's cell holds an image. VoiceOver then says the
  picture's words and "image", or "image cell" for a picture nobody described. A picture among
  words needs the text area and then the image, which costs the listener a step further in.
- A cell whose words are one link should hold a link element around its text areas, labeled by
  the cell's words, and offer a press. Only that shape said "hyperlink" once and kept the words
  reachable: a link in place of the text areas hid the words, and a link beside them said
  "hyperlink" twice. A header cell that is a link needs the cell's words as the link's title
  too.
- A cell with nothing in it, or decoration alone, is read as "empty cell".

## VoiceOver keeps what it made of an element

VoiceOver keeps its first interpretation of an element and finds it again by the element:

- An element that was a table is still a table to VoiceOver after the text it stood in is
  replaced, whatever it now says. With no rows it is read as "empty"; with the old counts, as a
  table of that size. A table the text no longer holds gives one row with nothing in it, a row
  count of one and no columns, and VoiceOver says neither.
- VoiceOver keeps its cursor on an element only while the element is among the children of the
  text it is in. When a page turn takes away the row element under its cursor, keep the departed
  elements among the text's children as static text with nothing in it, standing at the line the
  new page is entered at, until the text is replaced again. Without them VoiceOver left the
  text. A layout change, posted by the element, the text view or the window, did not hold it.
- VoiceOver gives keyboard focus to each cell text area it moves to (see [VoiceOver on the
  Mac](voiceover-mac.md)), so a cell's text view that leaves must hand focus to the text view
  around it.

VoiceOver's code that decides the departed table's words was read without running it, and is
recorded with the sessions in an [EPUBLib issue
comment](https://github.com/vocaro/EPUBLib/issues/485#issuecomment-6272726811).

## Mac VoiceOver reads a group by its name and nothing of what it holds

A row of a table that is not data is a group (`AXGroup`) at its character, holding its cells'
text areas. As it reads the text VoiceOver says the group's name and "group", and nothing of
what the group holds. Rows named with the app's own word for a row hid the table's words from a
listener who read on. Name the group by its cells' words in column order, a comma between cells.
A group without a name is read as its children's roles ("text image text image group"), and help
on it is read in the name's place (see [accessibility](accessibility.md)). VoiceOver's Actions
menu holds a group's actions only while its cursor is on the group, after going into the row and
out again.

Make the group the same element whether or not its cells are on screen. One made from what was
on screen when the text was asked for it, an image when the cells' views were absent, stayed an
image to VoiceOver after they came.

## A row with nothing to say must fold into the next line

A row of empty cells or decoration still stopped Mac VoiceOver, in silence, whatever the text
gave at its character, none included: it stops at an attachment character regardless. To pass it
over by word, by line and in Read All, take all four steps: give no element at the row's
character, give that character as a space, make the row's line part of the line after it, and
give the break after the row as a space. Every range still matches the text, but a client counts
one line fewer for each such row, and VoiceOver draws its cursor round the row and the next row
together. Rows at the end of a page are one line of spaces where VoiceOver stops once. A row
that holds a link, a rule or a picture nobody described must stay a stop. Inside a data table
such a row is still a row, and its cells are read as "empty cell".

## Safari reads tables with web-page speech

Compare a native table with Safari reading the same markup before calling a difference the app's
(Safari 27.0.1, macOS 27.0.1, hosted runner):

- Safari gives a table as one `AXTable` titled by its caption (`AXTitle`, no label), with
  `AXRows`, `AXVisibleRows`, `AXColumns`, `AXVisibleCells`, column and row header elements,
  `AXHeader`, the counts and `AXSelectedCells`, and no `AXSelectedRows`. A cell is an `AXCell`
  with its index ranges and header cells of its own, holding static text or a link, and nothing
  where it is empty. A table marked as layout is no table: each cell is a group of the page.
- VoiceOver says the table's size and caption on arriving and "end of table" past the last cell,
  and a row or column number at each new row and cell, because those are its words for a table
  in a web page (`SCRWebTable`). For another app's table (`SCRTable`) it says the headers and a
  number only where nothing heads a row or column. Numbers put into each cell's own words would
  be the app's words in the app's language at every cell.
- WebKit's accessibility code ends a row group after each row that is a child of `table` itself,
  as XHTML allows and an HTML parser never leaves (`processTableDescendant` in
  `AccessibilityNodeObject.cpp`, WebKit read on 2026-10-13). Cells that span rows in such a
  table were given as one row deep, so Safari is no reference for headers under other headers
  there.
