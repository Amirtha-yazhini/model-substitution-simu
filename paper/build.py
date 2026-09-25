"""Compile paper/main.tex to paper/build/main.pdf and report the page count.

Uses Tectonic (a self-contained LaTeX engine that fetches packages on demand), looked up
first in paper/.tools/ and then on PATH. Set PAPER_LATEX=latexmk to use a local TeX install.

    python paper/build.py
"""
import os
import re
import shutil
import subprocess
import sys
import zlib
from pathlib import Path

PAPER = Path(__file__).resolve().parent
BUILD = PAPER / "build"
PAGE_LIMIT = 6


def engine_command():
    if os.environ.get("PAPER_LATEX") == "latexmk":
        return ["latexmk", "-pdf", "-interaction=nonstopmode", f"-outdir={BUILD}", "main.tex"]
    local = PAPER / ".tools" / ("tectonic.exe" if os.name == "nt" else "tectonic")
    tectonic = str(local) if local.exists() else shutil.which("tectonic")
    if not tectonic:
        sys.exit("No LaTeX engine: put tectonic in paper/.tools/ or set PAPER_LATEX=latexmk.")
    return [tectonic, "--keep-logs", "--outdir", str(BUILD), "main.tex"]


def page_count(pdf: Path) -> int:
    """Read /Count from the page tree, looking inside compressed object streams if needed."""
    data = pdf.read_bytes()
    chunks = [data]
    for m in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", data, re.S):
        try:
            chunks.append(zlib.decompress(m.group(1)))
        except zlib.error:
            pass
    counts = [int(c) for chunk in chunks
              for c in re.findall(rb"/Type\s*/Pages\b[^>]*?/Count\s+(\d+)", chunk)]
    counts += [int(c) for chunk in chunks
               for c in re.findall(rb"/Count\s+(\d+)[^>]*?/Type\s*/Pages\b", chunk)]
    return max(counts) if counts else -1


def main():
    BUILD.mkdir(exist_ok=True)
    result = subprocess.run(engine_command(), cwd=PAPER)
    if result.returncode != 0:
        sys.exit(f"Build failed. See {BUILD / 'main.log'}")
    pdf = BUILD / "main.pdf"
    pages = page_count(pdf)
    status = "OVER LIMIT" if pages > PAGE_LIMIT else "ok"
    print(f"\n{pdf.relative_to(PAPER.parent)}: {pages} / {PAGE_LIMIT} pages ({status})")
    if pages > PAGE_LIMIT:
        sys.exit(1)


if __name__ == "__main__":
    main()
