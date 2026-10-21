# Raster contracts

These mechanisms and lessons apply when the stated capability is present. Original
measurements establish their recorded platform and workload; they do not establish
universal behavior on later operating systems or in a different application.

## Raster coordinates, conversions and lifetimes need separate contracts

State each of these for a raster type, and test each one:

- Origin and axes. A pixel raster is usually top-left with `y` down; PDF user space and a Core
  Graphics context have `y` up. Convert page boxes to pixels in one named place.
- Storage. Bytes per pixel, row stride (with or without padding), and the exact buffer length,
  checked for overflow and length when the raster is made.
- Luminance. Name the formula, for example Rec. 601 integer luma composited over white, and the
  handling of premultiplied, straight and skipped alpha. Convert other layouts (BGRA, gray with
  padded rows, 16-bit) with `vImageBuffer_InitWithCGImage` into a buffer you own, never by
  drawing them.
- Thresholds. For Otsu's method, which level wins a tie and what happens with no split; whether
  "darker than t" is strict, so the threshold level itself is paper or ink.
- Regions. Inclusive or exclusive boxes, 4- or 8-connectivity, and the order components are
  reported in.
- Bounds. A pixel ceiling checked before allocation, a label ceiling, and cancellation checked
  between rows.
- Ownership. The raster owns its output buffer and keeps no reference to the image it was read
  from.

PDFKit exposes no API for where an image is drawn on a page. An image XObject is painted by `Do`
over the unit square, so the current transformation matrix at that operator is its placement.
Walk the content stream with `CGPDFScanner`, tracking `q`, `Q` and `cm`; descend into Form
XObjects, applying each `/Matrix`, or a page full of images reports none; and count inline
images (`BI`/`ID`/`EI`) separately, so "no images" differs from "did not descend".

Compare geometry, decoded pixels and recognized content separately. Platform pixel differences
are not automatically missing content, and matching pixels alone do not prove semantic
correctness.

## Converting a raster through a context can retain a copy

- Drawing an image into a gray `CGContext` to convert it leaves Core Graphics holding a
  converted copy attached to the source image for as long as that image lives. Read the data
  provider's bytes directly, or convert with vImage into your own buffer using
  `kvImageNoAllocate`, and test that the image's data is released once the caller drops it.
- Reading a finished `CGImage`'s pixels copies them. To inspect a raster you render, read the
  bitmap context's own buffer before making the image.
- A rendered raster whose alpha plane is constant can be relabeled opaque over its own pixel
  buffer at write time, so a PNG records three channels without another copy. Keep the format a
  recognizer is measured against unchanged for the recognizer.

## Worst-case allocation follows the algorithm, not the typical page

Connected-component labeling needs one label per pixel in the worst case. A raster of isolated
pixels at a 12-megapixel ceiling means about 3 million labels and components, and measured
361 MiB of peak RSS beyond the raster itself, while the densest real page measured held fewer
than 4,000 components. Count every buffer an operation makes (the luminance buffer, an inverted
copy, per-label and per-component storage) against the caller's limit before allocating, and
offer a bounded form that throws past a caller-supplied label maximum.

Evidence: [PDFReflowLib measurements/raster-primitives-504](https://github.com/vocaro/PDFReflowLib/blob/dc89a4eccecb99943661709887fd2a61a1a51b29/measurements/raster-primitives-504/record.md).

## Rasterized glyph ink can fall outside the typographic box

A typographic box covers glyph ink as laid out. Drawing into a bitmap `CGContext` then moves
each glyph onto the pixel grid, down and to the left (subpixel quantization), and on macOS font
smoothing thickens it, so ink can fall up to two device pixels outside the box. Observed on
macOS 27.0 (26A428) and iOS 27.0, October 2026.

- A host that clips to a layout box allows two device pixels around it, or calls
  `setShouldSubpixelQuantizeFonts(false)` and `setShouldSmoothFonts(false)` on its own context
  before drawing.
- An ink-containment check at 2x allows one point.

## Mac font smoothing explains iOS pixel differences

A `CGContext` left at its default font smoothing draws glyphs heavier on macOS than iOS draws
them. Observed October 2026 between macOS 27 and iOS (the iOS 27.1 simulator and iOS 27.2
devices, which wrote identical bytes):

- Rendering the same crops on the Mac with font smoothing off reproduced the iOS RGBA digests
  exactly. With the default, they matched the Mac reference.
- The iOS digits carried 16 to 24% less ink. Rules drawn as paths were identical.
- Across a whole book the text was the same, but nearly every image differed in pixels and
  hundreds of crops differed in size by 1 to 3 pixels.

Set the context's font smoothing explicitly, which changes the Mac's output and needs new
references, or keep a pixel reference per platform. A pixel contract recorded on one platform is
that platform's drawing, not a fidelity requirement.

Evidence: [PDFReflowLib measurements/converter-extension-693](https://github.com/vocaro/PDFReflowLib/blob/dc89a4eccecb99943661709887fd2a61a1a51b29/measurements/converter-extension-693/record.md#page-379-on-ios).

## Exact pixel comparisons measure renderer drift

- Two renderers never agree exactly. Correct crops compared against a Poppler reference scored
  0.982 to 0.997 against a 0.95 similarity floor, and about 0.03 of that was renderer
  disagreement, not fidelity.
- The same binary on one Mac decoded different RGB pixels in two execution environments, with
  mean absolute channel differences under 1 of 255 (see
  [framework execution identity](framework-execution-identity.md)).
- Re-rendering a page did not reproduce stored image hashes across PDFKit versions. Bind durable
  provenance to the source file's hash, not to rendered bytes, and write an artifact manifest
  last so a crash leaves the previous complete set or no declared new one.
- A comparison of luminance only is blind to color: recoloring a page to complementary hues at
  equal lightness barely moved the score. It cannot speak for color coding.

Geometry decides correctness outcomes; pixels are for review. To build an appearance gate:

1. Render the reference through the library's own rasterizer as well as the reference renderer,
   and set the floor from their measured disagreement per page, not one hand-chosen constant.
2. Add a color statistic robust to that drift, such as the mean hue and chroma of a crop's
   largest flat regions, instead of asserting pixels.
3. Record the raster policy (resolution and any binding pixel ceiling) with each reference, so a
   run under another policy skips the reference explicitly rather than failing it.
