# locale-guard — check JSON i18n files before they break your app

A Claude Code skill plus a small Python script that checks JSON locale files (`en.json`,
`fr.json`, `locales/*/translation.json` …) against your base locale.

AI translation and quick manual edits break locale files in the same few ways. locale-guard finds them:

- JSON that no longer parses, and **duplicate keys** (most parsers silently keep the last one)
- keys **missing** from a language, keys that exist only in a translation, and type changes
- **renamed or dropped placeholders**: `{name}` → `{nom}`, `{{max}}` → `{{mix}}`, a lost `%s`,
  an extra `}`

```
$ python3 locale_guard.py check locales/en.json locales/es-ES.json
== locales/es-ES.json: 1 error(s), 0 warning(s)
  [error] chat.errors.promptTooLong: placeholder missing: {{max}}
  [error] chat.errors.promptTooLong: placeholder not in base: {{mix}}
```

(That one is real: we found it in the Spanish file of a well-known open-source app.)

- Python 3.8+, **standard library only** — no Node, no pip install
- Works **offline** on local files; nothing is sent anywhere
- Handles nested and flat JSON, i18next `{{x}}`, ICU `{x}`, printf `%s` / `%1$s` / `%(x)s`

## Install

**As a Claude Code plugin**

```
/plugin marketplace add dailypicks-tools/locale-guard
/plugin install locale-guard@daily-picks-skills
```

Then ask Claude, for example: *"Check our locale files for broken placeholders."*

**As a plain skill** — copy `locale-guard/skills/locale-guard` into `~/.claude/skills/`
(or your project's `.claude/skills/`).

**Without Claude** — the script works on its own:

```
python3 locale-guard/skills/locale-guard/scripts/locale_guard.py check BASE.json TARGET.json [...]
```

Options: `--errors-only`, `--allow-missing` (for projects that fall back to the base language
on purpose), `--flag-untranslated`. Exit code 1 when errors are found, so it fits in CI.

## Full edition

The [full edition](https://dailypicksjp.gumroad.com/l/locale-guard) (one-time purchase) adds:

- **ICU plural/select checks** — a plural flattened to plain text, a missing `other` branch,
  select branches that differ. Languages without plural forms (Japanese, Chinese, Korean…) are
  handled correctly.
- **Tag checks** — `<b>`, `<0>`, `<a>`, `<link>` dropped or mismatched, including tags repeated
  inside plural branches
- **`--json` output** for CI and scripts
- **The translation workflow** — `extract` only the strings that need translating, in chunks,
  let Claude translate them, then `merge` only the translations that pass every check. Rejected
  ones go to a separate file with the reason, so nothing broken reaches your locale file.

## Limits

JSON only (no YAML, .po, Android XML or iOS .strings yet). Checks structure, not translation quality.

## License

MIT — see [LICENSE](LICENSE). Made by Daily Picks.
