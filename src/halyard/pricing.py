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
import urllib.parse
import urllib.request
from contextlib import suppress
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
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

# A multiplier outside (0, _MAX_MULTIPLIER] is treated as malformed: a runaway
# value would silently inflate every cached-token cost.
_MAX_MULTIPLIER = 10.0

_LOCAL_PRICING_FILE = Path.home() / ".halyard" / "pricing.toml"
_REMOTE_HOST = "raw.githubusercontent.com"
_REMOTE_URL = f"https://{_REMOTE_HOST}/Kormiloio/Halyard/main/pricing/models.toml"

# Cached merged rate table and per-model multiplier table; computed once per
# process from a single local-file read. Both are invalidated together via
# invalidate_pricing_cache() when the user runs `halyard update-pricing` so a
# run can never mix old rates with new multipliers. Short-lived CLI processes
# never need mid-run invalidation.
_merged_table: dict[str, tuple[float, float]] | None = None
_multipliers_table: dict[str, tuple[float, float]] | None = None


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


def invalidate_pricing_cache() -> None:
    """Drop the cached rate and multiplier tables together."""
    global _merged_table, _multipliers_table
    _merged_table = None
    _multipliers_table = None


def load_pricing_table() -> dict[str, tuple[float, float]]:
    """Return merged table: local overrides bundled. Cached per process."""
    _ensure_tables()
    assert _merged_table is not None
    return _merged_table


def _ensure_tables() -> None:
    """Populate the rate and multiplier caches from one local-file read.

    Resetting _merged_table to None (the test hook) forces both to rebuild,
    so the two caches can never diverge.
    """
    global _merged_table, _multipliers_table
    if _merged_table is not None and _multipliers_table is not None:
        return
    raw = _load_local_raw()
    merged: dict[str, tuple[float, float]] = dict(PRICING)
    merged.update(_parse_local_rates(raw))
    _merged_table = merged
    _multipliers_table = _parse_local_multipliers(raw)


def _load_local_raw() -> dict[str, object] | None:
    """Read and parse the local pricing TOML. Warn (never raise) on failure."""
    if not _LOCAL_PRICING_FILE.exists():
        return None
    try:
        result: dict[str, object] = tomllib.loads(_LOCAL_PRICING_FILE.read_text())
        return result
    except (tomllib.TOMLDecodeError, ValueError, OSError) as e:
        print(
            f"[halyard] Warning: {_LOCAL_PRICING_FILE} is invalid — "
            f"custom pricing ignored, using bundled prices. ({e})",
            file=sys.stderr,
        )
        return None


def _parse_local_rates(raw: dict[str, object] | None) -> dict[str, tuple[float, float]]:
    if raw is None:
        return {}
    try:
        return _parse_models_table(raw)
    except ValueError as e:
        print(
            f"[halyard] Warning: {_LOCAL_PRICING_FILE} is invalid — "
            f"custom pricing ignored, using bundled prices. ({e})",
            file=sys.stderr,
        )
        return {}


def _parse_local_multipliers(
    raw: dict[str, object] | None,
) -> dict[str, tuple[float, float]]:
    """Return {model: (read_mult, write_mult)} for models that override them.

    A multiplier outside (0, _MAX_MULTIPLIER] is rejected and the model falls
    back to the global default for that side, with a stderr warning.
    """
    if raw is None:
        return {}
    models = raw.get("models")
    if not isinstance(models, dict):
        return {}
    out: dict[str, tuple[float, float]] = {}
    for name, entry in models.items():
        if not isinstance(entry, dict):
            continue
        read_m = _coerce_multiplier(
            entry.get("cache_read_multiplier"), _CACHE_READ_MULTIPLIER, name
        )
        write_m = _coerce_multiplier(
            entry.get("cache_write_multiplier"), _CACHE_WRITE_MULTIPLIER, name
        )
        out[name] = (read_m, write_m)
    return out


def _coerce_multiplier(val: object, default: float, model: str) -> float:
    if val is None:
        return default
    if not isinstance(val, (int, float)) or not (0 < float(val) <= _MAX_MULTIPLIER):
        print(
            f"[halyard] Warning: {_LOCAL_PRICING_FILE} model {model!r} has invalid "
            f"multiplier {val!r} — using default {default}.",
            file=sys.stderr,
        )
        return default
    return float(val)


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
            final_url = resp.geturl()
            body = resp.read()
    except urllib.error.URLError as exc:
        raise PricingFetchError(f"could not fetch pricing table — {exc.reason}") from exc
    except TimeoutError as exc:
        raise PricingFetchError("could not fetch pricing table — connection timed out") from exc
    except OSError as exc:
        raise PricingFetchError(f"could not fetch pricing table — {exc}") from exc

    parsed = urllib.parse.urlparse(final_url)
    if parsed.scheme != "https" or parsed.hostname != _REMOTE_HOST:
        raise PricingFetchError(
            f"pricing table served from unexpected origin: {final_url!r} "
            f"(expected https://{_REMOTE_HOST})"
        )

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
            if val is not None and (
                not isinstance(val, (int, float)) or not (0 < float(val) <= _MAX_MULTIPLIER)
            ):
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

    # Invalidate process cache (rates + multipliers together)
    invalidate_pricing_cache()

    return new_count, updated_count


def calculate_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_read: int = 0,
    cache_write: int = 0,
) -> float:
    """Return cost in USD. Returns 0.0 for unknown models."""
    _ensure_tables()
    assert _merged_table is not None and _multipliers_table is not None
    if model not in _merged_table:
        return 0.0
    input_rate, output_rate = _merged_table[model]
    read_mult, write_mult = _multipliers_table.get(
        model, (_CACHE_READ_MULTIPLIER, _CACHE_WRITE_MULTIPLIER)
    )

    # Decimal arithmetic so cost is deterministic and does not accumulate
    # binary-float error when summed across thousands of sessions.
    million = Decimal(1_000_000)
    in_rate = Decimal(str(input_rate))
    out_rate = Decimal(str(output_rate))
    cost = (Decimal(input_tokens) * in_rate + Decimal(output_tokens) * out_rate) / million
    if cache_read:
        cost += Decimal(cache_read) * in_rate * Decimal(str(read_mult)) / million
    if cache_write:
        cost += Decimal(cache_write) * in_rate * Decimal(str(write_mult)) / million
    return float(cost.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP))


def model_is_known(model: str) -> bool:
    return model in load_pricing_table()
