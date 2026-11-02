"""Build first_draft.tex (IEEEtran, editable) and first_draft.pdf (WeasyPrint two-column rendering)
from manuscript/first_draft.md.  The .md is the single source; both outputs are generated from it.

Usage: python research/scripts/build_manuscript.py [--no-pdf]
"""
import html
import re
import sys
from pathlib import Path

MAN = Path(__file__).resolve().parents[1] / "manuscript"
SRC = MAN / "first_draft.md"
BIB = MAN / "references.bib"

ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"]
TEX_CHARS = {"τ": r"$\tau$", "γ": r"$\gamma$", "β": r"$\beta$", "μ": r"$\mu$", "σ": r"$\sigma$", "ε": r"$\epsilon$",
             "×": r"$\times$", "±": r"$\pm$", "≥": r"$\geq$", "≤": r"$\leq$", "−": r"$-$", "°": r"$^{\circ}$",
             "↑": r"$\uparrow$", "↓": r"$\downarrow$", "–": "--", "—": "---", "≈": r"$\approx$", "′": "'", "·": r"$\cdot$",
             "∈": r"$\in$", "æ": r"{\ae}", "“": "``", "”": "''", "’": "'", "‘": "`"}
TOKEN = re.compile(r"(\$[^$]+\$|`[^`]+`|\[@[^\]]+\]|\[#[^\]]+\]|\*\*[^*]+\*\*|\*[^*]+\*|p_Holm|10\^-\d)")


# ----------------------------------------------------------------------------- parsing
def parse(md):
    blocks, cur = [], []
    for line in md.splitlines():
        if line.strip() == "":
            if cur:
                blocks.append("\n".join(cur)); cur = []
        else:
            cur.append(line)
    if cur:
        blocks.append("\n".join(cur))
    out, caption = [], None
    for b in blocks:
        if b.startswith("# "):
            out.append(("title", b[2:].strip()))
        elif b.startswith("## "):
            out.append(("h1", b[3:].strip()))
        elif b.startswith("### "):
            out.append(("h2", b[4:].strip()))
        elif b.startswith("Table:"):
            m = re.match(r"Table:\s*(.*?)\s*\{#(tab:[\w]+)\}\s*$", b, re.S)
            caption = (m.group(1), m.group(2))
        elif b.startswith("|"):
            rows = [[c.strip() for c in r.strip().strip("|").split("|")] for r in b.splitlines()]
            rows = [r for i, r in enumerate(rows) if i != 1]
            out.append(("table", rows, caption)); caption = None
        elif b.startswith("!["):
            m = re.match(r"!\[(.*?)\]\((.*?)\)\{#(fig:\w+)(?: width=([\d.]+))?\}", b, re.S)
            out.append(("figure", m.group(1), m.group(2), m.group(3), float(m.group(4) or 1)))
        elif b.startswith("$$"):
            out.append(("eq", b.strip().strip("$").strip()))
        elif re.match(r"^\d\. ", b):
            out.append(("list", [re.sub(r"^\d\.\s*", "", x) for x in re.split(r"\n(?=\d\. )", b)]))
        else:
            out.append(("p", b.replace("\n", " ")))
    return out


def number_refs(blocks):
    tabs, figs = {}, {}
    for b in blocks:
        if b[0] == "table" and b[2]:
            tabs[b[2][1]] = len(tabs) + 1
        if b[0] == "figure":
            figs[b[3]] = len(figs) + 1
    return tabs, figs


def cite_order(blocks):
    order = []
    for b in blocks:
        txt = " ".join(map(str, b[1:2])) if b[0] != "table" else " ".join(" ".join(r) for r in b[1])
        if b[0] == "list":
            txt = " ".join(b[1])
        for m in re.finditer(r"\[@([^\]]+)\]", txt):
            for k in m.group(1).split(","):
                k = k.strip()
                if k not in order:
                    order.append(k)
    return order


# ----------------------------------------------------------------------------- LaTeX
def tex_escape(t):
    t = t.replace("\\", r"\textbackslash{}")
    for c in "&%#_":
        t = t.replace(c, "\\" + c)
    t = t.replace("~", r"\textasciitilde{}").replace("^", r"\textasciicircum{}")
    for k, v in TEX_CHARS.items():
        t = t.replace(k, v)
    return t


def tex_inline(t):
    out = []
    for part in TOKEN.split(t):
        if not part:
            continue
        if part == "p_Holm":
            out.append(r"$p_{\mathrm{Holm}}$")
        elif part.startswith("10^-"):
            out.append(f"$10^{{-{part[-1]}}}$")
        elif part.startswith("$"):
            out.append(part)
        elif part.startswith("`"):
            out.append(r"\texttt{" + tex_escape(part[1:-1]).replace(r"\_", r"\_") + "}")
        elif part.startswith("[@"):
            out.append(r"\cite{" + part[2:-1].replace(" ", "") + "}")
        elif part.startswith("[#"):
            out.append(r"Table~\ref{" + part[2:-1] + "}" if part[2:].startswith("tab") else r"Fig.~\ref{" + part[2:-1] + "}")
        elif part.startswith("**"):
            out.append(r"\textbf{" + tex_inline(part[2:-2]) + "}")
        elif part.startswith("*"):
            out.append(r"\emph{" + tex_inline(part[1:-1]) + "}")
        else:
            out.append(tex_escape(part))
    return "".join(out)


def strip_num(h):
    return re.sub(r"^[IVX]+\.\s*|^[A-Z]\.\s*", "", h)


def to_tex(blocks):
    title = next(b[1] for b in blocks if b[0] == "title")
    L = [r"\documentclass[conference]{IEEEtran}",
         r"\usepackage{amsmath,amssymb,graphicx,booktabs,textcomp,url,cite}",
         r"\usepackage[T1]{fontenc}",
         r"\hyphenation{Sentinel DarkRS ExDark}",
         r"\begin{document}",
         r"\title{" + tex_inline(title) + "}",
         r"\author{\IEEEauthorblockN{[Authors to be added]}\IEEEauthorblockA{Draft manuscript generated from \texttt{research/manuscript/first\_draft.md}}}",
         r"\maketitle"]
    sec = None
    i = 0
    while i < len(blocks):
        b = blocks[i]
        k = b[0]
        if k == "title":
            pass
        elif k == "h1" and b[1] == "Abstract":
            abs_txt = blocks[i + 1][1]; kw = blocks[i + 2][1]
            kw = re.sub(r"^\*\*Keywords\*\*\s*—\s*", "", kw)
            L += [r"\begin{abstract}", tex_inline(abs_txt), r"\end{abstract}", r"\begin{IEEEkeywords}", tex_inline(kw), r"\end{IEEEkeywords}"]
            i += 2
        elif k == "h1":
            h = strip_num(b[1])
            L.append((r"\section*{" if h.startswith("Data and Code") else r"\section{") + tex_inline(h) + "}")
        elif k == "h2":
            L.append(r"\subsection{" + tex_inline(strip_num(b[1])) + "}")
        elif k == "p":
            L.append(tex_inline(b[1]) + "\n")
        elif k == "list":
            L += [r"\begin{enumerate}"] + [r"\item " + tex_inline(x) for x in b[1]] + [r"\end{enumerate}"]
        elif k == "eq":
            L.append(r"\begin{equation}" + "\n" + b[1] + "\n" + r"\end{equation}")
        elif k == "figure":
            _, cap, path, lab, w = b
            L += [r"\begin{figure}[t]", r"\centering", rf"\includegraphics[width={w}\columnwidth]{{{path}}}",
                  r"\caption{" + tex_inline(cap) + "}", rf"\label{{{lab}}}", r"\end{figure}"]
        elif k == "table":
            rows, cap = b[1], b[2]
            n = len(rows[0])
            spec = "l" + "c" * (n - 1)
            L += [r"\begin{table}[t]", r"\caption{" + tex_inline(cap[0]) + "}", rf"\label{{{cap[1]}}}", r"\centering\scriptsize",
                  r"\setlength{\tabcolsep}{2.5pt}", r"\resizebox{\columnwidth}{!}{%", rf"\begin{{tabular}}{{{spec}}}", r"\toprule",
                  " & ".join(tex_inline(c) for c in rows[0]) + r" \\", r"\midrule"]
            L += [" & ".join(tex_inline(c) for c in r) + r" \\" for r in rows[1:]]
            L += [r"\bottomrule", r"\end{tabular}}", r"\end{table}"]
        i += 1
    L += [r"\bibliographystyle{IEEEtran}", r"\bibliography{references}", r"\end{document}"]
    return "\n".join(L) + "\n"


# ----------------------------------------------------------------------------- HTML / PDF
GREEK = {r"\tau": "τ", r"\gamma": "γ", r"\beta": "β", r"\mu": "μ", r"\sigma": "σ", r"\epsilon": "ε", r"\times": "×",
         r"\pm": "±", r"\geq": "≥", r"\leq": "≤", r"\in": "∈", r"\approx": "≈", r"\cdot": "·", r"\uparrow": "↑", r"\downarrow": "↓"}


def math_html(m):
    s = m
    s = re.sub(r"\\mathrm\{([^}]*)\}", r"\1", s)
    s = re.sub(r"\\(?:tilde|bar)\{(\w)\}", "\\1\u0303", s)
    s = re.sub(r"\^\{\\circ\}", "°", s)
    for k, v in GREEK.items():
        s = re.sub(re.escape(k) + r"(?![A-Za-z])", v, s)
    s = re.sub(r"_\{([^}]*)\}", r"<sub>\1</sub>", s)
    s = re.sub(r"_(\w)", r"<sub>\1</sub>", s)
    s = re.sub(r"\^\{([^}]*)\}", r"<sup>\1</sup>", s)
    s = re.sub(r"\^(\w)", r"<sup>\1</sup>", s)
    s = re.sub(r"\\(?:bigl|bigr|left|right)", "", s)
    s = s.replace(r"\ln", "ln").replace(r"\,", " ").replace("\\ ", " ").replace("\\sqrt", "√")
    s = s.replace("{", "").replace("}", "")
    return s


def html_inline(t, nums, cites):
    out = []
    for part in TOKEN.split(t):
        if not part:
            continue
        if part == "p_Holm":
            out.append("<i>p</i><sub>Holm</sub>")
        elif part.startswith("10^-"):
            out.append(f"10<sup>−{part[-1]}</sup>")
        elif part.startswith("$"):
            out.append("<i>" + math_html(part[1:-1]) + "</i>")
        elif part.startswith("`"):
            out.append("<code>" + html.escape(part[1:-1]) + "</code>")
        elif part.startswith("[@"):
            ks = [k.strip() for k in part[2:-1].split(",")]
            out.append("[" + ", ".join(str(cites.index(k) + 1) for k in ks) + "]")
        elif part.startswith("[#"):
            key = part[2:-1]
            out.append(f"Table {ROMAN[nums['tab'][key] - 1]}" if key.startswith("tab") else f"Fig. {nums['fig'][key]}")
        elif part.startswith("**"):
            out.append("<b>" + html_inline(part[2:-2], nums, cites) + "</b>")
        elif part.startswith("*"):
            out.append("<i>" + html_inline(part[1:-1], nums, cites) + "</i>")
        else:
            out.append(html.escape(part))
    return "".join(out)


def parse_bib():
    txt = BIB.read_text()
    ents = {}
    for m in re.finditer(r"^@(\w+)\{([^,]+),(.*)\}\s*$", txt, re.M):
        body = m.group(3)
        f = {}
        for fm in re.finditer(r"(\w+)\s*=\s*", body):
            j = fm.end()
            if body[j] == "{":
                d, k = 0, j
                while True:
                    d += body[k] == "{"; d -= body[k] == "}"
                    k += 1
                    if d == 0:
                        break
                f[fm.group(1).lower()] = body[j + 1:k - 1]
            elif body[j].isdigit():
                f[fm.group(1).lower()] = re.match(r"\d+", body[j:]).group(0)
        ents[m.group(2).strip()] = f
    return ents


def fmt_ref(f):
    au = [a.strip() for a in f.get("author", "").split(" and ")]
    names = []
    for a in au:
        if "," in a:
            last, first = [x.strip() for x in a.split(",", 1)]
            ini = " ".join(w[0] + "." for w in re.split(r"[\s-]+", first) if w)
            names.append(f"{ini} {last}")
        else:
            names.append(a)
    a_txt = ", ".join(names[:-1]) + (", and " if len(names) > 2 else " and ") + names[-1] if len(names) > 1 else (names[0] if names else "")
    clean = lambda s: re.sub(r"[{}]", "", s).replace("--", "–").replace("\\&", "&").replace("``", "“").replace("''", "”")
    parts = [clean(a_txt), f"“{clean(f.get('title', ''))},”"]
    src = f.get("journal") or f.get("booktitle") or ""
    if src:
        parts.append(f"<i>{clean(src)}</i>,")
    for key, lab in (("volume", "vol. "), ("number", "no. "), ("pages", "pp. ")):
        if f.get(key):
            parts.append(f"{lab}{clean(f[key])},")
    if f.get("publisher") and not f.get("journal"):
        parts.append(clean(f["publisher"]) + ",")
    parts.append(f"{f.get('year', '')}.")
    if f.get("doi"):
        parts.append(f"doi:{clean(f['doi'])}")
    return " ".join(p for p in parts if p)


def render_eq(tex, idx, outdir):
    """Render one display equation to a PNG with matplotlib mathtext (STIX serif).  Raises on any parse error and
    returns (path, width_pt, height_pt) at natural size (never rescaled, so symbols match the body text)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import rcParams
    rcParams["mathtext.fontset"] = "stix"
    outdir.mkdir(exist_ok=True)
    dpi = 300
    fig = plt.figure(figsize=(0.01, 0.01))
    mt = re.sub(r"\\big[lr]?|\\Big[lr]?", "", tex)       # mathtext has no \\bigl/\\bigr; sizes are cosmetic
    fig.text(0, 0, f"${mt}$", fontsize=10)
    p = outdir / f"eq{idx}.png"
    fig.savefig(p, dpi=dpi, bbox_inches="tight", pad_inches=0.03, transparent=True)
    plt.close(fig)
    from PIL import Image
    w, h = Image.open(p).size
    assert w > 20 and h > 10, f"equation {idx} rendered empty: {tex}"
    return p, w * 72.0 / dpi, h * 72.0 / dpi


CSS = """
@page { size: A4; margin: 15mm 13mm 16mm 13mm; @bottom-center { content: counter(page); font: 8pt serif; } }
body { font-family: 'Liberation Serif','Times New Roman','DejaVu Serif',serif; font-size: 9pt; line-height: 1.22; text-align: justify; hyphens: auto; }
h1.title { font-size: 17pt; text-align: center; margin: 0 0 3pt; font-weight: bold; line-height: 1.15; }
.auth { text-align: center; font-size: 9pt; margin-bottom: 7pt; font-style: italic; }
.abs { font-weight: bold; font-size: 8.5pt; margin-bottom: 6pt; }
.cols { column-count: 2; column-gap: 7mm; }
h2.s { font-size: 9pt; text-transform: uppercase; text-align: center; margin: 8pt 0 3pt; font-weight: normal; letter-spacing: .3pt; break-after: avoid; }
h3.ss { font-size: 9pt; font-style: italic; margin: 6pt 0 2pt; font-weight: normal; break-after: avoid; }
p { margin: 0 0 4pt; }
table { border-collapse: collapse; width: 100%; font-size: 6.6pt; margin: 2pt 0 6pt; text-align: center; }
th, td { padding: 1pt 2pt; border-top: .4pt solid #888; }
th { border-bottom: .6pt solid #000; border-top: .8pt solid #000; }
tr:last-child td { border-bottom: .8pt solid #000; }
td:first-child, th:first-child { text-align: left; }
.cap { font-size: 7.5pt; text-align: center; margin: 4pt 0 1pt; break-after: avoid; }
.tbl { break-inside: avoid; }
.wide { column-span: all; }
figure { margin: 4pt 0; text-align: center; break-inside: avoid; }
figure.wide { column-span: all; }
figure img { max-width: 100%; }
figcaption { font-size: 7.5pt; margin-top: 2pt; }
.eq { display: flex; align-items: center; margin: 4pt 0; } .eq .m { flex: 1; text-align: center; } .eq .n { width: 16pt; text-align: right; font-size: 9pt; }
code { font-family: 'DejaVu Sans Mono', monospace; font-size: 7pt; }
ol { margin: 0 0 4pt 12pt; padding: 0; } li { margin: 0 0 2pt; }
.refs { font-size: 7.5pt; text-align: left; } .refs p { margin: 0 0 2pt; padding-left: 14pt; text-indent: -14pt; }
"""


def to_html(blocks, eqdir):
    tabs, figs = number_refs(blocks)
    nums = {"tab": tabs, "fig": figs}
    cites = cite_order(blocks)
    ent = parse_bib()
    title = next(b[1] for b in blocks if b[0] == "title")
    H = [f"<html><head><meta charset='utf-8'><style>{CSS}</style></head><body>",
         f"<h1 class='title'>{html.escape(title)}</h1><div class='auth'>[Authors to be added] — corrected draft v2. <b>Fallback rendering (WeasyPrint); this PDF was not compiled with IEEEtran/LaTeX.</b></div>"]
    sec = 0
    i, eq_i = 0, 0
    opened = False
    while i < len(blocks):
        b = blocks[i]
        k = b[0]
        if k == "h1" and b[1] == "Abstract":
            H.append("<div class='abs'><i>Abstract</i>—" + html_inline(blocks[i + 1][1], nums, cites) + "<br><br>" +
                     html_inline(blocks[i + 2][1].replace("**Keywords** — ", "<i>Index Terms</i>—"), nums, cites).replace("&lt;i&gt;Index Terms&lt;/i&gt;", "Index Terms") + "</div>")
            H.append("<div class='cols'>"); opened = True
            i += 3
            continue
        if k == "h1":
            h = b[1]
            H.append(f"<h2 class='s'>{html.escape(h)}</h2>")
        elif k == "h2":
            H.append(f"<h3 class='ss'>{html.escape(b[1])}</h3>")
        elif k == "p":
            H.append("<p>" + html_inline(b[1], nums, cites) + "</p>")
        elif k == "list":
            H.append("<ol>" + "".join("<li>" + html_inline(x, nums, cites) + "</li>" for x in b[1]) + "</ol>")
        elif k == "eq":
            eq_i += 1
            p, w_pt, h_pt = render_eq(b[1], eq_i, eqdir)
            assert w_pt < 235, f"equation {eq_i} is wider than a column ({w_pt:.0f} pt): split it"
            H.append(f"<div class='eq'><div class='m'><img src='{p.as_uri()}' style='width:{w_pt:.1f}pt;height:{h_pt:.1f}pt'></div><div class='n'>({eq_i})</div></div>")
        elif k == "figure":
            _, cap, path, lab, w = b
            H.append(f"<figure class='wide'><img src='{(MAN / path).resolve().as_uri()}' style='width:{int(w * 100)}%'>"
                     f"<figcaption>Fig. {figs[lab]}. {html_inline(cap, nums, cites)}</figcaption></figure>")
        elif k == "table":
            rows, cap = b[1], b[2]
            wide = len(rows[0]) >= 6
            t = f"<div class='tbl {'wide' if wide else ''}'><div class='cap'>TABLE {ROMAN[tabs[cap[1]] - 1]}<br>{html_inline(cap[0], nums, cites).upper() if False else html_inline(cap[0], nums, cites)}</div><table>"
            t += "<tr>" + "".join(f"<th>{html_inline(c, nums, cites)}</th>" for c in rows[0]) + "</tr>"
            for r in rows[1:]:
                t += "<tr>" + "".join(f"<td>{html_inline(c, nums, cites)}</td>" for c in r) + "</tr>"
            H.append(t + "</table></div>")
        i += 1
    H.append("<h2 class='s'>References</h2><div class='refs'>")
    for n, key in enumerate(cites, 1):
        H.append(f"<p>[{n}] {fmt_ref(ent[key])}</p>")
    H.append("</div></div></body></html>")
    return "\n".join(H), cites


def main():
    blocks = parse(SRC.read_text())
    (MAN / "first_draft.tex").write_text(to_tex(blocks))
    print("wrote first_draft.tex")
    cites = cite_order(blocks)
    ent = parse_bib()
    missing = [c for c in cites if c not in ent]
    assert not missing, f"citations without bib entries: {missing}"
    unused = [k for k in ent if k not in cites]
    print("unused bib entries:", unused)
    if "--no-pdf" in sys.argv:
        return
    import weasyprint
    page, _ = to_html(blocks, MAN / "_eq")
    (MAN / "_first_draft.html").write_text(page)
    weasyprint.HTML(string=page, base_url=str(MAN)).write_pdf(MAN / "first_draft.pdf")
    print("wrote first_draft.pdf")


if __name__ == "__main__":
    main()
