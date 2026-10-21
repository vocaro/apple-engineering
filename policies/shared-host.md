# Current shared host policy

The owner and concurrent sessions keep using this Mac. Builds use the common heavy slots;
whole-machine measurements and gate suites exclude heavy work. Physical devices need a window
agreed with the owner first. Every device needs a real reservation and the project's
human-readable handoff, which is a coordination record, not a mutex. A deadline alone never
releases a device.

Do not take over the screen, keyboard, pointer or Mac VoiceOver without the required explicit
owner authorization. A Mac VoiceOver session on this Mac is only for what a hosted runner cannot
do: someone listening, or stepping by hand. Drive owned Mac apps in the background only by PID
through accessibility; System Events element commands qualify, while `keystroke`, `key code`
and `set frontmost` are foreground input. Do not launch a debugger or raise a developer-password
dialog. Do not run disposable-runner defaults, launchctl, or display configuration on the
workstation.

Hosted macOS jobs are reserved for approved Mac VoiceOver sessions. Dispatch manually through
the guarded dispatcher, batch sessions, keep at most two branch runs or one when any run is
queued, and cancel only your own unneeded runs. The account runs five macOS jobs at a time and
its queue has no priorities: look at what is running before dispatching. Queue inspection
covers every enrolled repository; only this repository's runs on the branch count against its
cap, and a slow queue is no reason to force a dispatch. Retain each project's runner/cost
restrictions.

Read current main instructions in the participating projects before a shared action. Local
configuration records genuine exceptions; it does not invent owner authorization. Preserve live
reservations and uncertain orphan records until recovery confirms their work has stopped.
