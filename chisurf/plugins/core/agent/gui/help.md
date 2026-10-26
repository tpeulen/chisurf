# Agent

Drive ChiSurf in plain words. The agent reads the loaded session, runs ChiSurf's analysis tools on it — burst
search, species selection, sub-ensemble decays, fits — and writes small pipelines over the plugin and core APIs
when no ready-made tool fits. When a request leaves a choice open that changes the result (which file, which
Förster radius, how many components), it asks one round of questions first and waits for your answers.

## How it works
1. Pick a **provider** (the dot turns green when it is configured; **Provider settings…** holds the endpoint and
   the key — keys live in your settings store, never in a project or a file the agent writes).
2. Pick a **mode**: it decides which tools the agent may use (read-only, analysis, or code execution).
3. Type a request in the input box and press **Send** — or take one from **💡 Things to ask**.
4. Each tool the agent runs shows as a badge in the transcript (`[ok]` done, `[x]` failed; click to expand).
   If it needs answers it lists its questions as a message; reply in the input box and it continues.

## Before trusting a result
The agent reports the numbers its tools computed and the assumptions it made (correction factors, held or fitted
widths); read them. A fit is only as good as the R₀, the donor lifetime and the gate it was given — those are
your choices, which is why it asks. The request and the session summary go to the provider you picked; local
providers keep everything on this machine.

## Further reading
- [The workflow agent](docs/concepts/workflow_agent.md)
- [The AI assistant guide](docs/guides/40_ai_assistant.md)
