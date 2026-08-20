from __future__ import annotations

import json
import logging
import os
import pathlib

from chisurf.core.settings.path_utils import get_path

_LOG = logging.getLogger(__name__)

# Provider definitions: display_name -> (key, default_base_url, api_key_url, env_var)
#
# Ordered by where the data is processed, not by market share. ChiSurf's users
# are largely European labs working with unpublished measurements, so the
# providers that keep the data in the EEA — or on the machine — come first;
# sending it to a third country should be a deliberate choice, not the one a
# user lands on by default.
PROVIDERS: dict[str, tuple[str, str, str, str]] = {
    "Mistral (EU)": ("mistral", "https://api.mistral.ai/v1", "https://console.mistral.ai/api-keys/", "MISTRAL_API_KEY"),
    "Local (Ollama, LMStudio, ...)": ("local", "http://localhost:11434/v1", "", ""),
    "OpenAI (ChatGPT)": ("openai", "https://api.openai.com/v1", "https://platform.openai.com/api-keys", "OPENAI_API_KEY"),
    "OpenRouter": ("openrouter", "https://openrouter.ai/api/v1", "https://openrouter.ai/keys", "OPENROUTER_API_KEY"),
    "Custom (OpenAI-compatible)": ("custom", "", "", ""),
}

LEGACY_PROVIDER_KEYS = {
    "openai_api": "openai",
    "mistral_api": "mistral",
    "local_llm": "local",
}

# Default settings for each provider
DEFAULT_PROVIDER_SETTINGS = {
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "text_model": "gpt-4o",
        "model": "gpt-4o",
        "image_model": "gpt-image-2",
        "api_key": "",
        "temperature": 0.3,
        "top_p": 0.9,
        "max_tokens": 4096,
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "text_model": "openai/gpt-4o-mini",
        "model": "openai/gpt-4o-mini",
        "image_model": "",
        "api_key": "",
        "temperature": 0.3,
        "top_p": 0.9,
        "max_tokens": 4096,
    },
    "mistral": {
        "base_url": "https://api.mistral.ai/v1",
        # The large model, not the small one. The difference shows on the job
        # that matters here — following a described tool catalogue and reading
        # before answering. On the small model a bare, misspelled term
        # ("rhem weller") was answered by *correcting the user* to a different
        # subject; the large one finds the page.
        "text_model": "mistral-large-latest",
        "model": "mistral-large-latest",
        "image_model": "mistral-medium-latest",
        "api_key": "",
        "temperature": 0.3,
        "top_p": 0.9,
        "max_tokens": 4096,
    },
    "local": {
        "base_url": "http://localhost:11434/v1",
        "text_model": "llama3.2",
        "model": "llama3.2",
        "image_model": "",
        "api_key": "",
        "temperature": 0.3,
        "top_p": 0.9,
        "max_tokens": 4096,
    },
    "custom": {
        "base_url": "",
        "text_model": "",
        "model": "",
        "image_model": "",
        "api_key": "",
        "temperature": 0.3,
        "top_p": 0.9,
        "max_tokens": 4096,
    },
}

#: Provider a fresh install starts on.  Mistral processes in the EU, so the
#: out-of-the-box configuration keeps measurements inside the EEA; anything
#: else is one choice away in Settings -> AI.
DEFAULT_PROVIDER = "mistral"

DEFAULT_SETTINGS = {
    "provider": DEFAULT_PROVIDER,
    **DEFAULT_PROVIDER_SETTINGS[DEFAULT_PROVIDER],
}


def normalize_provider_key(provider: str | None) -> str:
    """Return the canonical provider key for saved or legacy settings."""
    if not provider:
        return DEFAULT_PROVIDER
    return LEGACY_PROVIDER_KEYS.get(provider, provider)


def _get_settings_path() -> pathlib.Path:
    """Return path to AI settings JSON file."""
    return get_path('settings') / 'ai_api_settings.json'


def get_api_settings(provider: str | None = None) -> dict:
    """
    Load AI API settings from JSON file with env var fallbacks.

    Priority: settings file > environment variables > defaults.

    Args:
        provider: If specified, return settings for this provider.
                 If None, return settings for the currently selected provider.

    Returns:
        dict: Settings for the specified/provider
    """
    settings_path = _get_settings_path()

    # Load all settings from file
    all_settings = {}
    if settings_path.is_file():
        try:
            with open(settings_path, encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, dict):
                    all_settings = data
        except (OSError, json.JSONDecodeError):
            # Fall back to defaults, but say so: silently reverting every
            # provider to defaults looks to the user like their keys vanished.
            _LOG.exception("Could not read AI settings from %s; using defaults", settings_path)

    if 'base_url' in all_settings and not any(
        key in all_settings for key in DEFAULT_PROVIDER_SETTINGS
    ):
        legacy_provider = normalize_provider_key(all_settings.get('provider'))
        all_settings = {
            legacy_provider: all_settings,
            'selected_provider': legacy_provider,
        }

    # Determine which provider to get settings for
    if provider is None:
        # Get the selected provider, or the shipped default (EU-hosted).
        provider = all_settings.get('selected_provider', DEFAULT_PROVIDER)
    provider = normalize_provider_key(provider)

    # Get settings for the specified provider, falling back to defaults
    provider_settings = all_settings.get(provider, {})

    # Merge with defaults for this provider
    defaults = DEFAULT_PROVIDER_SETTINGS.get(provider, {})
    result = {**defaults, **provider_settings}
    text_model = str(
        provider_settings.get('text_model')
        or provider_settings.get('model')
        or defaults.get('text_model')
        or defaults.get('model')
        or ''
    ).strip()
    image_model = str(result.get('image_model') or '').strip()
    result['text_model'] = text_model
    result['model'] = text_model
    result['image_model'] = image_model

    # Ensure we have the provider field
    result['provider'] = provider

    # The docstring has always promised "settings file > environment variables >
    # defaults", but the environment step was never implemented -- so a user who
    # exported MISTRAL_API_KEY saw an empty key box here, triage reported "no LLM
    # configured", and the agent panel showed the provider as unset. Three call
    # sites had each grown their own fallback to work around it
    # (llm.LLMSettings.from_provider, plugin_manager icons.api_key_for_provider);
    # doing it once, here, is what makes those agree.
    if not str(result.get('api_key') or '').strip():
        env_key = get_provider_api_key(provider)
        if env_key:
            result['api_key'] = env_key
            result['api_key_source'] = 'environment'

    return result


def save_api_settings(settings: dict, provider: str | None = None) -> bool:
    """Save AI API settings for a specific provider to JSON file."""
    settings_path = _get_settings_path()
    settings_path.parent.mkdir(parents=True, exist_ok=True)

    # Load existing settings
    all_settings = {}
    if settings_path.is_file():
        try:
            with open(settings_path, encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, dict):
                    all_settings = data
        except (OSError, json.JSONDecodeError):
            # Refuse rather than overwrite. Carrying on with ``all_settings = {}``
            # would rewrite the file with *only* this provider's block, deleting
            # every other provider's key because the load failed.
            _LOG.exception(
                "Refusing to save AI settings: %s exists but could not be read. "
                "Move it aside to start fresh.", settings_path,
            )
            return False

    # Determine which provider to save settings for
    if provider is None:
        provider = settings.get('provider', DEFAULT_PROVIDER)
    provider = normalize_provider_key(provider)

    text_model = str(settings.get('text_model') or settings.get('model') or '').strip()
    settings = {**settings, 'text_model': text_model, 'model': text_model}

    # Update settings for this provider
    all_settings[provider] = {
        k: v for k, v in settings.items()
        if k in ['base_url', 'text_model', 'model', 'image_model', 'api_key', 'temperature', 'top_p', 'max_tokens']
    }

    # Update selected provider
    all_settings['selected_provider'] = provider

    return _write_settings_file(settings_path, all_settings)


def _write_settings_file(settings_path, all_settings) -> bool:
    """Write the settings JSON atomically, readable only by this user.

    Two problems with the plain ``open(path, 'w')`` this replaces. It leaves
    API keys world-readable under the default umask; and a crash part-way
    through ``json.dump`` truncates the file, taking *every* provider's key with
    it. Writing a private temporary file in the same directory and renaming it
    over the target fixes both: the rename is atomic, so a reader sees either
    the old file or the new one.
    """
    import os
    import tempfile

    handle, temporary = tempfile.mkstemp(
        dir=str(settings_path.parent), prefix=".ai_api_settings-", suffix=".json"
    )
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as f:
            json.dump(all_settings, f, indent=2)
        # Before the rename, so the key is never briefly world-readable.
        os.chmod(temporary, 0o600)
        os.replace(temporary, settings_path)
    except OSError:
        _LOG.exception("Could not write AI settings to %s", settings_path)
        try:
            os.unlink(temporary)
        except OSError:
            pass
        return False
    return True


#: Suffixes people actually use when exporting a provider key. The table
#: above names one canonical variable per provider, but a shell profile is
#: just as likely to hold ``MISTRAL_KEY`` or ``OPENAI_API_TOKEN`` — and a key
#: that is present but looked for under the wrong name reads to the user as
#: "the provider does not work".
_KEY_ENV_SUFFIXES = ('_API_KEY', '_KEY', '_API_TOKEN', '_TOKEN')


def provider_key_env_names(provider: str) -> list[str]:
    """Return the environment variables that may hold a provider's API key.

    The provider's declared variable comes first, followed by the usual
    variations on its name.

    Parameters
    ----------
    provider : str
        Canonical provider key, e.g. ``"mistral"``.

    Returns
    -------
    list of str
        Candidate variable names, most canonical first, without duplicates.

    Examples
    --------
    >>> provider_key_env_names('mistral')[:2]
    ['MISTRAL_API_KEY', 'MISTRAL_KEY']
    """
    provider = normalize_provider_key(provider)
    declared = ''
    for _display, (key, _url, _api_url, env_var) in PROVIDERS.items():
        if key == provider:
            declared = env_var
            break
    if not declared and provider in ('local', 'custom'):
        return []

    stem = declared
    for suffix in _KEY_ENV_SUFFIXES:
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
            break
    if not stem:
        stem = provider.upper()

    names = [declared] if declared else []
    for suffix in _KEY_ENV_SUFFIXES:
        candidate = f'{stem}{suffix}'
        if candidate not in names:
            names.append(candidate)
    return names


def get_provider_api_key(provider: str) -> str:
    """Return the API key found in the environment for a provider.

    Parameters
    ----------
    provider : str
        Canonical provider key, e.g. ``"openrouter"``.

    Returns
    -------
    str
        The first non-empty candidate variable's value, or ``""``.
    """
    for name in provider_key_env_names(provider):
        value = os.environ.get(name, '').strip()
        if value:
            return value
    return ''


def get_api_key() -> str:
    """Get API key from settings or environment variable."""
    settings = get_api_settings()
    api_key = settings.get('api_key', '')

    if not api_key:
        api_key = get_provider_api_key(settings.get('provider', ''))

    return api_key.strip()


def get_base_url() -> str:
    """Get base URL for API."""
    settings = get_api_settings()
    return settings.get('base_url', '').strip().rstrip('/')


def get_model() -> str:
    """Get chat model name."""
    settings = get_api_settings()
    return settings.get('text_model', settings.get('model', '')).strip()


def get_image_model() -> str:
    """Get image generation model name."""
    settings = get_api_settings()
    model = settings.get('image_model', '').strip()
    provider = settings.get('provider', DEFAULT_PROVIDER)
    if model and (provider != 'openai' or _looks_like_image_model(model)):
        return model
    if provider == 'openai':
        return 'gpt-image-2'
    return ''


def _looks_like_image_model(model: str) -> bool:
    """Return whether a model name looks suitable for image generation."""
    normalized = model.lower()
    return any(marker in normalized for marker in ('image', 'dall-e', 'gpt-image'))


def model_capabilities(model: dict | str, provider: str = "") -> set[str]:
    """Infer model capabilities from endpoint metadata and model id."""
    if isinstance(model, str):
        model_id = model
        metadata = {}
    else:
        model_id = str(model.get('id') or model.get('name') or '')
        metadata = model
    normalized_id = model_id.lower()
    capabilities = set()

    metadata_values = _flatten_model_metadata(metadata)
    if any(_metadata_mentions(value, 'image') for value in metadata_values):
        capabilities.add('image')
    if any(_metadata_mentions(value, 'text', 'chat', 'completion', 'response') for value in metadata_values):
        capabilities.add('text')

    if _looks_like_image_model(model_id):
        capabilities.add('image')

    if provider == 'mistral' and normalized_id.startswith('mistral-'):
        capabilities.update({'text', 'image'})

    non_text_markers = (
        'embedding',
        'embed',
        'moderation',
        'whisper',
        'tts',
        'audio',
        'realtime',
        'transcribe',
        'video',
    )
    is_non_text_model = any(marker in normalized_id for marker in non_text_markers) or any(
        any(marker in value for marker in non_text_markers)
        for value in metadata_values
    )
    if not capabilities and not is_non_text_model:
        capabilities.add('text')
    if 'image' in capabilities and not is_non_text_model:
        capabilities.add('text') if provider == 'mistral' else None
    return capabilities


def split_models_by_capability(models: list[dict | str], provider: str = "") -> tuple[list[str], list[str]]:
    """Split model metadata into text and image model id lists."""
    text_models = []
    image_models = []
    for model in models:
        model_id = model if isinstance(model, str) else model.get('id') or model.get('name') or ''
        model_id = str(model_id).strip()
        if not model_id:
            continue
        capabilities = model_capabilities(model, provider=provider)
        if 'text' in capabilities:
            text_models.append(model_id)
        if 'image' in capabilities:
            image_models.append(model_id)
    return sorted(set(text_models)), sorted(set(image_models))


def _flatten_model_metadata(value):
    """Yield scalar metadata values from nested model metadata."""
    if isinstance(value, dict):
        for nested in value.values():
            yield from _flatten_model_metadata(nested)
    elif isinstance(value, (list, tuple, set)):
        for nested in value:
            yield from _flatten_model_metadata(nested)
    else:
        yield str(value).lower()


def _metadata_mentions(value: str, *needles: str) -> bool:
    """Return whether a metadata value mentions any capability keyword."""
    return any(needle in value for needle in needles)


def get_temperature() -> float:
    """Get temperature setting."""
    settings = get_api_settings()
    return float(settings.get('temperature', 0.3))


def get_top_p() -> float:
    """Get top_p setting."""
    settings = get_api_settings()
    return float(settings.get('top_p', 0.9))


def get_max_tokens() -> int:
    """Get max tokens setting."""
    settings = get_api_settings()
    return int(settings.get('max_tokens', 4096))


def get_provider() -> str:
    """Get the LLM provider key."""
    settings = get_api_settings()
    return settings.get('provider', DEFAULT_PROVIDER)


def get_available_providers() -> list[str]:
    """Get list of providers that have saved settings."""
    settings_path = _get_settings_path()
    if not settings_path.is_file():
        return list(DEFAULT_PROVIDER_SETTINGS.keys())

    try:
        with open(settings_path, encoding='utf-8') as f:
            data = json.load(f)
            if isinstance(data, dict):
                # Return providers that have settings plus the selected one
                providers = set(data.keys()) - {'selected_provider'}
                selected = data.get('selected_provider', DEFAULT_PROVIDER)
                providers.add(selected)
                return list(providers)
    except Exception:
        pass

    return list(DEFAULT_PROVIDER_SETTINGS.keys())
