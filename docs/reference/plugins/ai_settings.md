(plugin-ai_settings)=
# AI Settings

AI Settings plugin for configuring API providers and backends.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `ai_settings` |
| Menu path | Tools → **AI Settings** |
| Categories | Tools |
| Version | 1.0.0 |
| Surfaces | gui |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

### API Configuration

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Provider | `provider` | choice |  | choices: openai, mistral, local, custom | Configure one endpoint per provider. Switching reloads that provider's saved values. |
| Base URL | `base_url` | str |  |  | OpenAI-compatible API base URL for the selected provider. |
| API Key | `api_key` | secret |  |  | Bearer token for the endpoint. Pasting a key auto-saves it and tests the connection. Not needed for most local servers. |

### Models

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Text model | `text_model` | choice |  | choices: `available_text_models` | Used for chat, code editing, explanations, and other text tasks. Type a model id or pick from fetched models. |
| Image model | `image_model` | choice |  | choices: `available_image_models` | Used only for plugin icon and other image-generation tasks. |

### Generation Settings

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Temperature | `temperature` | float |  | 0.0 … 2.0 (step 0.1) | Sampling temperature (0 = deterministic, higher = more random). |
| Top-p | `top_p` | float |  | 0.0 … 1.0 (step 0.05) | Nucleus-sampling probability mass. |
| Max tokens | `max_tokens` | int |  | 1 … 1000000 | Maximum number of tokens to generate per response. |

## Source

- Plugin package: `chisurf/plugins/ai_settings/`
- Manifest: {src}`chisurf/plugins/ai_settings/manifest.json`
- UI spec: {src}`chisurf/plugins/ai_settings/gui/ai_settings.view.json`
