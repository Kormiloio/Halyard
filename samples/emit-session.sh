#!/usr/bin/env sh
set -eu

# Minimal polyglot emitter for Halyard Hub.
# Values used in the raw log line must be single-token values: no spaces or "=".

HUB_URL="${HALYARD_HUB_URL:-http://127.0.0.1:4318}"
START="${START:-$(date +"%Y-%m-%dT%H:%M:%S")}"
END="${END:-$START}"
TOOL="${TOOL:-custom-tool}"
MODEL="${MODEL:-custom-model}"
INPUT_TOKENS="${INPUT_TOKENS:-0}"
OUTPUT_TOKENS="${OUTPUT_TOKENS:-0}"
COST_USD="${COST_USD:-0.0000}"
PROJECT="${PROJECT:-}"

LINE="s $START $END $TOOL $MODEL $INPUT_TOKENS $OUTPUT_TOKENS $COST_USD"
if [ -n "$PROJECT" ]; then
  LINE="$LINE project=$PROJECT"
fi

curl -sS \
  -X POST "$HUB_URL/v1/ingest" \
  -H "Content-Type: application/json" \
  -d "{\"line\":\"$LINE\"}"
