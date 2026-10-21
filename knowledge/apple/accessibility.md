# Accessibility

These mechanisms and lessons apply when the stated capability is present. Original
measurements establish their recorded platform and workload; they do not establish
universal behavior on later operating systems or in a different application.

This article holds lessons that apply to any assistive technology or to both platforms. What
VoiceOver itself does is in [VoiceOver on iOS and iPadOS](voiceover-ios.md), [VoiceOver on the
Mac](voiceover-mac.md) and [VoiceOver and tables](voiceover-tables.md). How to record and read
speech is in the [VoiceOver guide](../../guides/voiceover.md). Spoken language per range is in
[text layout and Unicode](text-layout-and-unicode.md).

## Map HTML alternatives and hiding as HTML-AAM does

An app that renders HTML natively (a reader, a help viewer, an importer) owes assistive
technology what a browser gives it. WAI-ARIA 1.2 and HTML-AAM decide the mapping:

- An `img` with an empty `alt`, or one of white space alone, is decoration: no element, no name,
  no action. An `img` with no `alt` is content nobody described: give it an element with the
  image role or trait and no name, so that VoiceOver says its own word for an image in the
  listener's language. Do not invent a name such as "Book image".
- An SVG file's `title` and `desc` name it only where the markup gave no `alt`. An `object` or
  `embed` is named by its `title`. An inline `svg` is named by its `title` and `desc`.
- `aria-hidden="true"` on the image or on an ancestor, or the role `presentation` or `none`,
  hides the image from assistive technology alone. Its words still stand for it in selection,
  copy and search, as a browser copies them, so keep "hidden from assistive technology" apart
  from "has no words".
- ARIA ignores a presentational role on an element that can take focus (`tabindex`) or that has
  a global ARIA attribute such as `aria-label` or `aria-describedby`. The role is the first
  token of `role` that names a role. `aria-hidden="false"` hides nothing. A presentational role
  on an ancestor does not reach the image.
- A link stays reachable whatever its image's `alt` says. Decoration that is all a link holds is
  an image link without a name; decoration beside words in a link is passed over and the words
  carry the link.
- `h1` to `h6` and `role="heading"` are headings at their level or their `aria-level` from 1
  to 6. `role="heading"` without a level is level 2. An `aria-level` past 6 leaves a heading
  with no level. A heading element whose role is `presentation` or `none` is no heading to a
  listener, though it is drawn as one.
- An `hr` has the separator role: it is a break between scenes or subjects that a reader who
  sees the page gets from the line. Give it a stop. One the markup hides from assistive
  technology is ornament and has none.

Text that CSS `visibility: hidden` hides keeps its room and goes to nobody. Give a client spaces
in its place where the platform reads characters one for one (the Mac, see [VoiceOver on the
Mac](voiceover-mac.md)). Safari 27.0.1 is not exact here: its VoiceOver read hidden words inside
a shown paragraph and passed over a `visibility: visible` child of a hidden paragraph.

## VoiceOver speaks a role's own words

VoiceOver says a role in its own words, translated for the listener, and those words describe
the role wherever it is used. Choose a role by what VoiceOver says for it, not by its name.
Heard with Mac VoiceOver on a hosted runner (macOS 27.0.1 26A434), October 2026:

- AppKit has no role for a break in content. The nearest is `AXSplitter`, which WebKit gives an
  `hr` with the subrole `AXContentSeparator` and the role description "separator". VoiceOver
  reads any splitter as the bar between two panes: a horizontal splitter, collapsed, on top,
  with or without the subrole. With all of WebKit's attributes it still tells of a pane and of
  "no action available".
- An element of the unknown role (`AXUnknown`) with the role description "separator" was read as
  "separator". Static text whose value is the app's word was read as the word.
- UIKit has no trait for a separator, so VoiceOver has no word of its own for one, as it has for
  an image or a link. On iPhone and iPad give the break a stop with no trait whose label is the
  app's word.
- "Hyperlink" is AppKit's word for a link in text, and VoiceOver says it after the link's name.
  "Hyperlink cell" and "image cell" are its names for a cell that holds a link or a picture.
- VoiceOver was not heard to say a heading level that a UIKit element's traits or a Mac text's
  `AXHeadingLevel` attribute gives (iOS 27.0 simulator, iPadOS 27.2, macOS 27.0.1). It says the
  level of a Mac element with the heading role whose value is the level, and lists levels in the
  Mac rotor.

A word the platform lacks is the app's own, in the app's language: translate it with the app.
Never add a word that VoiceOver already says, such as a cell's row and column or an element's
role, as a value or an announcement. A VoiceOver that says its own would say it twice, in two
languages.

## An element without a name is read by its help or its contents

What VoiceOver says for an element without a label depends on the platform and the role:

- Mac VoiceOver reads an element's help (`AXHelp`) in the place of a missing label (macOS
  27.0.1). An image without words that carries a help sentence about an action is announced as
  that sentence. Give an unnamed element no help, or give it a name.
- A Mac group is read as its name and "group", and nothing of what it holds. A group without a
  name is read as the roles of its children in the listener's language, as "text image text
  image group" for two text areas that each hold an image.
- On iPhone and iPad VoiceOver says its own word for the image trait of an element without a
  label (iOS 27.0 simulator, iPadOS 27.2).

So a container whose words a listener needs must carry them as its name, and an element whose
only words are VoiceOver's role must not also carry help.

## SwiftUI puts named actions on the view it hosts

`accessibilityAction(named:)` and `accessibilityScrollAction` behave differently on each
platform when applied to a representable that wraps an AppKit or UIKit view:

- On iOS, SwiftUI attached the named actions to the represented UIKit view, and UIKit offers
  VoiceOver the actions of every element that contains the item under its cursor. Every line
  inside the view then said "Actions available" and offered those actions, twice where the lines
  had their own (iOS 27.0 simulator, iOS 27.2 iPhone). See [VoiceOver on iOS and
  iPadOS](voiceover-ios.md) for where actions come from.
- On the Mac, the same modifiers on an `NSViewRepresentable` whose view is not an accessibility
  element reached no element a client could see: no action of that name existed anywhere in the
  window (macOS 27.0.1). Give the actions to the AppKit element VoiceOver is on as
  `NSAccessibilityCustomAction`.
- SwiftUI's hosting view is an `AXGroup` around the window's content on the Mac, so a SwiftUI
  host always has an accessibility ancestor above an embedded AppKit view. In a SwiftPM test
  process the hosting view reported no accessibility children at all (see [VoiceOver on the
  Mac](voiceover-mac.md)).

## SwiftUI controls take different shapes in each platform's tree

Inspected with the iOS 27 and macOS 27 SDKs, October 2026:

- A segmented `Picker` in an iOS toolbar has no automatic overflow-menu representation, so it
  needs a high visibility priority or a pinned placement. Items placed with
  `.topBarPinnedTrailing` stay out of the overflow. On the Mac a segmented picker is a radio
  group: each segment is a radio button named by its label, with the current one selected.
- On the Mac a `ScrollView` is an `AXScrollArea` with no name around its content. VoiceOver
  stops on it as a scroll area and passes its controls by until the listener interacts with it.
  Avoid a scroll view around a few controls that always fit.
- On iOS a touch that rests on a control inside a scroll view before it moves presses that
  control, as in any scroll view.
- On iOS a `Menu` item's custom accessibility value is not exposed: the system menu shows a
  checkmark, which VoiceOver calls "selected". A `List` row's hidden checkmark image still
  appears in the tree as an image named "Selected"; VoiceOver did not stop on it.
- Do not put a text field inside a `Menu`; present search in a popover or a sheet.

## A layout priority is seen only from the outermost modifier

A stack offers its children space by layout priority, and views of equal priority each get an
equal share. A control strip that must keep its natural height beside a flexible view needs a
higher priority than that view. Padding or a frame applied after `.layoutPriority` wraps the
view in another whose priority is the default, which hides the priority from the stack: set the
priority again after the last such modifier. The same holds in a row, where the priority decides
who is offered width first. This matters most at accessibility text sizes, where a strip that
gets only an equal share scrolls or clips in half the screen.
