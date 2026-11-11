"""Publish every unpublished post folder on main to Instagram.

Runs in GitHub Actions after a pull request is merged. Images are fetched by
Instagram from raw.githubusercontent.com at the exact commit being published,
so the repository must be public.

중복 게시 방지 (2026-11-11 수정):
인스타가 '게시하기(media_publish)' 단계에서 오류를 돌려줘도 실제로는 게시되는 경우가 있다.
그래서 게시하기 요청 '직전'에 published.json(status=attempted)을 먼저 써 둔다.
이 파일이 있으면 pending_posts()가 그 폴더를 건너뛰므로, 어떤 경우에도 같은 게시물이
두 번 올라가지 않는다. 대신 정말 실패한 날은 자동 재시도를 하지 않으니 앱으로 직접 올린다.
"""
import datetime as dt
import json
import os
import sys

import ig
from posts import check, images, pending_posts

MAX_PER_RUN = 3  # safety net against accidental mass posting


def now_iso():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def raw_url(path):
    repo = os.environ["GITHUB_REPOSITORY"]
    sha = os.environ["GITHUB_SHA"]
    rel = path.relative_to(path.parents[2]).as_posix()  # posts/<folder>/<file>
    return f"https://raw.githubusercontent.com/{repo}/{sha}/{rel}"


def prepare(folder, token, user_id):
    """사진 컨테이너만 만든다. 여기서 실패하면 아무것도 게시되지 않으므로 다음 실행 때 다시 시도해도 안전하다."""
    caption = (folder / "caption.txt").read_text(encoding="utf-8").strip()
    imgs = images(folder)
    if len(imgs) == 1:
        c = ig.post(f"{user_id}/media", token, image_url=raw_url(imgs[0]), caption=caption)
        ig.wait_ready(c["id"], token)
        return c["id"], caption
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
    return parent["id"], caption


def find_recent_post(user_id, token, caption):
    """게시하기 오류 뒤에 실제로 올라갔는지 최근 게시물 캡션으로 확인한다 (최선 노력)."""
    try:
        res = ig.get(f"{user_id}/media", token, fields="id,permalink,caption,timestamp")
        head = caption[:60]
        for m in (res.get("data") or [])[:5]:
            if (m.get("caption") or "").strip()[:60] == head:
                return m.get("id", ""), m.get("permalink", "")
    except Exception as e:  # noqa: BLE001
        print(f"   ⚠️ 최근 게시물 확인 실패: {e}")
    return None, None


def write_record(folder, record):
    (folder / "published.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


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

        # 1단계: 사진 컨테이너 만들기 (실패해도 게시 안 됨 → 다음에 재시도 가능)
        try:
            creation_id, caption = prepare(d, token, user_id)
        except ig.IGError as e:
            failed = True
            print(f"❌ {d.name} 준비 실패(게시 안 됨, 다음 실행 때 재시도): {e}")
            continue

        # 2단계: 게시하기 직전에 '시도함' 기록부터 남긴다 → 이후 어떤 경우에도 재게시 안 됨
        write_record(d, {
            "status": "attempted",
            "creation_id": creation_id,
            "attempted_at": now_iso(),
            "commit": os.environ.get("GITHUB_SHA", ""),
        })

        # 3단계: 게시하기
        try:
            media = ig.post(f"{user_id}/media_publish", token, creation_id=creation_id)
            media_id = media["id"]
            link = ""
            try:
                link = ig.get(media_id, token, fields="permalink").get("permalink", "")
            except Exception as e:  # noqa: BLE001
                print(f"   ⚠️ 링크 확인 실패(게시는 완료): {e}")
        except ig.IGError as e:
            print(f"⚠️ {d.name} 게시하기 단계 오류: {e}")
            media_id, link = find_recent_post(user_id, token, caption)
            if not media_id:
                failed = True
                print(f"❌ {d.name} 인스타에서 게시물을 찾지 못함. 자동 재시도는 하지 않아요 → 인스타 앱을 확인하고, 없으면 직접 올려주세요.")
                continue
            print(f"   오류가 났지만 실제로는 게시됨을 확인: {link}")

        write_record(d, {
            "status": "published",
            "media_id": media_id,
            "permalink": link,
            "published_at": now_iso(),
            "commit": os.environ.get("GITHUB_SHA", ""),
        })
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
