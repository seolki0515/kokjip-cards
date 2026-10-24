"""Turn Notion rows marked '깃허브 = 요청' into publish pull requests.

Each row in '05 콘텐츠 운영 기록' is a post. The daily Claude task attaches two
files to the row's page — cards.html and caption.txt — and sets the select
property '깃허브' to '요청'. This script (run by GitHub Actions):

  1. renders cards.html to posts/<date>-<id>/01.jpg ...
  2. copies caption.txt, checks everything with scripts/posts.py
  3. pushes branch post/<folder> and opens a pull request
  4. sets '깃허브' to 'PR 열림' (or '실패') and writes the PR link / error to '깃허브 결과'

Usage: python from_notion.py check   -> prints count, sets has_work output
       python from_notion.py run
"""
import datetime as dt
import json
import os
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

import notion

REPO = Path(__file__).resolve().parent.parent
DB_ID = os.environ.get("NOTION_DB_ID", "174b1222da4d449481420c1925038873")
FLAG, RESULT = "깃허브", "깃허브 결과"
KST = dt.timezone(dt.timedelta(hours=9))
LAST_LINE = "확인 후 Merge하면 바로 인스타에 올라갑니다. 고칠 점은 댓글로 남겨주세요."


def requested():
    return notion.query(DB_ID, {"property": FLAG, "select": {"equals": "요청"}})


def set_out(key, value):
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write(f"{key}={value}\n")


def mark(page_id, flag, result):
    notion.update_page(page_id, {
        FLAG: {"select": {"name": flag}},
        RESULT: {"rich_text": [{"text": {"content": result[:1900]}}]},
    })


def sh(*args):
    subprocess.run(args, cwd=REPO, check=True)


def branch_exists(name):
    r = subprocess.run(["git", "ls-remote", "--exit-code", "--heads", "origin", name], cwd=REPO, capture_output=True)
    return r.returncode == 0


def gh_api(method, path, body):
    req = urllib.request.Request(
        f"https://api.github.com/repos/{os.environ['GITHUB_REPOSITORY']}/{path}",
        data=json.dumps(body).encode(), method=method,
        headers={"Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
                 "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())


def attachments(page_id):
    """Return {filename: url} for file blocks, and the first code block's text."""
    files, code = {}, None
    for b in notion.children(page_id):
        t = b["type"]
        if t in ("file", "image", "pdf"):
            obj = b[t]
            url = (obj.get("file") or obj.get("external") or {}).get("url")
            name = obj.get("name") or url.split("?")[0].rsplit("/", 1)[-1]
            if url:
                files[name] = url
        elif t == "code" and code is None:
            code = "".join(x["plain_text"] for x in b["code"]["rich_text"])
    return files, code


def pick(files, suffix):
    for name, url in files.items():
        if name.lower().endswith(suffix):
            return url
    return None


def build(page):
    from posts import check  # needs Pillow
    from render_cards import render

    pid = page["id"]
    props = page["properties"]
    date = notion.plain(props.get("게시일")) or dt.datetime.now(KST).date().isoformat()
    # Notion page ids in one workspace share their first characters, so use the end.
    folder_name = f"{date[:10]}-{pid.replace('-', '')[-8:]}"
    branch = f"post/{folder_name}"
    if branch_exists(branch):
        return None, f"이미 브랜치가 있음: {branch}"

    files, code = attachments(pid)
    html_url, cap_url = pick(files, ".html"), pick(files, "caption.txt")
    if not html_url:
        raise RuntimeError("페이지에 cards.html 첨부가 없음")
    folder = REPO / "posts" / folder_name
    folder.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        html = Path(tmp) / "cards.html"
        notion.download(html_url, html)
        render(html, folder)
    if cap_url:
        notion.download(cap_url, folder / "caption.txt")
    elif code:
        (folder / "caption.txt").write_text(code.strip() + "\n", encoding="utf-8")
    else:
        raise RuntimeError("caption.txt 첨부도, 캡션 코드블록도 없음")
    (folder / "source.json").write_text(json.dumps({"notion_page_id": pid}, indent=2) + "\n", encoding="utf-8")

    problems = check(folder)
    if problems:
        raise RuntimeError("검사 실패: " + " / ".join(problems))
    is_test = notion.plain(props.get("주제")).startswith("[시험]")
    if is_test:  # a rehearsal row: even if merged by mistake, publish.py skips it
        (folder / "SKIP").write_text("시험용 게시물이라 발행하지 않음\n", encoding="utf-8")

    sh("git", "checkout", "-B", branch, "origin/main")
    sh("git", "add", f"posts/{folder_name}")
    sh("git", "-c", "user.name=kokjip-bot", "-c", "user.email=kokjip-bot@users.noreply.github.com",
       "commit", "-m", f"게시물 추가: {folder_name}")
    sh("git", "push", "origin", branch)
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True).stdout.strip()

    repo = os.environ["GITHUB_REPOSITORY"]
    imgs = sorted(p.name for p in folder.glob("*.jpg"))
    preview = "\n".join(
        f"![{n}](https://raw.githubusercontent.com/{repo}/{sha or branch}/posts/{folder_name}/{n})" for n in imgs)
    caption = (folder / "caption.txt").read_text(encoding="utf-8").strip()
    title_text = " ".join(notion.plain(props.get("표지 문구")).replace("/", " ").split()) or notion.plain(props.get("주제"))
    prefix = "[화제 이슈]" if notion.plain(props.get("메모")).startswith("[화제 이슈]") else "[발행 대기]"
    if is_test:
        prefix = "[시험·발행 안 됨]"
    body = "\n\n".join([
        "### 검토 요약\n" + (notion.plain(props.get("검토 요약")) or "(검토 요약 없음 — Claude 메시지 확인)").replace("\n", "  \n"),
        f"**주제** {notion.plain(props.get('주제'))}",
        f"**선정 이유** {notion.plain(props.get('선정 이유'))}",
        f"**출처** {notion.plain(props.get('공식 원문 링크'))}",
        f"**메모** {notion.plain(props.get('메모'))}",
        f"**노션** {page['url']}",
        f"### 카드 {len(imgs)}장\n{preview}",
        f"### 캡션\n```\n{caption}\n```",
        LAST_LINE,
    ])
    pr = gh_api("POST", "pulls", {
        "title": f"{prefix} {date[5:7].lstrip('0')}/{date[8:10].lstrip('0')} {title_text}"[:120],
        "head": branch, "base": "main", "body": body,
    })
    sh("git", "checkout", "main")
    # Assign the repository owner so GitHub always notifies her (even without watching).
    owner = os.environ["GITHUB_REPOSITORY"].split("/")[0]
    try:
        gh_api("POST", f"issues/{pr['number']}/assignees", {"assignees": [owner]})
    except Exception as e:  # noqa: BLE001 — PR is open; a missing assignee is not fatal
        print(f"   ⚠️ 담당자 지정 실패: {e}")
    return pr["html_url"], None


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "run"
    if not os.environ.get("NOTION_TOKEN", "").strip():
        print("NOTION_TOKEN 비밀값이 아직 없어서 건너뜀")
        set_out("has_work", "false")
        return 0
    pages = requested()
    print(f"발행 요청 {len(pages)}건")
    if mode == "check":
        set_out("has_work", "true" if pages else "false")
        return 0
    failed = False
    for page in pages:
        name = notion.plain(page["properties"].get("주제"))
        try:
            url, note = build(page)
        except Exception as e:  # noqa: BLE001 — report any failure back to Notion
            failed = True
            print(f"❌ {name}: {e}")
            mark(page["id"], "실패", str(e))
            subprocess.run(["git", "checkout", "-f", "main"], cwd=REPO)
            continue
        if url:
            print(f"✅ {name}: {url}")
            mark(page["id"], "PR 열림", url)
        else:  # don't leave it as '요청' or it is retried every 15 minutes
            print(f"⏭️ {name}: {note}")
            mark(page["id"], "실패", note)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
