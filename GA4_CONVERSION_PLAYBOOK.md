# GA4 Conversion Playbook

최종 업데이트: 2026-02-15

## 1) 사전 체크
- `GA4_MEASUREMENT_ID`가 운영 `.env.production`에 설정되어 있어야 합니다.
- 배포 후 `Realtime`에서 최소 1개 이벤트가 들어오는지 먼저 확인합니다.

## 2) 전환(Conversion)으로 지정할 이벤트
우선 아래 3개를 추천합니다.

- `ranking_submit`: 사용자 기록 등록 (핵심 참여)
- `game_finish`: 게임 완료 (체류/완주)
- `utility_use`: 유틸리티 실제 사용

보조 이벤트(관찰용):
- `utility_result`
- `daily_pick_reveal`
- `nav_click`
- `blog_post_click`
- `policy_click`

## 3) GA4에서 전환 설정
1. GA4 접속
2. `관리` -> `이벤트`
3. 이벤트 목록에서 `ranking_submit`, `game_finish`, `utility_use` 찾기
4. 각 이벤트의 `전환으로 표시` 토글 ON

참고: 이벤트가 아직 한 번도 수집되지 않으면 목록에 즉시 안 보일 수 있습니다. 먼저 사이트에서 이벤트를 발생시킨 뒤 새로고침하세요.

## 4) 기본 리포트(탐색) 1개 만들기
추천 이름: `Game Performance Weekly`

- 차원: `eventName`, `pagePath`, `date`
- 측정항목: `eventCount`, `totalUsers`
- 필터: `eventName` in (`ranking_submit`, `game_finish`, `utility_use`)
- 비교: 최근 7일 vs 직전 7일

## 5) 주간 점검 체크리스트
- `ranking_submit` 주간 이벤트 수 증감
- `game_finish / game_start_click` 비율 (완주율)
- `utility_use` 증감
- `/games/*` 페이지별 이벤트 편차

## 6) 실패 시 점검
- 브라우저에서 GTM/GA 차단 확장 프로그램 OFF
- 도메인/프로토콜 불일치 확인 (`https://monosaccharide180.com`)
- 배포 후 캐시/정적파일 미갱신 여부 확인 (`collectstatic`)
