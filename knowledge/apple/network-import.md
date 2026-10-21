# Network import

These mechanisms and lessons apply when the stated capability is present. Original
measurements establish their recorded platform and workload; they do not establish
universal behavior on later operating systems or in a different application.

## Network import policy must survive redirects and decompression

- Have the fetcher return redirects instead of following them. `URLSession` would chase a 30x
  past every check the importer owns; returning it makes each hop re-enter the same gate as a
  newly discovered link: scope, robots exclusion, the private-network check and canonical
  deduplication.
- Gate every request and every redirect hop: the source's own host and port, HTTPS for internet
  hosts, and plain HTTP only to a local-network host the person enabled explicitly. Resolve
  hosts through an injectable resolver so the private-network check runs without DNS in tests.
- Bound the response while the body streams. Counting post-decompression bytes is also the
  answer to a decompression bomb.
- Use an ephemeral `URLSession` with no cookie, cache or credential store, and attach
  credentials only to requests the gate admitted. Do not store a person's username and password
  to replay.
- Check a download's format signature (such as `PK\x03\x04` or `%PDF-`) before handing it on,
  and name a failure by host at most, never by URL: some servers carry an API key in the path.
- Treat robots exclusion and a host's request spacing as rules, not preferences. Make catalog
  requests only on the person's explicit action, without crawling, prefetching or bulk download.
- Corpus permissions and authenticated sources are governed separately from these mechanisms.

## Traverse structure first and deduplicate in three layers

- Follow declared structure first (sitemap, `<nav>`, `rel="next"`), then links. A frontier that
  structure supplied is not extended by link-following, or the first page's links bring back a
  blind crawl.
- Deduplicate by canonical URL before fetching (a link farm of session IDs), by body digest
  before parsing, and by extracted-text digest afterwards (a print variant). Include resource
  bytes and provenance in content identity, but not fetch time, so an identical refetch
  deduplicates.
- An element nobody can see must not add pages to a crawl.

## Fetched markup is untrusted input

- Prune text invisible to a reader before anything reads the tree: `display:none`, `hidden`,
  comments, `<template>`, `<script>`, CDATA, attribute text and similar channels. Pruning the
  tree, rather than filtering in each reader, covers link discovery too. This is the mitigation
  for prompt injection through fetched material; verify it with a probe per channel and a
  control that visible text still arrives.
- Choose the HTML parser for attack surface, not convenience: Foundation's HTML import loads
  WebKit, `WKWebView` runs the page's scripts and `XMLParser` rejects real-world markup; see
  [document parsing](document-parsing.md). A maintained HTML parser such as SwiftSoup fits.
  Select main content from what the site declares (`<main>`, `role="main"`, a lone `<article>`),
  and otherwise score candidates by text and link density.
- Bound nesting depth and parse on a large stack; see
  [stack and work bounds](stack-and-work-bounds.md) for the measured parser costs and why a
  depth limit alone does not bound stack or work.
- Screen a feed as untrusted markup before parsing (no DTD or entity declaration; see
  [document parsing](document-parsing.md)), and bound its body size, depth, entries per page
  (reporting truncation), links per entry and string lengths. Show summaries as plain text and
  do not index them.

## Keep network import testable offline

Put fetching, host resolution, the clock and the politeness sleeper behind seams, so crawl tests
run against a dictionary without a network. Release builds construct only the real fetcher and
contain no fixture seam. A UI journey over an injected offline crawler covers discovery, review
and import without opening a connection. On the Mac it treats the AppKit roles SwiftUI exposes
(`MenuButton`, `MenuItem`, `click()`, a label or a value) as its acceptance contract.
