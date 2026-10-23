#!/usr/bin/env python3
"""locale_guard (free edition) - check JSON locale (i18n) files against a base locale.

Standard library only. Works on local files; nothing is sent anywhere. MIT License.

  check BASE TARGET [TARGET ...]   report problems in TARGET files against BASE

Finds: unreadable JSON, duplicate keys, missing / orphan keys, type changes, empty translations,
and renamed or dropped placeholders ({name}, {{name}}, %s, %1$s, %(name)s).

The full edition adds ICU plural/select and HTML/JSX tag checks, machine-readable --json output,
and the extract -> translate -> merge workflow that only merges translations that pass:
https://dailypicksjp.gumroad.com/l/locale-guard

Exit codes: 0 = no errors, 1 = errors found, 2 = usage / unreadable input.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, OrderedDict
from pathlib import Path

__version__ = "0.1.1-free"

SEP = "."


class DuplicateKeyError(ValueError):
    pass


# ---------------------------------------------------------------- loading


def _no_dupes(pairs):
    seen = OrderedDict()
    for k, v in pairs:
        if k in seen:
            raise DuplicateKeyError(f"duplicate key {k!r}")
        seen[k] = v
    return seen


def load_json(path: Path):
    """Load a JSON file, refusing duplicate keys (json.load silently keeps the last one)."""
    text = path.read_text(encoding="utf-8-sig")
    return json.loads(text, object_pairs_hook=_no_dupes)


def flatten(obj, prefix="", sep=SEP, out=None):
    """Flatten nested dicts to {"a.b.c": value}. Lists are kept as leaf values."""
    if out is None:
        out = OrderedDict()
    if isinstance(obj, dict):
        if not obj and prefix:
            out[prefix] = obj
        for k, v in obj.items():
            key = f"{prefix}{sep}{k}" if prefix else str(k)
            flatten(v, key, sep, out)
    else:
        out[prefix] = obj
    return out


# ---------------------------------------------------------------- placeholders

ICU_TYPES = {"plural", "select", "selectordinal", "number", "date", "time", "spellout", "ordinal", "duration"}
PRINTF_RE = re.compile(r"%(?:(\d+)\$)?(?:\(([A-Za-z_][\w]*)\))?[-+0#]*\d*(?:\.\d+)?(l{0,2}[sdifuxX@])")
TAG_RE = re.compile(r"<\s*(/?)\s*([A-Za-z0-9][\w-]*)[^<>]*?(/?)\s*>")
IDENT_RE = re.compile(r"\s*([A-Za-z0-9_][\w.\-]*)\s*$")


def _match_brace(s: str, i: int) -> int:
    """Index of the '}' matching the '{' at s[i], or -1."""
    depth = 0
    for j in range(i, len(s)):
        c = s[j]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return j
    return -1


def _parse_branches(body: str):
    """Parse 'one {..} other {..}' into [(key, text), ...]."""
    branches = []
    i = 0
    n = len(body)
    while i < n:
        while i < n and body[i].isspace():
            i += 1
        if i >= n:
            break
        m = re.match(r"(=?[\w-]+|offset:\s*\d+)\s*", body[i:])
        if not m:
            return None
        key = m.group(1)
        i += m.end()
        if key.startswith("offset:"):
            continue
        if i >= n or body[i] != "{":
            return None
        j = _match_brace(body, i)
        if j < 0:
            return None
        branches.append((key, body[i + 1 : j]))
        i = j + 1
    return branches


def analyze(text: str):
    """Return a signature of the placeholders in one string.

    {"tokens": Counter, "plural": {arg: set(branch keys)}, "select": {arg: set(keys)},
     "tags": Counter, "errors": [str]}
    Recognises {name}, {{name}} (i18next/Handlebars), ICU arguments with nested plural/select
    branches, printf (%s, %1$s, %(name)s, %@) and HTML/JSX-style tags (<b>, </b>, <0/>).
    """
    sig = {"tokens": Counter(), "plural": {}, "select": {}, "tags": Counter(), "errors": []}
    if not isinstance(text, str):
        return sig
    _walk(text, sig)
    stripped = re.sub(r"%%", "", text)
    for m in PRINTF_RE.finditer(stripped):
        pos, name, conv = m.groups()
        if name:
            sig["tokens"][f"%({name})"] += 1
        elif pos:
            sig["tokens"][f"%{pos}$"] += 1
        else:
            sig["tokens"][f"%{conv}"] += 1
    for m in TAG_RE.finditer(text):
        closing, name, selfclose = m.groups()
        sig["tags"][("</" if closing else "<") + name + ("/>" if selfclose else ">")] += 1
    return sig


def _walk(s: str, sig):
    i = 0
    n = len(s)
    while i < n:
        c = s[i]
        if c == "'" and i + 1 < n and s[i + 1] in "{}":
            # ICU quoting: '{' ... ' is literal text
            end = s.find("'", i + 1)
            i = n if end < 0 else end + 1
            continue
        if c == "{":
            if s.startswith("{{", i):
                end = s.find("}}", i + 2)
                if end < 0:
                    sig["errors"].append("unclosed '{{'")
                    return
                inner = s[i + 2 : end].strip()
                name = re.split(r"[\s,|]", inner, maxsplit=1)[0] if inner else ""
                sig["tokens"]["{{" + name + "}}"] += 1
                i = end + 2
                continue
            j = _match_brace(s, i)
            if j < 0:
                sig["errors"].append("unbalanced '{'")
                return
            inner = s[i + 1 : j]
            parts = inner.split(",", 2)
            arg = parts[0].strip()
            if len(parts) >= 2 and parts[1].strip() in ICU_TYPES and IDENT_RE.match(parts[0]):
                kind = parts[1].strip()
                sig["tokens"]["{" + arg + "}"] += 1
                if kind in ("plural", "select", "selectordinal") and len(parts) == 3:
                    branches = _parse_branches(parts[2])
                    if branches is None:
                        sig["errors"].append(f"cannot parse {kind} branches of {{{arg}}}")
                    else:
                        bucket = "select" if kind == "select" else "plural"
                        sig[bucket][arg] = {k for k, _ in branches}
                        for _, btxt in branches:
                            sub = {"tokens": Counter(), "plural": sig["plural"], "select": sig["select"],
                                   "tags": Counter(), "errors": sig["errors"]}
                            _walk(btxt, sub)
                            # placeholders inside branches count once (union), not per branch
                            for t in sub["tokens"]:
                                if t not in sig["tokens"]:
                                    sig["tokens"][t] = 1
            elif IDENT_RE.match(inner):
                sig["tokens"]["{" + inner.strip() + "}"] += 1
            else:
                # free text inside braces (rare); look inside for nested placeholders
                _walk(inner, sig)
            i = j + 1
            continue
        if c == "}":
            sig["errors"].append("unbalanced '}'")
            i += 1
            continue
        i += 1


# CLDR languages whose only cardinal plural category is "other"
NO_PLURAL_LANGS = {"ja", "zh", "ko", "th", "vi", "id", "ms", "lo", "my", "km", "yue", "bo", "dz", "ig", "ii",
                   "jv", "kea", "ses", "sg", "to", "wo", "yo", "nqo", "sah", "su", "tok"}


def lang_of(path) -> str:
    """Guess the language code from a file name such as ja.json, zh-TW.json, pt_BR.json."""
    return re.split(r"[-_.]", Path(path).stem, maxsplit=1)[0].lower()


def compare(base_text, target_text, lang=None):
    """Return a list of (severity, message) comparing a translated string to its base.

    lang: target language code (e.g. "ja"); used to accept plurals simplified to a plain
    placeholder in languages without plural forms.
    """
    issues = []
    b = analyze(base_text)
    t = analyze(target_text)
    for e in t["errors"]:
        issues.append(("error", f"syntax: {e}"))
    if b["tokens"] != t["tokens"]:
        missing = b["tokens"] - t["tokens"]
        extra = t["tokens"] - b["tokens"]
        if missing:
            issues.append(("error", "placeholder missing: " + ", ".join(sorted(missing.elements()))))
        if extra:
            issues.append(("error", "placeholder not in base: " + ", ".join(sorted(extra.elements()))))
    return issues


# ---------------------------------------------------------------- check


def check_pair(base_flat, target_flat, *, flag_same=False, min_same_len=4, allow_missing=False, lang=None):
    """Compare two flattened locales. Returns list of dicts {severity, key, message}."""
    out = []
    for key, bval in base_flat.items():
        if key not in target_flat:
            out.append({"severity": "warning" if allow_missing else "error", "key": key, "message": "missing key"})
            continue
        tval = target_flat[key]
        if type(bval) is not type(tval):
            out.append({"severity": "error", "key": key,
                        "message": f"type differs: base {type(bval).__name__}, target {type(tval).__name__}"})
            continue
        if isinstance(bval, str):
            if bval.strip() and not tval.strip():
                out.append({"severity": "warning", "key": key, "message": "empty translation"})
                continue
            for sev, msg in compare(bval, tval, lang):
                out.append({"severity": sev, "key": key, "message": msg})
            if flag_same and tval == bval and len(bval) >= min_same_len and re.search(r"[A-Za-z]{3}", bval):
                out.append({"severity": "warning", "key": key, "message": "identical to base (untranslated?)"})
    for key in target_flat:
        if key not in base_flat:
            out.append({"severity": "warning", "key": key, "message": "key not in base (orphan)"})
    return out


def cmd_check(args) -> int:
    base_path = Path(args.base)
    try:
        base = load_json(base_path)
    except (OSError, ValueError) as e:
        print(f"{base_path}: cannot read base: {e}", file=sys.stderr)
        return 2
    base_flat = flatten(base)
    for k, v in base_flat.items():
        for e in analyze(v)["errors"] if isinstance(v, str) else []:
            print(f"{base_path}: {k}: base itself has a syntax problem: {e}", file=sys.stderr)
    report = {"base": str(base_path), "files": []}
    total_err = 0
    for tp in args.targets:
        tpath = Path(tp)
        entry = {"file": str(tpath), "issues": []}
        try:
            target = load_json(tpath)
        except (OSError, ValueError) as e:
            entry["issues"].append({"severity": "error", "key": "", "message": f"cannot read: {e}"})
        else:
            entry["issues"] = check_pair(base_flat, flatten(target), flag_same=args.flag_untranslated,
                                         allow_missing=args.allow_missing, lang=lang_of(tpath))
        n_err = sum(1 for i in entry["issues"] if i["severity"] == "error")
        n_warn = sum(1 for i in entry["issues"] if i["severity"] == "warning")
        entry["errors"], entry["warnings"] = n_err, n_warn
        total_err += n_err
        report["files"].append(entry)
    for f in report["files"]:
        print(f"== {f['file']}: {f['errors']} error(s), {f['warnings']} warning(s)")
        for i in f["issues"]:
            if i["severity"] == "warning" and args.errors_only:
                continue
            print(f"  [{i['severity']}] {i['key']}: {i['message']}")
    return 1 if total_err else 0


# ---------------------------------------------------------------- cli


def build_parser():
    p = argparse.ArgumentParser(prog="locale_guard", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("check", help="report missing/orphan keys and broken placeholders")
    c.add_argument("base")
    c.add_argument("targets", nargs="+")
    c.add_argument("--errors-only", action="store_true")
    c.add_argument("--flag-untranslated", action="store_true", help="warn when a value equals the base")
    c.add_argument("--allow-missing", action="store_true",
                   help="report missing keys as warnings (for projects that fall back to the base language)")
    c.set_defaults(func=cmd_check)

    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
