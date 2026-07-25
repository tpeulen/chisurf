# Scheduled maintenance jobs (Claude-driven)

Durable, OS-level jobs that periodically wake **Claude Code headlessly** to do
upkeep that needs judgement — currently:

| Job | Label | Default schedule | What it does |
|-----|-------|------------------|--------------|
| UI translation | `com.chisurf.translate-ui` | daily 03:17 | extract new UI strings → translate untranslated `de`/`fr` → recompile `.qm` → commit the catalogues |
| Docs rebuild | `com.chisurf.build-docs` | daily 03:47 | regenerate plugin docs → Sphinx build → fix clear doc defects → commit only touched docs |

Unlike an in-session Claude cron (which dies when the session ends), these are
**macOS LaunchAgents** — they survive restarts and keep running until you remove
them.

## How it works

Each LaunchAgent runs [`claude_job.sh`](claude_job.sh) `<name> <prompt-file>`,
which sets a sane `PATH` (launchd starts with almost none), `cd`s to the repo,
and runs `claude -p "$(cat <prompt>)" --dangerously-skip-permissions`, logging to
`build_tools/jobs/logs/<name>-YYYYMMDD.log`. The task prompts live in
[`prompts/`](prompts/) and are the safety boundary: each one scopes the job to a
narrow set of files and forbids pushing / history rewrites (`--dangerously-skip-permissions`
is needed only because an unattended run has no TTY to approve tool calls).

A per-job `flock` prevents overlapping runs. Credentials come from the
`~/.claude` login already on the machine; if that login expires the run fails and
is logged — run `claude` once interactively to re-authenticate.

## Install

```bash
cd /Users/tpeulen/dev/chisurf
cp build_tools/jobs/launchagents/com.chisurf.translate-ui.plist ~/Library/LaunchAgents/
cp build_tools/jobs/launchagents/com.chisurf.build-docs.plist   ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.chisurf.translate-ui.plist
launchctl load ~/Library/LaunchAgents/com.chisurf.build-docs.plist
```

## Verify / run now / uninstall

```bash
launchctl list | grep com.chisurf                    # is it loaded?
launchctl start com.chisurf.translate-ui             # run once, right now
tail -f build_tools/jobs/logs/translate-ui-*.log     # watch it work

launchctl unload ~/Library/LaunchAgents/com.chisurf.translate-ui.plist
rm ~/Library/LaunchAgents/com.chisurf.translate-ui.plist
```

## Change the schedule

Edit the `StartCalendarInterval` in the plist (add a `Day`/`Weekday` key for
weekly, or use an array of dicts for several times a day), then `launchctl unload`
+ `load` it again. The scripts and prompts are machine-independent; the plists
and `claude_job.sh` hard-code this checkout's absolute path
(`/Users/tpeulen/dev/chisurf`) because launchd needs absolute paths — adjust if
the repo moves.

## Cost & safety notes

- Each firing spends API tokens (a full headless Claude run). Daily is cheap;
  raise the frequency only if the UI/docs churn a lot.
- The jobs commit **locally only, never push**, and only the files they own
  (translation catalogues / touched docs) by explicit pathspec — matching the
  shared-working-tree rules in `CLAUDE.md`.
