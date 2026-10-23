---
name: locale-guard
description: Check JSON i18n locale files (en.json, fr.json, messages/*.json, locales/*/translation.json) against the base locale before you ship them. Use after adding a language, after an AI or a translator updated a locale file, or when keys may be out of sync. A bundled Python script reports invalid JSON, duplicate keys, missing or extra keys, empty translations, and renamed or dropped placeholders ({name}, {{name}}, %s, %1$s).
---

# locale-guard (free edition)

Locale files break in predictable ways when a model or a person edits them: keys get renamed or
dropped, `{name}` becomes `{nom}`, `%s` disappears, a key is written twice, or the JSON no longer
parses. This skill checks the files; it does not rewrite them.

The script is `scripts/locale_guard.py` (Python 3.8+, standard library only, works offline).
Run it with `python3 <skill-dir>/scripts/locale_guard.py ...`.

## Workflow

1. **Find the files.** Identify the base locale (usually `en`) and the target locale files. Ask the
   user if more than one base candidate exists. Skip JSON files in the same folder that are not
   locales. Do not edit any file.
2. **Check.**
   `python3 scripts/locale_guard.py check BASE.json TARGET.json [MORE.json ...]`
   Exit code 1 means errors were found. Add `--errors-only` to hide warnings.
   If the project leaves untranslated keys out on purpose and falls back to the base language,
   add `--allow-missing` so missing keys are warnings instead of errors.
   Add `--flag-untranslated` to warn about values identical to the base.
3. **Report.** Show the user a short summary: counts per file and a few examples of each kind of
   problem, not the whole list.
4. **Fix only what the user asks for**, one key at a time, then run `check` again.

## What is checked

- JSON that cannot be read, and duplicate keys (most parsers silently keep the last one)
- keys missing from a target, keys only in a target ("orphan", a warning), and type changes
- empty translations (warning)
- placeholders: `{name}`, `{{name}}`, ICU arguments such as `{count, plural, ...}` (the argument
  name only), `%s` `%d` `%1$s` `%(name)s`, and unbalanced braces

## Full edition

The full edition (https://dailypicksjp.gumroad.com/l/locale-guard) adds:
- ICU plural/select checks (a plural flattened to text, a missing `other` branch, select branches
  that differ), with languages without plural forms such as Japanese handled correctly
- HTML/JSX tag checks (`<b>`, `<0>`, `<link>`)
- `--json` output for CI
- the translation workflow: `extract` only the strings that need translating (in chunks), and
  `merge` only translations that pass every check, with rejected ones written to a separate file
