# Agent

Drive ChiSurf in plain words. The agent reads the loaded session, runs ChiSurf's analysis tools on it — burst
search, species selection, sub-ensemble decays, fits — and writes small pipelines over the plugin and core APIs
when no ready-made tool fits. Before an analysis it interviews you about the choices that change the result
(which files, which gate, which model and how many components, which correction factors and background, what
output you want) and waits for your answers — up to three rounds, each question with options and its
recommended default. A question that only asks for information ("what is loaded?") is answered directly.

## How it works
1. Pick a **provider** (the dot turns green when it is configured; **Provider settings…** holds the endpoint and
   the key — keys live in your settings store, never in a project or a file the agent writes).
2. Pick a **mode**: it decides which tools the agent may use (read-only, analysis, or code execution).
3. Type a request in the input box and press **Enter** (or **Send**) — or take one from **💡 Things to ask**.
   A long request wraps; the box grows to six lines and then scrolls. **Shift+Enter** starts a new line.
   **↑** on the first line brings back the request you sent before (again for older ones), **↓** on the last
   line goes forward, and past the newest you get back what you were typing. The last 200 requests are kept.
4. Each tool the agent runs shows as a badge in the transcript (`[ok]` done, `[x]` failed; click to expand).
   If it needs answers it lists its questions as a message; reply in the input box and it continues.

## Typing while it works
The input stays open while the agent works. **While working** decides what Enter does then:
- **Interrupt** (the default) stops the run and sends your new message once it has stopped;
- **Queue** holds the message (shown as *queued*) and sends it when the run ends;
- **Steer** hands it to the running agent, which reads it after its next tool call, without stopping.
  With an ACP agent steering is not possible and the message is queued instead.

**Stop** always interrupts, and drops the queued messages. Typing `/busy interrupt`, `/busy queue` or
`/busy steer` switches the mode too; `/busy` alone says which one is in force.

## Grill first and memory
**Grill first** (on by default) is the interview described above. Switched off, the agent asks at most one
round, and only when a request is ambiguous.

**Use memory (Mnemosyne)** (on by default) gives the agent the long-term memory your other agents share:
before each request it recalls the few memories that bear on it (a preference, a fix that worked, a setting a
dataset needed), and it keeps new lessons — one fact each, with why it matters; never secrets or session
noise. Without Mnemosyne installed, the agent works as before. Your saved **skills** are different: a skill is
a whole procedure, loaded when a request's words match it.

## Before trusting a result
The agent reports the numbers its tools computed and the assumptions it made (correction factors, held or fitted
widths); read them. A fit is only as good as the R₀, the donor lifetime and the gate it was given — those are
your choices, which is why it asks. The request and the session summary go to the provider you picked; local
providers keep everything on this machine.

## Further reading
- [The workflow agent](docs/concepts/workflow_agent.md)
- [The AI assistant guide](docs/guides/40_ai_assistant.md)
