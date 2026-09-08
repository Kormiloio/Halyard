# v5.44 — A moored card never said what it was moored against

## Why

The user asked why their most active project was labelled
`Shipshape · Moored`. The badge is `sessions / target`:

```python
pct = session_count / max(target, 1)
if pct >= 1.0:
    return "moored"
```

They had no `voyages.toml`, so every project silently used
`_DEFAULT_TARGET = 20`. Halyard was at 107 sessions — **535% of a target
nobody set** — and "Moored" reads as *finished* on the project they were
working on at that moment.

The target is already configurable: `halyard voyage set <slug>
--sessions <n>` has shipped for some time, writes
`~/.halyard/hub-data/voyages.toml`, and is read by the dashboard through
the same `find_project_dir() or find_hub()` chain. Nothing was broken.

What was missing is that **the card gave no way to work that out.**
Active cards already render their denominator:

```
git/Nautilus       Anchors Aweigh    2 / 20
kormilo:halyard    Anchors Aweigh  108 / 500
```

The moored branch renders creature, slug, stage and trait — and no count.
So the one state whose cause is least obvious is the only one that hides
the number that explains it.

## What

Moored cards show `N / target`, the same as active cards.

That is the whole change. It makes a badge produced by an unset default
self-explaining, and it points at the knob without needing a nudge, a
doctor check, or new copy.

## Not in scope

- The default of 20 stays. Changing it would move every existing user's
  badge to justify one user's surprise.
- No doctor check. The card explaining itself is the proportionate fix;
  a warning for a cosmetic label would be noise, and nothing downstream
  consumes the stage.
- The "past 100% carries no information" property is unchanged — a
  project at 21 sessions and one at 107 both read moored. Showing the
  count is what makes that visible rather than hiding it.
