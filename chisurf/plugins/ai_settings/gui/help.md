# AI Settings

One endpoint per provider, with separate models for text and for image
generation. ChiSurf uses these settings for the agent panel in the code editor,
for AI-assisted curve triage, and for generating plugin icons.

## Providers

The list is the provider table the rest of the application uses, so anything you
can select here works everywhere. It is ordered by where your data goes:

| Provider | Notes |
|---|---|
| **On this computer** | The default: Liquid AI's LFM3-1.7B, run by llama.cpp on your own machine. No account, no key, works offline, nothing leaves the computer. Ollama, LM Studio or anything else speaking the OpenAI API locally works too. |
| **Mistral (EU)** | Data stays in the EU. A much larger model: better on long, open-ended analyses. |
| **OpenAI** | |
| **OpenRouter** | A gateway in front of many models. |
| **Custom** | Any OpenAI-compatible endpoint; you supply the base URL. |

Each provider keeps its **own** base URL, key and models. Switching providers
does not carry your key across.

## The API key

Paste it and it is saved and tested straight away.

**Where it is stored:** a JSON file in your ChiSurf settings directory
(`ai_api_settings.json`), written so that only your user account can read it.

**You may not need to type one at all.** If the key is in your environment —
`MISTRAL_API_KEY`, `OPENAI_API_KEY` and the usual variants — ChiSurf picks it up
and the field shows it as coming from the environment. A key you type here takes
precedence over the environment.

The key is drawn as stars. **Show key** shows it
in clear text for this session only; changing the provider hides it again and the
choice is never saved. Enter, or a click elsewhere, saves the key and tests the
endpoint.

To stop using a key, clear the field and press **Save**.

## The on-device model (LFM3)

**On this computer** needs nothing set up. The first time the agent is asked
something, ChiSurf starts `llama-server` (part of the ChiSurf environment) with
[LFM3-1.7B](https://huggingface.co/LiquidAI/LFM3-1.7B-GGUF) and waits for it;
the first start downloads the model (about 1.1 GB) into llama.cpp's cache, later
starts take a few seconds. The server listens on `127.0.0.1:8080` only, and is
stopped when ChiSurf exits. Its output goes to `llama-server.log` in the
ChiSurf settings directory.

- **A server you run yourself is used as it is.** If something already answers
  at the base URL — `llama-server`, Ollama (`http://127.0.0.1:11434/v1`, model
  `hf.co/LiquidAI/LFM3-1.7B-GGUF:Q4_K_M`), LM Studio — ChiSurf starts nothing.
- **Another model:** put a Hugging Face GGUF reference (`repo:quant`) or the
  path of a `.gguf` file in the text model field.
- The sampling is Liquid AI's recommendation for tool use (temperature 0.1,
  top-k 50, repetition penalty 1.1). LFM3 reasons before it answers, so the
  token limit covers that reasoning as well. Turning reasoning off
  (`"reasoning": false` in the local block of `ai_api_settings.json`) makes
  each step about three times faster but the model loses its way in
  multi-step jobs — measured, half the routine analyses then fail.

LFM3 is small. It drives the routine chains — load, fit, report — well; for a
long open-ended analysis a hosted model is the stronger choice.

## Models

**Fetch models** asks the provider what it offers and splits the answer into
text-capable and image-capable models, in the background, and fills the two
pick lists under the model fields (**Fetched text models**, **Fetched image
models**). Each model is a text field, so if the provider does not list a model
you know exists, type its id; a pick from the list sets the field.

- **Text model** — the agent panel and curve triage.
- **Image model** — plugin-icon generation only.

## Generation settings

Collapsed by default because the defaults are sensible.

- **Temperature** — randomness. Lower is more repeatable; 0.3 is the default.
- **Top-p** — nucleus sampling. Leave it alone unless you know why you are
  changing it.
- **Max tokens** — the ceiling on a single reply. Providers *reserve* this
  amount, so an oversized value can be refused outright (HTTP 402) even when
  the reply would have been short.

## Test connection, Save and Reset

**Save** writes the current provider's settings (they are also saved as you
edit). **Reset** puts the provider's fields back to their defaults without
saving; press **Save** to keep them. The result of each action appears in the
line under the buttons.

### Test connection

Asks the endpoint for its model list. It checks that the URL is reachable and
the key is accepted; it does not check that the model you selected can actually
run. A failure names what went wrong — a bad host, a rejected key, or an
endpoint that does not publish a model list.

## Further reading

- [Settings reference](docs/reference/settings.md)
