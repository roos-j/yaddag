from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from yaddag.latex_to_label_numbers import (
    build_label_numbers_from_file,
    parse_aux_label_numbers,
)
from yaddag.latex_to_graph import build_graph


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"

EXPECTED_SHARED_SECTION = {
    "sec:first": "1",
    "thm:first": "1.1",
    "lem:first": "1.2",
    "def:first": "1.1",
    "subsec:first": "1.1",
    "thm:after-subsection": "1.3",
    "sec:second": "2",
    "lem:second": "2.1",
    "def:second": "2.1",
}

EXPECTED_GLOBAL_SUBSECTION = {
    "sec:one": "1",
    "prop:one": "1",
    "cor:one": "2",
    "subsec:one-one": "1.1",
    "claim:one-one": "1.1.1",
    "eq:one": "1.1",
    "subsec:one-two": "1.2",
    "claim:one-two": "1.2.1",
    "sec:two": "2",
    "prop:two": "3",
    "subsec:two-one": "2.1",
    "claim:two-one": "2.1.1",
    "eq:two": "2.1",
}


class LabelNumberingTests(unittest.TestCase):
    def test_shared_section_theorems(self) -> None:
        actual = build_label_numbers_from_file(FIXTURES / "shared_section_theorems.tex")
        self.assertEqual(actual, EXPECTED_SHARED_SECTION)

    def test_global_and_subsection_theorems(self) -> None:
        actual = build_label_numbers_from_file(FIXTURES / "global_and_subsection_theorems.tex")
        self.assertEqual(actual, EXPECTED_GLOBAL_SUBSECTION)

    def test_cli_writes_label_mapping(self) -> None:
        fixture = FIXTURES / "shared_section_theorems.tex"
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "numbers.json"
            result = subprocess.run(
                [sys.executable, "-m", "yaddag.latex_to_label_numbers", str(fixture), str(output)],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(output.read_text(encoding="utf-8")), EXPECTED_SHARED_SECTION)

    def test_graph_extractor_uses_local_counter_numbers(self) -> None:
        graph = build_graph(
            FIXTURES / "shared_section_theorems.tex",
            granularity="subsection",
            include_definitions=False,
            default_status="can_state",
        )
        self.assertEqual(graph["source"]["reference_numbering"]["mode"], "local_counter")
        self.assertEqual(graph["reference_catalog"]["lem:second"]["number"], "2.1")
        self.assertEqual(graph["nodes"][0]["number"], "1.1")

    @unittest.skipUnless(shutil.which("latexmk"), "latexmk is not installed")
    def test_fixtures_match_latexmk_auxiliary_numbers(self) -> None:
        latexmk = shutil.which("latexmk")
        assert latexmk is not None
        for fixture in sorted(FIXTURES.glob("*.tex")):
            with self.subTest(fixture=fixture.name), tempfile.TemporaryDirectory() as temporary:
                output_directory = Path(temporary)
                result = subprocess.run(
                    [
                        latexmk,
                        "-pdf",
                        "-interaction=nonstopmode",
                        "-halt-on-error",
                        f"-outdir={output_directory}",
                        str(fixture.resolve()),
                    ],
                    cwd=fixture.parent,
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(result.returncode, 0, result.stdout + "\n" + result.stderr)
                aux_file = output_directory / f"{fixture.stem}.aux"
                expected = parse_aux_label_numbers(aux_file.read_text(encoding="utf-8", errors="replace"))
                actual = build_label_numbers_from_file(fixture)
                self.assertEqual(actual, expected)
