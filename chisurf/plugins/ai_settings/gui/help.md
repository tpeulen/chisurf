# AI Settings

One endpoint per provider, with separate models for text and for image
generation. ChiSurf uses these settings for the agent panel in the code editor,
for AI-assisted curve triage, and for generating plugin icons.

## Providers

The list is the provider table the rest of the application uses, so anything you
can select here works everywhere. It is ordered by where your data goes:

| Provider | Notes |
|---|---|
| **Mistral (EU)** | The default. Data stays in the EU. |
| **Local** | Ollama, LM Studio or anything else speaking the OpenAI API on your own machine. No key needed, nothing leaves the computer. |
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

The key is drawn as stars. **Show key** (the eye button of the Qt window) shows it
in clear text for this session only; changing the provider hides it again and the
choice is never saved. Enter, or a click elsewhere, saves the key and tests the
endpoint.

To stop using a key, clear the field and press **Save**.

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
