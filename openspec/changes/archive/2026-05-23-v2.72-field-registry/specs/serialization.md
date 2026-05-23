# Spec: Declarative Field Registry Serialization

## Scenario: Round-trip consistency for optional fields
GIVEN an `AiSession` object with populated optional fields
WHEN `to_log_line()` is called
THEN the resulting string MUST contain `key=value` tokens for all populated fields
AND WHEN that string is passed to `from_log_line()`
THEN the resulting `AiSession` MUST be equal to the original object

## Scenario: Byte-identical output for existing fields
GIVEN a set of field values that were serialized by the manual v2.71 implementation
WHEN those same values are serialized by the v2.72 registry-based implementation
THEN the resulting `key=value` tokens MUST be byte-for-byte identical to the v2.71 output

## Scenario: Forward-compatibility (passthrough)
GIVEN a log line containing an unrecognized `unknown_key=some%20value` token
WHEN the line is parsed
THEN the unknown token MUST be preserved in the `extra` dictionary
AND WHEN the session is re-serialized
THEN the `unknown_key=some%20value` token MUST be present in the output

## Scenario: Legacy tag promotion
GIVEN a log line with a `tags=branch:feature-x,other-tag` token and no `branch=` field
WHEN the line is parsed
THEN the `branch` attribute MUST be set to `feature-x`
AND the `tags` list MUST contain `branch:feature-x` and `other-tag`

## Scenario: Suppression of default values
GIVEN an `AiSession` with `billing="api"`
WHEN serialized
THEN the `billing=api` token MUST NOT be present in the output
