# Raster contracts

These mechanisms and lessons apply when the stated capability is present. Original
measurements establish their recorded platform and workload; they do not establish
universal behavior on later operating systems or in a different application.

## Raster coordinates, conversions and lifetimes need separate contracts

State origin, units, alpha/premultiplication, stride and inclusive bounds. A grayscale drawing conversion can leave a converted copy retained by the source image; the raster module instead owns its output buffer. Compare geometry, decoded pixels and OCR content separately: macOS font smoothing alone reproduced iOS crop-byte differences.

[PDFReflowLib doc/document-raster-analysis.md](https://github.com/vocaro/PDFReflowLib/blob/4a625316a5b4a4aafea5134dfcfec1a6991e9cbd/doc/document-raster-analysis.md) and [PDFReflowLib measurements/converter-extension-693/record.md](https://github.com/vocaro/PDFReflowLib/blob/4a625316a5b4a4aafea5134dfcfec1a6991e9cbd/measurements/converter-extension-693/record.md#page-379-on-ios). Platform pixel differences are not automatically missing content, and matching pixels alone do not prove semantic correctness.
