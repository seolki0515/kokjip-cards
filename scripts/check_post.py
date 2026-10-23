"""Run on every pull request: make sure each unpublished post is ready to publish."""
import sys

from posts import check, pending_posts


def main():
    posts = pending_posts()
    if not posts:
        print("검사할 게시물 없음")
        return 0
    failed = False
    for d in posts:
        problems = check(d)
        if problems:
            failed = True
            print(f"❌ {d.name}")
            for p in problems:
                print(f"   - {p}")
        else:
            print(f"✅ {d.name}: 발행 가능")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
