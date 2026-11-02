"""Regression tests for manuscript generation: every equation must render and survive into both outputs."""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import build_manuscript as B  # noqa: E402
import verify_manuscript_numbers  # noqa: E402,F401


def _blocks():
    return B.parse(B.SRC.read_text())


def test_all_display_equations_render_and_fit(tmp_path):
    eqs = [b[1] for b in _blocks() if b[0] == "eq"]
    assert len(eqs) >= 5
    for i, e in enumerate(eqs, 1):
        p, w, h = B.render_eq(e, i, tmp_path)
        assert p.stat().st_size > 500 and 20 < w < 235 and h > 8, (i, e, w, h)


def test_equations_present_in_html_and_tex(tmp_path):
    blocks = _blocks()
    n = sum(b[0] == "eq" for b in blocks)
    page, cites = B.to_html(blocks, tmp_path)
    assert page.count("class='eq'") == n and page.count("<img src='file://" + str(tmp_path)) == n
    tex = B.to_tex(blocks)
    assert tex.count(r"\begin{equation}") == n and tex.count(r"\end{equation}") == n


def test_no_unconverted_markup_in_html(tmp_path):
    page, _ = B.to_html(_blocks(), tmp_path)
    body = re.sub(r"<code>.*?</code>", "", page, flags=re.S)
    body = re.sub(r"<style>.*?</style>", "", body, flags=re.S)
    text = re.sub(r"<[^>]+>", "", body)
    for bad in ("$", "\\tau", "\\gamma", "\\mathrm", "_{", "^{", "[@", "[#", "**"):
        assert bad not in text, bad


def test_citations_and_cross_references_resolve():
    blocks = _blocks()
    ent = B.parse_bib()
    assert not [c for c in B.cite_order(blocks) if c not in ent]
    tabs, figs = B.number_refs(blocks)
    src = B.SRC.read_text()
    for m in re.finditer(r"\[#((?:tab|fig):\w+)\]", src):
        assert m.group(1) in tabs or m.group(1) in figs, m.group(1)


def test_every_figure_file_exists():
    for b in _blocks():
        if b[0] == "figure":
            assert (B.MAN / b[2]).exists(), b[2]


def test_manuscript_numbers_match_recorded_csvs():
    import verify_manuscript_numbers as V
    assert V.main() == 0
