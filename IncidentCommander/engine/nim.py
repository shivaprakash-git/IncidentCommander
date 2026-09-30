"""Thin NVIDIA NIM client (chat + embeddings) over `requests`.

Keys come from engine.config only and are never logged or put in messages.
Any missing key or persistent failure raises NimUnavailable so callers can
degrade gracefully. Resolved model ids are cached in cache/nim_models.json.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Optional

import numpy as np
import requests

from . import config

BASE_URL = "https://integrate.api.nvidia.com/v1"
MODELS_URL = f"{BASE_URL}/models"
CHAT_URL = f"{BASE_URL}/chat/completions"
EMBED_URL = f"{BASE_URL}/embeddings"

TIMEOUT = 60
RETRIES = 3
CHAT_TIMEOUT = 420      # hosted gemma can queue for minutes (a 1-line prompt took 211 s)
CHAT_RETRIES = 1
BATCH = 32
MODELS_CACHE = config.CACHE_DIR / "nim_models.json"

PREFERRED_CHAT = "google/gemma-4-31b-it"
FALLBACK_EMBED = "nvidia/llama-3.2-nv-embedqa-1b-v2"


class NimUnavailable(RuntimeError):
    """NIM cannot be used (missing key, network error, persistent API failure)."""


def _key(name: str) -> str:
    value = getattr(config, name, "")
    if not value:
        raise NimUnavailable(f"{name} is not set (add it to .env)")
    return value


def _headers(key_name: str) -> dict:
    return {"Authorization": f"Bearer {_key(key_name)}", "Accept": "application/json"}


def _verify() -> "bool | str":
    """TLS trust: certifi plus the Windows root store (corporate proxies re-sign TLS)."""
    if sys.platform != "win32":
        return True
    bundle = config.CACHE_DIR / "ca_bundle.pem"
    if not bundle.exists():
        import certifi
        import ssl
        pems = [Path(certifi.where()).read_text()]
        for store in ("ROOT", "CA"):
            try:
                pems += [ssl.DER_cert_to_PEM_cert(der) for der, enc, _ in ssl.enum_certificates(store)
                         if enc == "x509_asn"]
            except OSError:
                pass
        bundle.parent.mkdir(parents=True, exist_ok=True)
        bundle.write_text("\n".join(pems))
    return str(bundle)


def _request(method: str, url: str, key_name: str, **kwargs) -> requests.Response:
    """Send with retries on 429/5xx/network errors; return the final response."""
    headers = _headers(key_name)
    timeout = kwargs.pop("timeout", TIMEOUT)
    retries = kwargs.pop("retries", RETRIES)
    kwargs.setdefault("verify", _verify())
    last = "no response"
    for attempt in range(retries + 1):
        try:
            send = requests.get if method == "GET" else requests.post
            resp = send(url, headers=headers, timeout=timeout, **kwargs)
        except requests.RequestException as exc:
            last = type(exc).__name__
        else:
            if resp.status_code != 429 and resp.status_code < 500:
                return resp
            last = f"HTTP {resp.status_code}"
        if attempt < retries:
            time.sleep(2 ** attempt)
    raise NimUnavailable(f"{url} failed after {retries + 1} attempts ({last})")


def _fail(resp: requests.Response) -> NimUnavailable:
    return NimUnavailable(f"{resp.url} returned HTTP {resp.status_code}: {resp.text[:300]}")


def pick_models(ids: list[str]) -> dict:
    """Choose chat and embedding model ids from a /v1/models id listing."""
    low = {i: i.lower() for i in ids}
    embeds = [i for i in ids if "embed" in low[i]]
    embed = next((i for i in embeds if "nemotron" in low[i]), None)
    if embed is None and FALLBACK_EMBED in ids:
        embed = FALLBACK_EMBED
    if embed is None and embeds:
        embed = embeds[0]

    chat = PREFERRED_CHAT if PREFERRED_CHAT in ids else None
    if chat is None:
        gemma = [i for i in ids if "gemma" in low[i] and ("-it" in low[i] or "instruct" in low[i])]
        chat = sorted(gemma)[-1] if gemma else None
    if chat is None:
        chatty = [i for i in ids if "embed" not in low[i] and any(
            t in low[i] for t in ("instruct", "chat", "-it"))]
        chat = chatty[0] if chatty else None
    return {"chat": chat, "embed": embed}


def resolve_models(refresh: bool = False) -> dict:
    """Return {"chat": id, "embed": id}, using the disk cache unless refresh."""
    if not refresh and MODELS_CACHE.exists():
        try:
            cached = json.loads(MODELS_CACHE.read_text())
            if cached.get("chat") and cached.get("embed"):
                return cached
        except (OSError, ValueError):
            pass
    resp = _request("GET", MODELS_URL, "NVIDIA_CHAT_API_KEY")
    if resp.status_code != 200:
        raise _fail(resp)
    ids = [m["id"] for m in resp.json().get("data", []) if "id" in m]
    models = pick_models(ids)
    if not models["chat"] or not models["embed"]:
        raise NimUnavailable(f"could not select models from catalog: {models}")
    MODELS_CACHE.parent.mkdir(parents=True, exist_ok=True)
    MODELS_CACHE.write_text(json.dumps(models, indent=2))
    return models


def embed_model() -> str:
    return resolve_models()["embed"]


def embed(texts: list[str], input_type: str = "passage") -> np.ndarray:
    """Embed texts (batches of 32); returns a float32 array (len(texts), dim)."""
    _key("NVIDIA_EMBED_API_KEY")
    if not texts:
        return np.zeros((0, 0), dtype=np.float32)
    model = embed_model()
    out: list[list[float]] = []
    extras: Optional[dict] = {"input_type": input_type, "truncate": "END"}
    for start in range(0, len(texts), BATCH):
        body = {"model": model, "input": texts[start:start + BATCH], "encoding_format": "float"}
        resp = _request("POST", EMBED_URL, "NVIDIA_EMBED_API_KEY", json={**body, **(extras or {})})
        if resp.status_code == 400 and extras is not None:
            extras = None  # model does not accept input_type/truncate
            resp = _request("POST", EMBED_URL, "NVIDIA_EMBED_API_KEY", json=body)
        if resp.status_code != 200:
            raise _fail(resp)
        data = sorted(resp.json()["data"], key=lambda d: d.get("index", 0))
        out.extend(d["embedding"] for d in data)
    return np.asarray(out, dtype=np.float32)


def chat(messages: list[dict], temperature: float = 0.2, max_tokens: int = 1200) -> str:
    """Return the assistant text for a chat completion."""
    _key("NVIDIA_CHAT_API_KEY")
    body = {"model": resolve_models()["chat"], "messages": messages,
            "temperature": temperature, "max_tokens": max_tokens}
    resp = _request("POST", CHAT_URL, "NVIDIA_CHAT_API_KEY", json=body,
                    timeout=CHAT_TIMEOUT, retries=CHAT_RETRIES)
    if resp.status_code != 200:
        raise _fail(resp)
    try:
        return resp.json()["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, ValueError) as exc:
        raise NimUnavailable(f"unexpected chat response shape ({type(exc).__name__})") from exc
