# Automated docs loops

## Wikipedia docs-mining tranche

One tranche per run: pick a lead, mine the local Wikipedia dump, Crossref-verify
every DOI, land it, pass the four docs guardrail tests, commit only its own
files, record the next lead, stop.

| Piece | File |
|---|---|
| Mandate, rails, procedure | `wikipedia-docs-mining.prompt.md` |
| Runner (branch guard, pid lock, logging) | `run-mining-tranche.sh` |
| Schedule | `~/Library/LaunchAgents/dev.chisurf.docs-mining.plist` |
| Run logs | `~/Library/Logs/chisurf-docs-mining/` |
| Superseded goose recipe | `wikipedia-docs-mining.yaml` |

Weekdays, 09:17–17:17 local, hourly. Run one by hand with
`bash okf/recipes/run-mining-tranche.sh`; the log lands in the directory above.

Control the schedule with:

```bash
launchctl bootout    gui/$(id -u)/dev.chisurf.docs-mining   # pause
launchctl bootstrap  gui/$(id -u) ~/Library/LaunchAgents/dev.chisurf.docs-mining.plist
launchctl print      gui/$(id -u)/dev.chisurf.docs-mining | grep -E "state|runs"
```

### Why it does not run on goose any more

It did, until 2026-08-31. The goose scheduler fired reliably, but the loop ran
on the GLM coding-plan provider, whose weekly quota ran out mid-morning: three
consecutive fires produced a session with the prompt written, zero assistant
messages and zero tokens, and the request log carried
`Rate limit exceeded: Weekly/Monthly Limit Exhausted`. A scheduled job that
dies silently on quota looks exactly like a job with nothing to do, which is
the failure mode worth knowing about. goose has only that one provider
configured, so the loop moved to the Claude CLI (`claude -p`) under launchd,
and the goose schedule was cleared (`~/.local/share/goose/schedule.json`,
backup beside it).

### The mandate is saturated

Independently of the quota, the runs that *did* complete on 2026-08-31 all
concluded the same thing: the dump has no more fluorescence-relevant citations
to give. The fifth tranche returned 2 keepers from 173 candidates; the sixth
and seventh were idle. Until the loop is given a wider mandate than
"mine Wikipedia" or a newer dump, expect idle runs that correctly commit
nothing. That is the loop working, not the loop broken.
