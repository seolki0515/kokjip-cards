"""Publish every unpublished post folder on main to Instagram.

Runs in GitHub Actions after a pull request is merged. Images are fetched by
Instagram from raw.githubusercontent.com at the exact commit being published,
so the repository must be public.
"""
import datetime as dt
import json
import os
import sys

import ig
from posts import check, images, pending_posts

MAX_PER_RUN = 3  # safety net against accidental mass posting


def raw_url(path):
    repo = os.environ["GITHUB_REPOSITORY"]
    sha = os.environ["GITHUB_SHA"]
    rel = path.relative_to(path.parents[2]).as_posix()  # posts/<folder>/<file>
    return f"https://raw.githubusercontent.com/{repo}/{sha}/{rel}"


def publish(folder, token, user_id):
    caption = (folder / "caption.txt").read_text(encoding="utf-8").strip()
    imgs = images(folder)
    if len(imgs) == 1:
        c = ig.post(f"{user_id}/media", token, image_url=raw_url(imgs[0]), caption=caption)
        ig.wait_ready(c["id"], token)
        creation_id = c["id"]
    else:
        children = []
        for p in imgs:
            c = ig.post(f"{user_id}/media", token, image_url=raw_url(p), is_carousel_item="true")
            children.append(c["id"])
            print(f"   올림: {p.name}")
        for cid in children:
            ig.wait_ready(cid, token)
        parent = ig.post(
            f"{user_id}/media", token,
            media_type="CAROUSEL", children=",".join(children), caption=caption,
        )
        ig.wait_ready(parent["id"], token)
        creation_id = parent["id"]
    media = ig.post(f"{user_id}/media_publish", token, creation_id=creation_id)
    info = ig.get(media["id"], token, fields="permalink")
    return media["id"], info.get("permalink", "")


def record_in_notion(folder, link):
    """Mark the Notion row as published (best effort; publishing already succeeded)."""
    src = folder / "source.json"
    if not (src.exists() and os.environ.get("NOTION_TOKEN", "").strip()):
        return
    try:
        import notion
        pid = json.loads(src.read_text(encoding="utf-8"))["notion_page_id"]
        notion.update_page(pid, {
            "상태": {"status": {"name": "발행됨"}},
            "게시물 URL": {"url": link or None},
            "깃허브": {"select": {"name": "발행됨"}},
        })
        print("   노션 기록: 발행됨")
    except Exception as e:  # noqa: BLE001
        print(f"   ⚠️ 노션 기록 실패(발행은 완료됨): {e}")


def main():
    token = os.environ.get("IG_ACCESS_TOKEN", "").strip()
    posts = pending_posts()
    if not posts:
        print("발행할 게시물 없음")
        return 0
    if not token:
        print("⚠️ IG_ACCESS_TOKEN 비밀값이 아직 없어서 발행을 건너뜀:", ", ".join(d.name for d in posts))
        return 0
    if len(posts) > MAX_PER_RUN:
        print(f"❌ 발행 대기 게시물이 {len(posts)}개라 멈춤 (한 번에 최대 {MAX_PER_RUN}개). 필요 없는 폴더에 SKIP 파일을 넣어주세요.")
        return 1

    who = ig.me(token)
    user_id = who["user_id"]
    print(f"계정: @{who.get('username')}")

    summary = []
    failed = False
    for d in posts:
        problems = check(d)
        if problems:
            failed = True
            print(f"❌ {d.name} 검사 실패: {problems}")
            continue
        print(f"▶ {d.name} 발행 시작")
        try:
            media_id, link = publish(d, token, user_id)
        except ig.IGError as e:
            failed = True
            print(f"❌ {d.name} 발행 실패: {e}")
            continue
        record = {
            "media_id": media_id,
            "permalink": link,
            "published_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "commit": os.environ.get("GITHUB_SHA", ""),
        }
        (d / "published.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"✅ {d.name} 발행 완료: {link}")
        summary.append(f"- {d.name}: {link}")
        record_in_notion(d, link)

    out = os.environ.get("GITHUB_OUTPUT")
    if out and summary:
        with open(out, "a", encoding="utf-8") as f:
            f.write("published<<EOF\n" + "\n".join(summary) + "\nEOF\n")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
