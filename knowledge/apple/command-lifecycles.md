# Command lifecycles

These mechanisms and lessons apply when the stated capability is present. Original
measurements establish their recorded platform and workload; they do not establish
universal behavior on later operating systems or in a different application.

These lessons apply to any asynchronous UI or service API that accepts commands and reports
their effects later: a document viewer, a player, a renderer session. Durable recovery and actor
reentrancy are in [scenes and recovery](scenes-and-recovery.md).

## Command submission is not completion

An API that takes commands acknowledges that it accepted one, not that its effect happened.
Report navigation, paint and failure as later events, and keep the two apart in the contract and
in tests.

- Cancelling a caller before submission throws `CancellationError`. A command already submitted
  cannot be undone by cancelling its caller: a page turn that was sent turns.
- Commands whose order matters go through one serial queue in FIFO order. Direct `async` calls
  interleave at their suspension points, so a host that mixes its own commands with a toolbar's
  sends both through the same queue.
- A queued edit reads current state when it executes, not when it was queued, so that it keeps
  fields an earlier queued edit or a host command changed.
- Queued work checks the session's lifecycle again just before submission. Closing or replacing
  the session invalidates the queue, and work queued for one document never reaches the next.
- Readiness is emitted exactly once. Later disclosures, such as reduced fidelity, do not restart
  the lifecycle.
- `close` is idempotent, disables callbacks and releases the renderer's references. A view a
  closed session returns shows nothing.

## Publish state before the event that reports it

When a session exposes observable state as well as an event stream, update the state first and
then emit the matching event. A host that reads state from its event handler then sees the state
the event describes. Keep lifecycle, capabilities, the style actually applied, the resolved
appearance, location and the number of commands in flight in that state, so that built-in
controls can disable themselves before readiness, after close and while detached.
