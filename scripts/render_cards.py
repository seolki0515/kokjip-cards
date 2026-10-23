"""Render every <section class="card"> in a cards.html file to 1080x1350 JPEGs.

Usage: python render_cards.py cards.html OUT_DIR

Font URLs in the HTML (any path ending in Pretendard-<Weight>.otf, or the
FONTDIR placeholder) are rewritten to the fonts/ folder in this repository, so
the same HTML renders identically here and in the Claude workspace.
"""
import io
import re
import sys
import tempfile
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parent.parent
FONTS = (REPO / "fonts").as_uri()


def localize_fonts(html: str) -> str:
    html = re.sub(r'url\((["\']?)[^)"\']*?(Pretendard-[A-Za-z]+\.otf)\1\)', rf'url("{FONTS}/\2")', html)
    return html.replace("FONTDIR", FONTS)


def render(html_path: Path, out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    html = localize_fonts(html_path.read_text(encoding="utf-8"))
    if re.search(r'(src|href)=["\']https?://', html):
        raise SystemExit("cards.html이 외부 파일(이미지·스크립트)을 불러옴. 안에 다 넣어야 함")
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as f:
        f.write(html)
        tmp = Path(f.name)
    written = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1080, "height": 1350}, device_scale_factor=1)
        pg.goto(tmp.as_uri())
        pg.evaluate("document.fonts.ready")
        pg.wait_for_timeout(800)
        cards = pg.locator("section.card")
        n = cards.count()
        if not 1 <= n <= 10:
            raise SystemExit(f"카드(section.card)가 {n}장. 1~10장이어야 함")
        for i in range(n):
            png = cards.nth(i).screenshot()
            im = Image.open(io.BytesIO(png)).convert("RGB")
            if im.size != (1080, 1350):
                im = im.resize((1080, 1350))
            dest = out_dir / f"{i + 1:02d}.jpg"
            im.save(dest, "JPEG", quality=92, optimize=True)
            written.append(dest)
        b.close()
    tmp.unlink(missing_ok=True)
    return written


if __name__ == "__main__":
    for path in render(Path(sys.argv[1]), Path(sys.argv[2])):
        print(path)
