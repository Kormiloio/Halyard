# Spec: Claude Code Client Surface Detection

## Scenario: Detecting Desktop app on macOS
GIVEN an environment where `__CFBundleIdentifier` is `com.anthropic.Claude`
WHEN `detect_surface()` is called
THEN it MUST return `"desktop"`

## Scenario: Detecting VS Code terminal
GIVEN an environment where `TERM_PROGRAM` is `vscode`
WHEN `detect_surface()` is called
THEN it MUST return `"ide"`

## Scenario: Detecting Terminal CLI
GIVEN an environment where `TERM_PROGRAM` is `iTerm.app`
AND the parent process chain does NOT contain `Claude.app`
WHEN `detect_surface()` is called
THEN it MUST return `"cli"`

## Scenario: Fallback to TTY check
GIVEN an environment with no identifying variables
AND `stdin` is a TTY
WHEN `detect_surface()` is called
THEN it MUST return `"cli"`

## Scenario: Unidentifiable surface
GIVEN an environment with no identifying variables
AND `stdin` is NOT a TTY
WHEN `detect_surface()` is called
THEN it MUST return `"unknown"`
