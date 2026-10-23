"""Tests for locale_guard (free edition). Run: python3 -m unittest discover -s tests -v"""
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "skills" / "locale-guard" / "scripts"))
import locale_guard as lg  # noqa: E402

BASE = {
    "app": {"title": "My App", "greeting": "Hello, {name}!"},
    "cart": {"items": "{count, plural, one {# item for {name}} other {# items for {name}}}"},
    "legacy": {"files": "%d files in %s", "named": "%(user)s logged in", "pos": "%1$s of %2$s"},
    "i18next": {"welcome": "Welcome back, {{user}}"},
    "empty_ok": "",
    "list": ["a", "b"],
}


def run(argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = lg.main(argv)
    return code, out.getvalue(), err.getvalue()


class AnalyzeTests(unittest.TestCase):
    def tok(self, s):
        return dict(lg.analyze(s)["tokens"])

    def test_simple_and_double_braces(self):
        self.assertEqual(self.tok("Hi {name}"), {"{name}": 1})
        self.assertEqual(self.tok("Hi {{ user }}"), {"{{user}}": 1})

    def test_icu_arguments_are_placeholders(self):
        self.assertEqual(self.tok(BASE["cart"]["items"]), {"{count}": 1, "{name}": 1})

    def test_printf(self):
        self.assertEqual(self.tok("%d files in %s, 100%% done"), {"%d": 1, "%s": 1})
        self.assertEqual(self.tok("%1$s / %2$s"), {"%1$": 1, "%2$": 1})
        self.assertEqual(self.tok("%(user)s"), {"%(user)": 1})

    def test_percent_in_prose_is_not_placeholder(self):
        self.assertEqual(self.tok("100% sure"), {})

    def test_unbalanced(self):
        self.assertTrue(lg.analyze("Hi {name")["errors"])
        self.assertTrue(lg.analyze("Hi name}")["errors"])


class CompareTests(unittest.TestCase):
    def errs(self, b, t):
        return [m for s, m in lg.compare(b, t) if s == "error"]

    def test_ok_translation(self):
        self.assertEqual(self.errs("Hello, {name}!", "こんにちは、{name}さん！"), [])

    def test_translated_placeholder_name(self):
        e = self.errs("Hello, {name}!", "Bonjour, {nom} !")
        self.assertTrue(any("missing: {name}" in x for x in e))
        self.assertTrue(any("not in base: {nom}" in x for x in e))

    def test_printf_order_and_count(self):
        self.assertEqual(self.errs("%d files in %s", "%s 内の %d ファイル"), [])
        self.assertTrue(self.errs("%d files in %s", "%d fichiers"))

    def test_double_brace_renamed(self):
        self.assertTrue(self.errs("Order {{orderId}}", "Commande {{orderID}}"))


class CheckCommandTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)
        (self.d / "en.json").write_text(json.dumps(BASE), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, obj_or_text):
        p = self.d / name
        p.write_text(obj_or_text if isinstance(obj_or_text, str) else json.dumps(obj_or_text, ensure_ascii=False),
                     encoding="utf-8")
        return str(p)

    def test_clean_copy_passes(self):
        t = self.write("copy.json", BASE)
        code, out, _ = run(["check", str(self.d / "en.json"), t])
        self.assertEqual(code, 0, out)

    def test_reports_missing_orphan_and_placeholder(self):
        bad = json.loads(json.dumps(BASE))
        bad["app"] = {"title": "Mon appli", "greeting": "Bonjour, {nom} !", "old": "x"}
        t = self.write("fr.json", bad)
        code, out, _ = run(["check", str(self.d / "en.json"), t])
        self.assertEqual(code, 1)
        self.assertIn("app.greeting: placeholder missing", out)
        self.assertIn("app.old: key not in base (orphan)", out)

    def test_missing_key_and_allow_missing(self):
        t = self.write("de.json", {"app": {"title": "Meine App", "greeting": "Hallo, {name}!"}})
        code, out, _ = run(["check", str(self.d / "en.json"), t])
        self.assertEqual(code, 1)
        self.assertIn("legacy.files: missing key", out)
        code, out, _ = run(["check", str(self.d / "en.json"), t, "--allow-missing"])
        self.assertEqual(code, 0, out)

    def test_invalid_json_and_duplicates(self):
        bad = self.write("bad.json", '{"app": {"title": "x",}}')
        dup = self.write("dup.json", '{"app": {"title": "a", "title": "b"}}')
        code, out, _ = run(["check", str(self.d / "en.json"), bad, dup])
        self.assertEqual(code, 1)
        self.assertIn("cannot read", out)
        self.assertIn("duplicate key", out)

    def test_type_change(self):
        broken = json.loads(json.dumps(BASE))
        broken["app"] = "flattened by mistake"
        t = self.write("x.json", broken)
        code, out, _ = run(["check", str(self.d / "en.json"), t])
        self.assertEqual(code, 1)
        self.assertIn("app.title: missing key", out)

    def test_flag_untranslated(self):
        t = self.write("same.json", BASE)
        code, out, _ = run(["check", str(self.d / "en.json"), t, "--flag-untranslated"])
        self.assertEqual(code, 0)
        self.assertIn("identical to base", out)

    def test_full_edition_commands_are_absent(self):
        with self.assertRaises(SystemExit):
            run(["extract", str(self.d / "en.json"), str(self.d / "en.json"), "-o", "x.json"])


if __name__ == "__main__":
    unittest.main()
