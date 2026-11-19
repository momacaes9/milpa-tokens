"""build-outputs writes every deck file, deterministically, and docs quote it correctly."""

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
from milpa.outputs import build, num, usd, write_csv

CFG = load()
ROOT = DEFAULT_CONFIG.parents[1]
TABLES = (
    "lock_in_table.md", "lock_in_table.csv", "token_table.md", "simulation_summary.md",
    "simulation_summary.csv", "simulation_monthly.csv", "stress_normal_then_storm.md",
    "stress_normal_then_storm_monthly.csv", "monte_carlo.md", "monte_carlo.csv",
    "sensitivity.md", "sensitivity.csv", "key_results.md", "key_results.csv",
)


class TestFormatting(unittest.TestCase):
    def test_usd_rounds_half_up_like_the_case(self):
        self.assertEqual(usd(148.5), "$149")
        self.assertEqual(usd(1221.5), "$1,222")
        self.assertEqual(usd(761.5), "$762")
        self.assertEqual(usd(243.6), "$244")
        self.assertEqual(usd(-62.4), "-$62")
        self.assertEqual(usd(float("nan")), "n/a")

    def test_num(self):
        self.assertEqual(num(17.82, 1), "17.8")
        self.assertEqual(num(float("inf")), "fully backed")
        self.assertEqual(num(float("nan")), "n/a")

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
        cls.written = build(CFG, cls.out, charts=False, mc_runs=50)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_all_tables_written(self):
        names = {p.name for p in self.written}
        for name in TABLES:
            self.assertIn(name, names)
            self.assertGreater((self.out / name).stat().st_size, 50)

    def test_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp:
            build(CFG, Path(tmp), charts=False, mc_runs=50)
            for name in TABLES:
                self.assertEqual((self.out / name).read_text(), (Path(tmp) / name).read_text(), name)

    def test_csv_parses(self):
        for name in TABLES:
            if name.endswith(".csv"):
                rows = list(csv.DictReader((self.out / name).open()))
                self.assertTrue(rows, name)

    def test_summary_quotes_case_numbers(self):
        md = (self.out / "simulation_summary.md").read_text()
        for figure in ("$1,370", "$594", "$1,222", "$762", "$900", "$491", "$704", "$244"):
            self.assertIn(figure, md)


class TestCommittedOutputsAreCurrent(unittest.TestCase):
    """The Markdown/CSV committed in outputs/ must equal a fresh build."""

    def test_committed_tables_match_fresh_build(self):
        committed = ROOT / "outputs"
        if not (committed / "key_results.md").exists():
            self.skipTest("outputs/ not built yet")
        with tempfile.TemporaryDirectory() as tmp:
            build(CFG, Path(tmp), charts=False)
            for name in TABLES:
                self.assertEqual((committed / name).read_text(), (Path(tmp) / name).read_text(),
                                 f"outputs/{name} is stale: run `milpa build-outputs`")


class TestReadmeNumbers(unittest.TestCase):
    """Every number the README quotes from key_results.md must appear there verbatim."""

    def test_readme_matches_key_results(self):
        readme = (ROOT / "README.md").read_text()
        key = (ROOT / "outputs" / "key_results.md")
        if not key.exists() or "<!-- key-results -->" not in readme:
            self.skipTest("README has no generated key-results block yet")
        block = re.search(r"<!-- key-results -->\n(.*?)\n<!-- /key-results -->", readme, re.S).group(1)
        body = key.read_text().split("\n", 2)[2].strip()
        self.assertEqual(block.strip(), body)


class TestCli(unittest.TestCase):
    def run_cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(list(args))
        return code, out.getvalue(), err.getvalue()

    def test_lockin(self):
        code, out, _ = self.run_cli("lockin")
        self.assertEqual(code, 0)
        self.assertIn("+20%", out)
        code, out, _ = self.run_cli("lockin", "--wage-bzd", "6", "--in-kind-lb", "9")
        self.assertIn("-10%", out)

    def test_simulate_both(self):
        code, out, _ = self.run_cli("simulate")
        self.assertEqual(code, 0)
        self.assertIn("Bad-weather year", out)
        self.assertIn("$1,222", out)

    def test_simulate_one_year_with_overrides_and_mc(self):
        code, out, _ = self.run_cli("simulate", "--year", "bad", "--drums", "3", "--wage-bzd", "6",
                                    "--in-kind-lb", "12", "--monte-carlo", "20", "--seed", "5")
        self.assertEqual(code, 0)
        self.assertIn("### bad year", out)
        self.assertIn("Monte Carlo: 20 runs, fixed seed 5", out)

    def test_simulate_error(self):
        code, _, err = self.run_cli("simulate", "--drums", "1")
        self.assertEqual(code, 1)
        self.assertIn("sale drum", err)

    def test_sensitivity(self):
        code, out, _ = self.run_cli("sensitivity")
        self.assertEqual(code, 0)
        self.assertIn("**(base)**", out)

    def test_build_outputs_no_charts(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, out, _ = self.run_cli("build-outputs", "--out", tmp, "--no-charts", "--mc-runs", "10")
            self.assertEqual(code, 0)
            self.assertIn("key_results.md", out)


class TestCharts(unittest.TestCase):
    def test_charts_render_when_matplotlib_present(self):
        try:
            import matplotlib  # noqa: F401
        except ImportError:
            self.skipTest("matplotlib not installed (optional)")
        with tempfile.TemporaryDirectory() as tmp:
            written = build(CFG, Path(tmp), charts=True, mc_runs=10)
            pngs = [p for p in written if p.suffix == ".png"]
            self.assertEqual(len(pngs), 5)
            for p in pngs:
                self.assertEqual(p.read_bytes()[:4], b"\x89PNG")


if __name__ == "__main__":
    unittest.main()
