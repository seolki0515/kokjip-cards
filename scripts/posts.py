"""Find and validate post folders: posts/<YYYY-MM-DD-slug>/{01.jpg..., caption.txt}."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "posts"
CAPTION_MAX = 2200
HASHTAG_MAX = 30
IMAGE_MAX_BYTES = 8 * 1024 * 1024


def images(folder: Path):
    return sorted(p for p in folder.iterdir() if p.suffix.lower() in (".jpg", ".jpeg"))


def pending_posts():
    """Post folders on this branch that have not been published yet."""
    if not ROOT.exists():
        return []
    out = []
    for d in sorted(ROOT.iterdir()):
        if not d.is_dir():
            continue
        if (d / "published.json").exists() or (d / "SKIP").exists():
            continue
        out.append(d)
    return out


def check(folder: Path):
    """Return a list of problems (empty list = OK)."""
    from PIL import Image

    problems = []
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}-[a-z0-9-]+", folder.name):
        problems.append(f"폴더 이름 형식이 아님: {folder.name} (예: 2026-10-24-tax-refund)")
    imgs = images(folder)
    if not 1 <= len(imgs) <= 10:
        problems.append(f"이미지는 1~10장이어야 함 (지금 {len(imgs)}장)")
    for p in imgs:
        if p.stat().st_size > IMAGE_MAX_BYTES:
            problems.append(f"{p.name}: 8MB 초과")
        try:
            with Image.open(p) as im:
                if im.format != "JPEG":
                    problems.append(f"{p.name}: JPEG 아님 ({im.format})")
                if im.size != (1080, 1350):
                    problems.append(f"{p.name}: 크기 {im.size[0]}x{im.size[1]} (1080x1350이어야 함)")
        except Exception as e:  # noqa: BLE001
            problems.append(f"{p.name}: 이미지를 열 수 없음 ({e})")
    cap = folder / "caption.txt"
    if not cap.exists():
        problems.append("caption.txt 없음")
    else:
        text = cap.read_text(encoding="utf-8").strip()
        if not text:
            problems.append("caption.txt가 비어 있음")
        if len(text) > CAPTION_MAX:
            problems.append(f"캡션 {len(text)}자 (최대 {CAPTION_MAX}자)")
        tags = re.findall(r"#\S+", text)
        if len(tags) > HASHTAG_MAX:
            problems.append(f"해시태그 {len(tags)}개 (최대 {HASHTAG_MAX}개)")
        if re.search(r"https?://", text):
            problems.append("캡션에 URL이 있음 (콕집뉴스 규칙: 캡션에 링크 넣지 않음)")
    return problems
