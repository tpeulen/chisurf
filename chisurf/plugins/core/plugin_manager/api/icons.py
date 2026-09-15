"""Generate a plugin icon through an AI image provider.

Lifted out of the manager widget, where it was roughly 60 % of a 1856-line file
and every network call blocked the GUI thread -- up to five minutes of frozen
window, with ``QApplication.processEvents()`` as the only mitigation and a
``time.sleep`` on a server-supplied ``Retry-After``. Here it is ordinary
functions over an explicit :class:`IconConfig`, so the caller decides which
thread pays, and the existing tests can call them directly instead of binding
unbound methods to a ``SimpleNamespace``.

Behaviour is otherwise unchanged: same endpoints, same retry policy, same prompt.
"""

from __future__ import annotations

import base64
import logging
import os
from dataclasses import dataclass

from chisurf.core.settings import ai_settings

logger = logging.getLogger(__name__)


class AIIconRateLimitError(RuntimeError):
    """The provider kept answering 429 after the retry budget ran out."""


@dataclass
class IconConfig:
    """Where to ask for an icon, and as whom.

    Attributes
    ----------
    provider : str
        ``"mistral"``, ``"openai"``, or another OpenAI-compatible provider key.
    endpoint : str
        Base URL, no trailing slash.
    model : str
        Image model name.

    """

    provider: str = "mistral"
    endpoint: str = ""
    model: str = ""

    @property
    def base_url(self) -> str:
        """The endpoint with any trailing slash removed."""
        return self.endpoint.strip().rstrip("/")


def default_icon_generation_values(provider: str) -> tuple[str, str]:
    """Endpoint and model defaults for *provider*."""
    settings = ai_settings.get_api_settings(provider)
    endpoint = str(settings.get("base_url", "")).strip()
    model = str(settings.get("image_model", "")).strip()
    if provider == "openai" and model and not ai_settings._looks_like_image_model(model):
        model = ""
    if provider == "mistral":
        endpoint = endpoint or "https://api.mistral.ai/v1"
        model = model or "mistral-medium-latest"
    elif provider == "openai":
        endpoint = endpoint or "https://api.openai.com/v1"
        model = model or "gpt-image-2"
    else:
        model = model or str(settings.get("image_model", "")).strip()
    return endpoint.rstrip("/"), model


def api_key_for_provider(provider: str) -> str:
    """The provider's API key from AI Settings, falling back to its env var."""
    settings = ai_settings.get_api_settings(provider)
    api_key = str(settings.get("api_key", "")).strip()
    if api_key:
        return api_key
    for _display, (key, _url, _api_url, env_var) in ai_settings.PROVIDERS.items():
        if key == provider and env_var:
            return os.environ.get(env_var, "").strip()
    return ""


def mistral_endpoint_url(endpoint: str, path: str) -> str:
    """Normalise a Mistral API URL for a relative *path*."""
    base_url = str(endpoint or "").strip().rstrip("/")
    if not base_url:
        raise ValueError("Icon generation endpoint is empty")
    if base_url.endswith("/beta"):
        base_url = base_url[:-5]
    return f"{base_url}/{path.lstrip('/')}"


def retry_after_seconds(response) -> float | None:
    """The ``Retry-After`` delay on a response, when it carries one."""
    headers = getattr(response, "headers", {}) or {}
    value = headers.get("Retry-After") or headers.get("retry-after")
    if value is None:
        return None
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return None


def extract_mistral_file_id(data) -> str | None:
    """The first generated image file id anywhere in a Mistral response."""
    if isinstance(data, dict):
        if data.get("type") == "tool_file" and data.get("file_id"):
            return data["file_id"]
        if data.get("file_id") and data.get("file_type") in (None, "png", "image/png"):
            return data["file_id"]
        for value in data.values():
            file_id = extract_mistral_file_id(value)
            if file_id:
                return file_id
    elif isinstance(data, list):
        for value in data:
            file_id = extract_mistral_file_id(value)
            if file_id:
                return file_id
    return None


def post_mistral_json_with_retries(endpoint, path, headers, payload, timeout, *, sleep=None):
    """POST JSON to Mistral, retrying a bounded number of times on HTTP 429.

    Parameters
    ----------
    endpoint : str
        Base URL of the Mistral API.
    path : str
        Endpoint path relative to *endpoint* (``"agents"``, ``"conversations"``).
    headers : dict
        Request headers, including the bearer token.
    payload : dict
        JSON body.
    timeout : float
        Per-request timeout in seconds.
    sleep : callable, optional
        Injected so a caller on the GUI thread can yield instead of blocking,
        and so tests need not actually wait. Defaults to :func:`time.sleep`.

    Raises
    ------
    AIIconRateLimitError
        When the provider is still rate-limiting after the last attempt.

    """
    import time

    from chisurf.core.support import http

    sleep = sleep or time.sleep
    max_attempts = 3
    last_response = None
    for attempt in range(max_attempts):
        response = http.post(
            mistral_endpoint_url(endpoint, path),
            headers=headers,
            json=payload,
            timeout=timeout,
        )
        if response.status_code != 429:
            response.raise_for_status()
            return response

        last_response = response
        if attempt == max_attempts - 1:
            break
        retry_after = retry_after_seconds(response)
        delay = retry_after if retry_after is not None else 2 ** attempt
        logger.warning(
            "Mistral icon generation rate-limited on /%s; retrying in %.1f seconds",
            path,
            delay,
        )
        sleep(delay)

    detail = ""
    if last_response is not None and getattr(last_response, "text", ""):
        detail = f": {last_response.text[:300]}"
    raise AIIconRateLimitError(
        "Mistral returned 429 Too Many Requests after retrying. "
        "Wait before regenerating, or increase the Workspace rate limits in Mistral Studio"
        f"{detail}"
    )


def request_openai_compatible_icon_bytes(config: IconConfig, plugin_info, prompt=None) -> bytes:
    """Request an icon through an OpenAI-compatible image endpoint."""
    from chisurf.core.support import http

    base_url = config.base_url
    image_model = str(config.model or "").strip()
    api_key = api_key_for_provider(config.provider)
    if not base_url:
        raise ValueError("Icon generation endpoint is empty")
    if not image_model:
        raise ValueError("Icon generation model is empty")

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    if not prompt:
        prompt = ai_icon_prompt(plugin_info)
    payload = {
        "model": image_model,
        "prompt": prompt,
        "n": 1,
        "size": "1024x1024",
        "output_format": "png",
    }
    url = f"{base_url}/images/generations"
    response = http.post(url, headers=headers, json=payload, timeout=90)
    if response.status_code >= 400:
        minimal_payload = dict(payload)
        minimal_payload.pop("output_format", None)
        response = http.post(url, headers=headers, json=minimal_payload, timeout=90)
    if response.status_code >= 400:
        raise RuntimeError(f"{response.status_code}: {response.text[:300]}")

    data = response.json()
    images = data.get("data") or []
    if not images:
        raise ValueError("AI provider returned no image data")
    first = images[0]
    if first.get("b64_json"):
        return base64.b64decode(first["b64_json"])
    if first.get("url"):
        image_response = http.get(first["url"], timeout=60)
        image_response.raise_for_status()
        return image_response.content
    raise ValueError("AI provider returned neither b64_json nor url")


def request_mistral_generated_icon_bytes(
    config: IconConfig, plugin_info, prompt=None, *, sleep=None
) -> bytes:
    """Request an icon through Mistral Agents image generation."""
    from chisurf.core.support import http

    model = str(config.model or "").strip()
    api_key = api_key_for_provider("mistral")
    if not config.base_url:
        raise ValueError("Icon generation endpoint is empty")
    if not model:
        raise ValueError("Icon generation model is empty")
    if not api_key:
        raise ValueError("Mistral API key is missing in AI Settings")

    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    agent_payload = {
        "model": model,
        "name": "ChiSurf Plugin Icon Generator",
        "description": "Agent used by ChiSurf Plugin Manager to generate plugin icons.",
        "instructions": (
            "Use the image generation tool to create a single square icon. "
            "Return the generated image file."
        ),
        "tools": [{"type": "image_generation"}],
        "completion_args": {"temperature": 0.3, "top_p": 0.95},
    }
    agent_response = post_mistral_json_with_retries(
        config.endpoint, "agents", headers=headers, payload=agent_payload,
        timeout=60, sleep=sleep,
    )
    agent_id = agent_response.json().get("id")
    if not agent_id:
        raise ValueError("Mistral did not return an agent id")

    if not prompt:
        prompt = ai_icon_prompt(plugin_info)
    conversation_response = post_mistral_json_with_retries(
        config.endpoint, "conversations",
        headers=headers,
        payload={"agent_id": agent_id, "inputs": prompt, "stream": False},
        timeout=120, sleep=sleep,
    )
    file_id = extract_mistral_file_id(conversation_response.json())
    if not file_id:
        raise ValueError("Mistral response did not contain a generated image file id")

    file_response = http.get(
        mistral_endpoint_url(config.endpoint, f"files/{file_id}/content"),
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=60,
    )
    if file_response.status_code == 404:
        file_response = http.get(
            mistral_endpoint_url(config.endpoint, f"files/{file_id}/download"),
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=60,
        )
    file_response.raise_for_status()
    return file_response.content


def request_icon_bytes(config: IconConfig, plugin_info, prompt=None, *, sleep=None) -> bytes:
    """Request a generated icon from whichever provider *config* names."""
    if config.provider == "mistral":
        return request_mistral_generated_icon_bytes(config, plugin_info, prompt=prompt, sleep=sleep)
    return request_openai_compatible_icon_bytes(config, plugin_info, prompt=prompt)


def icon_visual_elements(plugin_name: str, description: str) -> str:
    """Visual elements for the prompt, inferred from the plugin's own words."""
    return _by_topic(plugin_name, description)[0]


def icon_symbol_pair(plugin_name: str, description: str) -> tuple[str, str]:
    """Primary and secondary icon symbols, inferred from plugin metadata."""
    return _by_topic(plugin_name, description)[1]


#: (matching terms, visual elements, (primary symbol, secondary symbol)).
#: One table rather than the two eight-branch if-chains this replaced, whose
#: keyword lists were duplicated verbatim and could drift apart.
_TOPICS: tuple[tuple[tuple[str, ...], str, tuple[str, str]], ...] = (
    (("fcs", "correlation"),
     "fluorescence correlation data, smooth decay curve, focused detection volume",
     ("correlation curve", "confocal detection spot")),
    (("decay", "lifetime", "tcspc"),
     "fluorescence lifetime decay, photon timing, clean exponential curve",
     ("decay curve", "single photon pulse")),
    (("molecule", "protein", "structure", "trajectory"),
     "molecular structure, connected atoms, scientific 3D geometry",
     ("molecular node network", "subtle 3D depth cue")),
    (("image", "microscopy", "camera"),
     "scientific image analysis, microscope field, focused signal",
     ("microscope image frame", "bright analytical feature")),
    (("database", "sample", "repository"),
     "organized scientific records, structured data, sample archive",
     ("stacked data cylinder", "sample marker")),
    (("plot", "graph", "histogram"),
     "scientific plotting, measured data trend, clean analytical chart",
     ("clean graph curve", "data point cluster")),
    (("settings", "manager", "setup", "plugin"),
     "software configuration, modular plugin component, scientific tool",
     ("modular hexagon", "calibration dot")),
)

_FALLBACK = (
    "scientific measurement, analytical data, precise research instrument",
    ("scientific instrument glyph", "measured signal curve"),
)


def _by_topic(plugin_name: str, description: str):
    """Match a plugin's words against :data:`_TOPICS`."""
    terms = f"{plugin_name} {description}".lower()
    for keywords, elements, symbols in _TOPICS:
        if any(term in terms for term in keywords):
            return elements, symbols
    return _FALLBACK


def ai_icon_prompt(plugin_info) -> str:
    """Build the image-generation prompt for one plugin."""
    plugin_name = plugin_info["name"]
    description = (plugin_info.get("doc") or "Scientific data analysis plugin.").strip()
    one_sentence = " ".join(description.splitlines()).strip()
    if "." in one_sentence:
        one_sentence = one_sentence.split(".", 1)[0].strip() + "."
    visual_elements = icon_visual_elements(plugin_name, description)
    primary_symbol, secondary_symbol = icon_symbol_pair(plugin_name, description)

    return f"""Scientific Software Icon Template

    Create a single professional application icon for scientific software.

    Output requirements

    Square icon, 128x128 pixels
    Toolbar/app icon style
    Centered composition
    One clear visual concept only
    Clean silhouette recognizable at 16x16 and 32x32 pixels
    High contrast
    Minimal details
    Modern scientific software aesthetic
    Subtle depth and lighting
    Transparent or simple neutral background
    No text
    No letters
    No numbers
    No UI screenshots
    No watermark
    No borders
    No decorative clutter

    Scientific context
    Plugin: {plugin_name}

    Purpose:
    {one_sentence}

    Visual metaphor
    Represent:
    {visual_elements}

    Combine:
    {primary_symbol} + {secondary_symbol}

    Style:
    scientific visualization, vector-like clarity, professional research software, publication-quality graphics, simple geometric forms, visually balanced, elegant and memorable.

    Composition

    Subject centered
    Occupies ~70% of icon area
    Strong foreground/background separation
    Distinct shape visible at very small sizes
    Limited color palette
    Avoid thin lines
    Avoid small labels
    Avoid complex scenes

    Negative prompts
    text, letters, words, numbers, watermark, screenshot, interface, toolbar, menu, browser window, photorealistic scene, multiple unrelated objects, crowded composition, excessive detail, blurry image, low contrast"""
