# App extensions

Qualify memory and process lifetime on the actual extension point and hardware. Simulator
behavior does not establish jetsam budgets. XPC invalidation may suspend rather than terminate;
end work explicitly, wait for the process to exit, and keep one-session, cancellation and
watchdog controls. Keep App Group identity with the app.
