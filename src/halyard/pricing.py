"""Model pricing table and cost calculator.

Prices are USD per million tokens, snapshotted 2026-05.
Run `halyard update-pricing` to refresh from the live table.
"""

from __future__ import annotations

import hashlib
import os
import sys
import tempfile
import tomllib
import urllib.error
import urllib.request
from contextlib import suppress
from datetime import datetime
from pathlib import Path

# (input_per_mtok, output_per_mtok)
PRICING: dict[str, tuple[float, float]] = {
    # Anthropic
    "claude-opus-4-7": (15.00, 75.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-haiku-4-5-20251001": (0.80, 4.00),
    "claude-haiku-4-5": (0.80, 4.00),
    # OpenAI
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "o3": (10.00, 40.00),
    "o4-mini": (1.10, 4.40),
    # Google Gemini
    "gemini-2.5-pro": (1.25, 10.00),
    "gemini-2.5-flash": (0.15, 0.60),
    "gemini-3-pro": (1.25, 5.00),
    "gemini-3-flash": (0.075, 0.30),
    # DeepSeek
    "deepseek-v3": (0.27, 1.10),
    "deepseek-r1": (0.55, 2.19),
    # xAI Grok
    "grok-3": (3.00, 15.00),
    "grok-3-mini": (0.30, 0.50),
    # Mistral
    "mistral-large-latest": (2.00, 6.00),
    "mistral-small-latest": (0.10, 0.30),
}

# Anthropic prompt cache pricing multipliers (relative to input rate)
_CACHE_READ_MULTIPLIER = 0.10  # cache reads = 10% of input price
_CACHE_WRITE_MULTIPLIER = 1.25  # cache writes = 125% of input price

_LOCAL_PRICING_FILE = Path.home() / ".halyard" / "pricing.toml"
_REMOTE_URL = "https://raw.githubusercontent.com/Kormiloio/Halyard/main/pricing/models.toml"

# Cached merged table; computed once per process. Invalidated explicitly via
# invalidate_pricing_cache() when the user runs `halyard update-pricing`.
# Short-lived CLI processes never need mid-run invalidation.
_merged_table: dict[str, tuple[float, float]] | None = None


def _pricing_hash_path() -> Path:
    """Return the path for the stored pricing table SHA-256 hash."""
    return Path.home() / ".halyard" / "pricing-hash.txt"


def _check_pricing_hash(body: bytes) -> bool:
    """D-5: Detect silent changes to the remote pricing table.

    Computes SHA-256 of the fetched response body and compares against the
    hash stored in ~/.halyard/pricing-hash.txt.

    Returns True when hashes match (or no stored hash yet — first fetch).
    Returns False when the stored hash differs from the new hash.

    A warning is printed to stderr when the table has changed.  The new hash
    is NOT written here — the caller writes it only after accepting the table.
    """
    new_hash = hashlib.sha256(body).hexdigest()
    hash_path = _pricing_hash_path()

    if not hash_path.exists():
        # First fetch — no baseline yet; accept silently.
        return True

    stored = hash_path.read_text().strip()
    if not stored:
        return True

    if stored == new_hash:
        return True

    # Hash differs — warn before accepting.
    print(
        "[halyard] Warning: remote pricing table has changed. Review before accepting.",
        file=sys.stderr,
    )
    return False


class PricingFetchError(Exception):
    pass


def load_pricing_table() -> dict[str, tuple[float, float]]:
    """Return merged table: local overrides bundled. Cached per process."""
    global _merged_table
    if _merged_table is not None:
        return _merged_table

    local = _load_local_pricing()
    merged: dict[str, tuple[float, float]] = dict(PRICING)
    merged.update(local)
    _merged_table = merged
    return _merged_table


def _load_local_pricing() -> dict[str, tuple[float, float]]:
    if not _LOCAL_PRICING_FILE.exists():
        return {}
    try:
        data = tomllib.loads(_LOCAL_PRICING_FILE.read_text())
        return _parse_models_table(data)
    except (tomllib.TOMLDecodeError, ValueError) as e:
        print(
            f"[halyard] Warning: {_LOCAL_PRICING_FILE} is invalid — "
            f"custom pricing ignored. ({e})",
            file=sys.stderr,
        )
        return {}
    except OSError:
        return {}


def _parse_models_table(data: object) -> dict[str, tuple[float, float]]:
    if not isinstance(data, dict):
        raise ValueError("TOML root must be a table")
    models = data.get("models")
    if not isinstance(models, dict):
        raise ValueError("Missing [models] table")
    result: dict[str, tuple[float, float]] = {}
    for name, entry in models.items():
        if not isinstance(entry, dict):
            continue
        inp = entry.get("input")
        out = entry.get("output")
        if not isinstance(inp, (int, float)) or not isinstance(out, (int, float)):
            raise ValueError(f"Model {name!r} missing input/output prices")
        if inp <= 0 or out <= 0:
            raise ValueError(f"Model {name!r} has non-positive price")
        result[name] = (float(inp), float(out))
    return result


def _get_multipliers(data: dict[str, object], model: str) -> tuple[float, float]:
    """Return (cache_read_mult, cache_write_mult) for a model from raw toml data."""
    try:
        models = data.get("models", {})
        if not isinstance(models, dict):
            return _CACHE_READ_MULTIPLIER, _CACHE_WRITE_MULTIPLIER
        entry = models.get(model, {})
        if not isinstance(entry, dict):
            return _CACHE_READ_MULTIPLIER, _CACHE_WRITE_MULTIPLIER
        read_mult = float(entry.get("cache_read_multiplier", _CACHE_READ_MULTIPLIER))
        write_mult = float(entry.get("cache_write_multiplier", _CACHE_WRITE_MULTIPLIER))
        return read_mult, write_mult
    except (TypeError, ValueError):
        return _CACHE_READ_MULTIPLIER, _CACHE_WRITE_MULTIPLIER


def _load_local_toml_raw() -> dict[str, object] | None:
    if not _LOCAL_PRICING_FILE.exists():
        return None
    try:
        result: dict[str, object] = tomllib.loads(_LOCAL_PRICING_FILE.read_text())
        return result
    except tomllib.TOMLDecodeError:
        return None


def pricing_table_age_days() -> int | None:
    """Days since ~/.halyard/pricing.toml was last written. None if absent."""
    if not _LOCAL_PRICING_FILE.exists():
        return None
    mtime = _LOCAL_PRICING_FILE.stat().st_mtime
    age = datetime.now().timestamp() - mtime
    return int(age / 86400)


class PricingHashChangedError(Exception):
    """Raised when the remote pricing table has a different hash than the stored one."""


def update_pricing(timeout: int = 5, accept_changed: bool = False) -> tuple[int, int]:
    """Fetch remote table, validate, save locally.

    Returns (new_count, updated_count) — models added or updated.
    Raises PricingFetchError on network or validation failure.
    """
    try:
        req = urllib.request.Request(
            _REMOTE_URL,
            headers={"User-Agent": "halyard/update-pricing"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
    except urllib.error.URLError as exc:
        raise PricingFetchError(f"could not fetch pricing table — {exc.reason}") from exc
    except TimeoutError as exc:
        raise PricingFetchError("could not fetch pricing table — connection timed out") from exc
    except OSError as exc:
        raise PricingFetchError(f"could not fetch pricing table — {exc}") from exc

    try:
        content = body.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PricingFetchError(f"pricing table has invalid encoding — {exc}") from exc

    try:
        data = tomllib.loads(content)
    except tomllib.TOMLDecodeError as exc:
        raise PricingFetchError(f"pricing table has invalid TOML — {exc}") from exc

    # Validate structure
    if not isinstance(data.get("models"), dict):
        raise PricingFetchError("pricing table missing [models] table")

    fetched: dict[str, tuple[float, float]]
    try:
        fetched = _parse_models_table(data)
    except ValueError as exc:
        raise PricingFetchError(str(exc)) from exc

    if len(fetched) < 3:
        raise PricingFetchError(
            f"pricing table has only {len(fetched)} models (expected ≥ 3); "
            "may be a truncated response"
        )

    # Validate optional multipliers
    models_raw = data["models"]
    if not isinstance(models_raw, dict):
        raise PricingFetchError("pricing.toml 'models' section is not a table")
    for model_name, entry in models_raw.items():
        if not isinstance(entry, dict):
            raise PricingFetchError(f"pricing.toml model entry {model_name!r} is not a table")
        for field in ("cache_read_multiplier", "cache_write_multiplier"):
            val = entry.get(field)
            if val is not None and (not isinstance(val, (int, float)) or float(val) <= 0):
                raise PricingFetchError(f"Model {model_name!r} has invalid {field}: {val!r}")

    # D-5: check hash before accepting the table.
    # Raise PricingHashChangedError if the table has changed and accept_changed is False.
    # The hash is persisted below only after the table is written successfully.
    hash_ok = _check_pricing_hash(body)
    if not hash_ok and not accept_changed:
        raise PricingHashChangedError(
            "Remote pricing table has changed since the last accepted update.\n"
            "Run 'halyard update-pricing --accept-changed' to accept the new table,\n"
            "or review the changes first."
        )

    # Count new vs updated relative to bundled table
    new_count = sum(1 for m in fetched if m not in PRICING)
    updated_count = sum(1 for m, rates in fetched.items() if m in PRICING and rates != PRICING[m])

    # Atomic write
    _LOCAL_PRICING_FILE.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=_LOCAL_PRICING_FILE.parent, suffix=".toml.tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(content)
        os.replace(tmp_path, _LOCAL_PRICING_FILE)
    except OSError:
        with suppress(OSError):
            os.unlink(tmp_path)
        raise

    # D-5: persist the new hash now that the table has been accepted and written.
    new_hash = hashlib.sha256(body).hexdigest()
    hash_path = _pricing_hash_path()
    hash_path.parent.mkdir(parents=True, exist_ok=True)
    hash_path.write_text(new_hash + "\n")

    # Invalidate process cache
    global _merged_table
    _merged_table = None

    return new_count, updated_count


def calculate_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_read: int = 0,
    cache_write: int = 0,
) -> float:
    """Return cost in USD. Returns 0.0 for unknown models."""
    table = load_pricing_table()
    if model not in table:
        return 0.0
    input_rate, output_rate = table[model]

    # Per-model multipliers: check local file first, fall back to globals
    local_raw = _load_local_toml_raw()
    models_section = local_raw.get("models") if local_raw else None
    if local_raw and isinstance(models_section, dict) and model in models_section:
        read_mult, write_mult = _get_multipliers(local_raw, model)
    else:
        read_mult, write_mult = _CACHE_READ_MULTIPLIER, _CACHE_WRITE_MULTIPLIER

    cost = (input_tokens * input_rate + output_tokens * output_rate) / 1_000_000
    if cache_read:
        cost += (cache_read * input_rate * read_mult) / 1_000_000
    if cache_write:
        cost += (cache_write * input_rate * write_mult) / 1_000_000
    return round(cost, 4)


def model_is_known(model: str) -> bool:
    return model in load_pricing_table()
