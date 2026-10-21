# Simulator disposable

Create each simulator under a unique name, pass its canonical uppercase UDID to every command,
boot it headlessly to `bootstatus -b`, and shut it down and delete it by that UDID however the
run ends. Never select by name or `booted`, and never touch another session's device. Do not
open a live simulator view or screen-controlling simulator tool unless the owner asked to watch.
Run lifecycle, builds and tests as one admitted lane; pass test environment with `TEST_RUNNER_`;
require a positive executed count; report a boot timeout as unmeasured. Set Duo poses by
automation and confirm the observed display; never use screenConfig on the Duo simulator. Agree a window with the
owner before any session on the paired iPhone or iPad, and still reserve it. Methods:
guides/simulator-testing.md, guides/device-testing.md.
