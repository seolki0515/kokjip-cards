# 콕집뉴스 카드 발행함 (@kokjip.news)

Claude가 만든 카드뉴스를 **Pull Request(PR)**로 올리고, Becky가 확인 후 **Merge**를 누르면 인스타그램에 자동으로 발행돼요.

## 매일 흐름

1. 아침에 Claude가 노션 '05 콘텐츠 운영 기록'에 카드(`cards.html`)와 `caption.txt`를 첨부하고 **깃허브 = 요청**으로 표시해요.
   15분 안에 '노션에서 PR 만들기'가 카드를 1080×1350 JPEG로 그려 `posts/날짜-id/` 폴더로 PR을 열어요.
2. 깃허브 앱 알림 → PR을 열어 카드와 캡션을 확인해요.
3. 괜찮으면 **Merge pull request** → **Confirm merge**를 눌러요. 1~2분 뒤 인스타에 올라가고, PR에 게시물 링크 댓글이 달려요.
4. 마음에 안 들면 PR에 댓글로 고칠 점을 적거나 **Close**를 눌러요. 닫은 PR은 발행되지 않아요.

## 폴더 규칙

```
posts/2026-10-24-tax-refund/
  01.jpg  02.jpg  ...   ← 1080×1350 JPEG, 파일 이름 순서대로 올라감 (최대 10장)
  caption.txt           ← 캡션 (URL 넣지 않음, 해시태그 30개 이하)
  published.json        ← 발행 후 자동으로 생김 (있으면 다시 발행하지 않음)
  SKIP                  ← 이 파일을 넣으면 발행하지 않음
```

## 비밀값 (Settings → Secrets and variables → Actions)

| 이름 | 내용 | 없으면 |
| --- | --- | --- |
| `IG_ACCESS_TOKEN` | 인스타그램 장기 토큰 (60일) | 발행을 건너뜀 (오류 아님) |
| `NOTION_TOKEN` | 노션 통합(integration) 토큰. '05 콘텐츠 운영 기록'에 연결돼 있어야 함 | 노션에서 PR을 만들지 않음 |
| `GH_PAT` | 이 저장소의 비밀값만 바꿀 수 있는 깃허브 토큰 | 토큰 자동 연장 후 저장 실패 시 알림 |

## 자동 작업 (Actions 탭)

- **게시물 검사**: PR마다 이미지 크기·장수·캡션 규칙을 검사해요. 빨간 ❌면 Merge하지 마세요.
- **노션에서 PR 만들기**: 15분마다 노션의 '요청'을 확인해요. 결과(PR 링크·오류)는 노션 '깃허브 결과' 칸에 적혀요.
- **인스타 발행**: Merge하면 실행돼요. 발행 후 노션 행을 '발행됨'으로 바꿔요.
- **인스타 토큰 연장**: 매달 1일·15일에 토큰을 연장해요.

제목이 `[시험]`으로 시작하는 노션 행은 PR까지만 만들고, 잘못 Merge해도 발행하지 않아요(SKIP).

⚠️ 설정 → Actions → General → Workflow permissions에서 **Allow GitHub Actions to create and approve pull requests**가 켜져 있어야 PR이 열려요.

⚠️ 이 저장소는 공개(Public)여야 해요. 인스타그램이 이미지 주소로 카드를 가져가기 때문이에요. 토큰은 비밀값 칸에 있어서 공개돼도 보이지 않아요.
