"""Extend the long-lived Instagram token (valid 60 days) and store it back as a secret.

Writes the new token to the file named by NEW_TOKEN_FILE so the workflow can
update the repository secret without printing it.
"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request


def main():
    token = os.environ.get("IG_ACCESS_TOKEN", "").strip()
    if not token:
        print("IG_ACCESS_TOKEN 비밀값이 없어서 건너뜀")
        return 0
    q = urllib.parse.urlencode({"grant_type": "ig_refresh_token", "access_token": token})
    try:
        with urllib.request.urlopen(f"https://graph.instagram.com/refresh_access_token?{q}", timeout=60) as r:
            data = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        print(f"❌ 토큰 연장 실패 (HTTP {e.code}): {e.read().decode(errors='replace')}")
        print("토큰이 이미 만료됐다면 새로 발급받아 IG_ACCESS_TOKEN 비밀값을 바꿔주세요.")
        return 1
    new = data["access_token"]
    days = int(data.get("expires_in", 0)) // 86400
    print(f"✅ 토큰 연장 완료: 앞으로 약 {days}일 유효")
    with open(os.environ["NEW_TOKEN_FILE"], "w", encoding="utf-8") as f:
        f.write(new)
    return 0


if __name__ == "__main__":
    sys.exit(main())
