"""build-outputs writes every deck file, deterministically, and the docs quote it correctly."""

from __future__ import annotations

import csv
import io
import re
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from milpa.cli import main
from milpa.config import DEFAULT_CONFIG, load
from milpa.outputs import build, num, pct, usd, write_csv

CFG = load()
ROOT = DEFAULT_CONFIG.parents[1]
TABLES = (
    "annual_model.md", "annual_model.csv", "lock_in_table.md", "lock_in_table.csv",
    "token_table.md", "token_table.csv", "monthly_replay.md", "monthly_replay.csv",
    "key_results.md", "key_results.csv",
)
LABOR_WORDS = re.compile(r"\b(wage|wages|hour|hours|labor|labour|work-hour|hauling|storm-recovery)\b", re.I)


class TestFormatting(unittest.TestCase):
    def test_usd_rounds_half_up_like_the_case(self):
        self.assertEqual(usd(148.5), "$149")
        self.assertEqual(usd(122.85), "$123")
        self.assertEqual(usd(79.08), "$79")
        self.assertEqual(usd(-62.4), "-$62")
        self.assertEqual(usd(float("nan")), "n/a")

    def test_num_and_pct(self):
        self.assertEqual(num(73.365), "73")
        self.assertEqual(num(float("inf")), "inf")
        self.assertEqual(num(float("nan")), "n/a")
        self.assertEqual(pct(0.05355, 1), "5.4%")

    def test_empty_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "x.csv"
            write_csv(path, [])
            self.assertEqual(path.read_text(), "")


class TestBuild(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.out = Path(cls.tmp.name)
        cls.written = build(CFG, cls.out, charts=False)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_all_tables_written_no_html(self):
        names = {p.name for p in self.written}
        self.assertEqual(names, set(TABLES))
        self.assertFalse(any(p.suffix == ".html" for p in self.written))

    def test_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp:
            build(CFG, Path(tmp), charts=False)
            for name in TABLES:
                self.assertEqual((self.out / name).read_text(), (Path(tmp) / name).read_text(), name)

    def test_csv_parses(self):
        for name in TABLES:
            if name.endswith(".csv"):
                with (self.out / name).open() as fh:
                    self.assertTrue(list(csv.DictReader(fh)), name)

    def test_key_results_quote_the_deck(self):
        md = (self.out / "key_results.md").read_text()
        for text in ("73 (13 on-time reward + 60 pickup)", "5.4% of $1,370", "cap 10% = 137 tokens",
                     "$594 x (25% - 10%) = $89", "| $79 |", "$135 ($240 - $60 cash - 60 x $1 x 75%)",
                     "70% x $176 turned away = $123", "3.33 lb = 1 token", "1.00 lb = 1 token"):
            self.assertIn(text, md)

    def test_no_labor_in_outputs(self):
        for name in TABLES:
            self.assertIsNone(LABOR_WORDS.search((self.out / name).read_text()), name)


class TestCommittedFiles(unittest.TestCase):
    def test_committed_tables_match_fresh_build(self):
        committed = ROOT / "outputs"
        with tempfile.TemporaryDirectory() as tmp:
            build(CFG, Path(tmp), charts=False)
            for name in TABLES:
                self.assertEqual((committed / name).read_text(), (Path(tmp) / name).read_text(),
                                 f"outputs/{name} is stale: run `milpa build-outputs`")

    def test_readme_key_results_block_matches(self):
        readme = (ROOT / "README.md").read_text()
        block = re.search(r"<!-- key-results -->\n(.*?)\n<!-- /key-results -->", readme, re.S).group(1)
        body = (ROOT / "outputs" / "key_results.md").read_text().split("\n", 2)[2].strip()
        self.assertEqual(block.strip(), body)

    def test_readme_lock_in_block_matches(self):
        readme = (ROOT / "README.md").read_text()
        block = re.search(r"<!-- lock-in -->\n(.*?)\n<!-- /lock-in -->", readme, re.S).group(1)
        body = (ROOT / "outputs" / "lock_in_table.md").read_text().split("\n", 2)[2].strip()
        self.assertEqual(block.strip(), body)

    def test_docs_have_no_labor_rules(self):
        for doc in ("README.md", "docs/DESIGN.md"):
            text = (ROOT / doc).read_text()
            for line in text.splitlines():
                if LABOR_WORDS.search(line):
                    self.assertIn("no labor", line.lower(), f"{doc}: {line}")


class TestCli(unittest.TestCase):
    def run_cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(list(args))
        return code, out.getvalue(), err.getvalue()

    def test_commands(self):
        for cmd, expect in (("check", "config OK"), ("token-table", "3.33 lb"),
                            ("lockin", "| As cash | $0.00 |"), ("model", "| $79 |"),
                            ("simulate", "| 73 |")):
            code, out, _ = self.run_cli(cmd)
            self.assertEqual(code, 0, cmd)
            self.assertIn(expect, out, cmd)

    def test_no_wage_option(self):
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            main(["lockin", "--wage-bzd", "5"])

    def test_errors(self):
        code, _, err = self.run_cli("simulate", "--years", "0")
        self.assertEqual(code, 1)
        self.assertIn("years", err)
        code, _, err = self.run_cli("--config", "/no/such.json", "check")
        self.assertEqual(code, 2)

    def test_build_outputs_no_charts(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, out, _ = self.run_cli("build-outputs", "--out", tmp, "--no-charts")
            self.assertEqual(code, 0)
            self.assertIn("key_results.md", out)


class TestCharts(unittest.TestCase):
    def test_charts_render_when_matplotlib_present(self):
        try:
            import matplotlib  # noqa: F401
        except ImportError:
            self.skipTest("matplotlib not installed (optional)")
        with tempfile.TemporaryDirectory() as tmp:
            pngs = [p for p in build(CFG, Path(tmp), charts=True) if p.suffix == ".png"]
            self.assertEqual(len(pngs), 3)
            for p in pngs:
                self.assertEqual(p.read_bytes()[:4], b"\x89PNG")


if __name__ == "__main__":
    unittest.main()
