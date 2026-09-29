# Web dashboard as a service

## The inherited-web-dist trap

When the Electron desktop app is running it exports `HERMES_WEB_DIST` pointing at its own packaged
renderer bundle (`.../app.asar.unpacked/dist`). A `hermes dashboard` started from that shell
inherits the variable and serves the DESKTOP frontend to the browser, which then fails looking for
an Electron IPC bridge that does not exist in a browser tab. `curl` returns HTTP 200 the whole
time, so the server looks healthy while every page is broken.

Start it with the variable stripped:

```bash
env -u HERMES_WEB_DIST hermes dashboard --isolated --no-open --port 9119
```

Do NOT pass `--skip-build` while diagnosing this: the real dashboard bundle may never have been
built, and skipping the build leaves the wrong bundle in place and hides the cause.

## Verify the served bundle, not just the status code

HTTP 200 proves a server answered, not that it answered with the right app:

```bash
curl -s http://127.0.0.1:9119/ > /tmp/dash.html
grep -o "<title>[^<]*</title>" /tmp/dash.html      # expect the Dashboard title
grep -c "app.asar\|TRANSPARENT_WINDOWS" /tmp/dash.html   # expect 0
```

A non-zero count on the second grep means the Electron bundle is being served.

## Autostart via launchd

A dashboard started by hand dies with its shell. For a persistent one, model the LaunchAgent on
the existing gateway plists (`RunAtLoad`, `KeepAlive`, `ThrottleInterval` 30, explicit `PATH`,
`VIRTUAL_ENV`, `HERMES_HOME`, log paths).

**Omit `HERMES_WEB_DIST` from `EnvironmentVariables`.** launchd does not inherit the login shell's
exports, so leaving it out is the whole fix — no `env -u` wrapper needed.

After `launchctl load`, an exit status of 75 with `BACKEND_PORT_IN_USE` in the log means a
manually started instance still holds the port. Stop that process; KeepAlive brings the managed
one up on the next throttle window (~30 s), so wait before declaring failure. Confirm stability by
checking the PID twice a minute apart — a changing PID is a crash loop, an unchanged one is
healthy, and a stale non-zero exit code from the first failed attempt is not a live error.
