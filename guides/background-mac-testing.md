# Background mac testing

These mechanisms and lessons apply when the stated capability is present. Original
measurements establish their recorded platform and workload; they do not establish
universal behavior on later operating systems or in a different application.

## Background Mac view testing

Offscreen windows, in-process accessibility actions, synthetic storage and nonactivating app drivers.

[studywright doc/testing.md](https://github.com/vocaro/studywright/blob/f25d97a147e63c8c9a3bdbebaad2ea1c7e957e8c/doc/testing.md#mac-views-without-ui-automation) and [Pagepour scripts/mac-reader-scene-driver/README.md](https://github.com/vocaro/Pagepour/blob/e8cce638223f4751f4365b61ade888c3eeefb4bd/scripts/mac-reader-scene-driver/README.md). Share the hosting/AX primitives; focus, native menus, other processes and actual assistive interaction need their own lanes.

## Stable snapshots and galleries

Scene inventories, render-until-stable, explicit locale/appearance/scrollbar settings, baseline review, galleries and comparisons.

[studywright doc/testing.md](https://github.com/vocaro/studywright/blob/f25d97a147e63c8c9a3bdbebaad2ea1c7e957e8c/doc/testing.md#static-snapshots-and-accessibility) and [Pagepour doc/design-snapshots.md](https://github.com/vocaro/Pagepour/blob/e8cce638223f4751f4365b61ade888c3eeefb4bd/doc/design-snapshots.md). Keep scene catalogs and baselines local. Window renders and system screenshots establish different things.
