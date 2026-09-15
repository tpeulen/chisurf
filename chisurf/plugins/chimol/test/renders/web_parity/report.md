# chimol: the browser against the desktop

- backend: desktop `native`, browser `browser`
- commands registered: 239 / 239
- commands probed: 213 (26 skipped, see `parity.SKIP`)
- controls reachable: 186 / 186

## Verdict

- ✅ commands missing in the browser: **0**
- ✅ commands the browser has and the desktop does not: **0**
- ❌ commands that behave differently: **2**
- ✅ controls the browser cannot reach: **0**
- ✅ controls only the browser has: **0**
- ✅ menus that differ: **0**
- ✅ host gestures the browser does not deliver: **0**

## Commands that behave differently

| command | desktop | browser |
|---|---|---|
| `diagnose` | ok: chimol <version> from <path> | python <version> on <platform> | host: <host>; viewer: Viewer; chrome: yes | settings: <path> | plugins: 7 loaded -- dbg(5),  | ok: chimol <version> from <path> | python <version> on <platform> | host: <host>; viewer: Viewer; chrome: yes | settings: <path> | plugins: 7 loaded -- dbg(1),  |
| `doctor` | ok: chimol <version> from <path> | python <version> on <platform> | host: <host>; viewer: Viewer; chrome: yes | settings: <path> | plugins: 7 loaded -- dbg(5),  | ok: chimol <version> from <path> | python <version> on <platform> | host: <host>; viewer: Viewer; chrome: yes | settings: <path> | plugins: 7 loaded -- dbg(1),  |
