"""Shared JSON projection for `--json` output (v2.69).

One serialisation convention so every `--json` branch produces a
predictable, additive-only shape: dataclass → object (private `_`
fields skipped), datetime/date → ISO 8601, Path → str, Decimal →
float, set/tuple → array.
"""

from __future__ import annotations

import dataclasses
import json
import sys
from datetime import date, datetime
from decimal import Decimal
from typing import Any


def to_jsonable(obj: Any) -> Any:
    if obj is None or isinstance(obj, (bool, int, str, float)):
        return obj
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {
            f.name: to_jsonable(getattr(obj, f.name))
            for f in dataclasses.fields(obj)
            if not f.name.startswith("_")
        }
    if isinstance(obj, dict):
        return {str(k): to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set, frozenset)):
        return [to_jsonable(v) for v in obj]
    # pathlib.Path and any other path-like / opaque value
    return str(obj)


def dump_json(obj: Any) -> str:
    return json.dumps(to_jsonable(obj), indent=2) + "\n"


def emit(obj: Any) -> None:
    """Write the JSON projection to stdout (the only thing `--json` prints)."""
    sys.stdout.write(dump_json(obj))
