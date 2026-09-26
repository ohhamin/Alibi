# ALIBI

AI 캐릭터들이 각자의 비밀·목표·기억을 가지고 행동하는 턴제 추리게임입니다.

현재 첫 스토리 **《폐점 후의 서점》**을 기준으로 Flutter 모바일 앱, FastAPI 백엔드, Supabase, OpenAI 에이전트가 연결되어 있습니다.

## 현재 게임 흐름

- Supabase Auth 이메일 로그인/가입
- 4명의 용의자 중 플레이 캐릭터 선택
- 선택 캐릭터의 개인 배경·목표·비밀·사건 당시 타임라인 확인
- 총 6라운드 진행
- 한 라운드는 **모든 인물이 1행동씩 두 바퀴** 순환
  - 플레이어
  - 나머지 용의자 3명
  - 탐정 강해진
  - 다시 같은 순서로 두 번째 행동
- 각 주행동 전에 인접 장소 1칸 무료 이동 가능
- 조사/수색/대화/증거 제시/행동 넘기기 지원
- NPC↔NPC 대화도 플레이어가 같은 장소에서 목격하면 상황판에 개별 말풍선으로 표시
- 시스템 공지·라운드 구분·행동 구분선을 분리한 사건 채팅형 상황판
- 라운드 종료 인터랙션 제공

## 증거 시스템

### 비공개 소지

게임 시작 시 4명의 용의자가 각각 **서로 중복되지 않는 증거 3개**를 무작위로 받습니다.

- 플레이어가 찾은 증거 → 플레이어 비공개 소지
- NPC가 찾은 증거 → 해당 NPC 비공개 소지
- 한 세션에서 같은 증거는 두 사람이 동시에 발견할 수 없음
- 비공개 증거는 일반 플레이 중 자동 공개되지 않음

### 공개되는 경우

- 탐정이 직접 발견한 증거 → 즉시 공개
- 플레이어가 탐정에게 직접 제시한 비공개 증거 → 공개
- 2·5라운드 비공개 취조 전에 강제로 제출한 증거 → 공개

증거 제출은 **매 라운드가 아니라 2라운드와 5라운드의 탐정 취조 직전에만 1개씩** 요구됩니다.

NPC는 자기 알리바이에 유리한 증거를 우선 제출하고 자신에게 불리한 증거는 가능한 오래 숨기도록 행동합니다.

## 대화와 AI 캐릭터

각 캐릭터는 서로 분리된 상태를 가집니다.

- 전용 시스템 프롬프트
- 개인 배경과 목표
- 알고 있는 사실
- 거짓말 정책
- 개인 기억(`agent_memories`)
- 다른 용의자에 대한 관계도와 의심도

대화, 목격, 공개 증거에 따라 관계와 의심도가 달라집니다.

NPC는 탐정처럼 사건 전체를 조사하는 대신 **자기 알리바이 구축, 자기방어, 불리한 증거 해명**을 우선합니다.

같은 시간대·같은 알리바이 질문을 표현만 바꿔 반복하는 경우 서버에서 주제 중복을 감지해 다른 질문이나 조사 행동으로 전환합니다.

## 2·5라운드 탐정 비공개 취조

2라운드와 5라운드 종료 시:

1. 증거를 가진 각 용의자가 증거 1개를 탐정에게 제출
2. 제출 증거는 모두 공개
3. 탐정이 각 용의자를 비공개 취조
4. 플레이어는 탐정과 실제 대화 세션 진행
5. 대화 내용은 탐정과 해당 인물만 알 수 있음
6. 단, 탐정에게 제시한 증거 자체는 공개

NPC 3명의 자동 취조 답변은 지연을 줄이기 위해 병렬 생성됩니다.

## 최종 결과

6라운드가 끝나면 바로 진실을 공개하지 않습니다.

1. 모든 용의자가 자신과 탐정을 제외한 한 명을 예상 범인으로 선택
2. 이유를 제출
3. 플레이어는 남아 있는 비공개 증거 1개를 최종 제보로 선택 가능(선택 사항)
4. **용의자들의 선택**을 먼저 표시
5. `탐정의 선택 보기` 버튼으로 탐정 판정 공개
6. `사건의 진실 보기` 버튼으로 실제 사건의 진실 공개

탐정은 직접 확보한 증거와 진술을 가장 중요하게 보고, 용의자들의 최종 의견과 제안된 증거를 보조 정보로 사용합니다.

### 플레이어 성공 조건

- 탐정이 플레이어를 최종 범인으로 지목함 → **실패**
- 탐정이 다른 인물을 지목함 → **성공**

플레이어가 실제 범인인지 여부와 무관하게 이 기준으로 성공/실패가 결정됩니다.

## NPC 행동 속도 최적화

탐정의 수사력과 긴장감은 유지하면서 **용의자 NPC의 행동 결정만 즉시 계산되는 전략 엔진으로 경량화**되어 있습니다.

용의자가 이동/대화/조사 중 무엇을 할지 정할 때는 더 이상 매 행동마다 LLM을 호출하지 않습니다. 서버에 이미 저장된 게임 상태를 사용합니다.

- 현재 위치와 인접 장소
- 이번 라운드에 이미 대화한 상대
- 인물별 관계도와 의심도
- 현재 라운드와 첫 번째/두 번째 행동 순서
- 반복 질문 방지 기록

첫 번째 행동에서는 자신의 알리바이를 확인해 줄 수 있는 상대와의 대화를 우선하고, 두 번째 행동에서는 불리한 정황 확인이나 증거 조사를 더 우선합니다. 관계도와 의심도에 따라 대화 상대가 달라지고, 같은 상대/같은 질문만 반복하지 않도록 서버가 제어합니다.

NPC↔NPC 대화는 다음처럼 처리합니다.

- 플레이어가 같은 장소에서 목격하는 NPC↔NPC 대화만 자연어 답변을 LLM으로 생성
- 목격 가능한 NPC 답변은 압축 컨텍스트 + 최대 약 90 output tokens + 약 2.8초 상한
- 플레이어가 볼 수 없는 다른 장소의 NPC↔NPC 대화는 추가 LLM 호출을 생략
- 보이지 않는 대화도 deterministic 반응으로 내부 기억·관계도·의심도는 정상 갱신
- 플레이어가 직접 NPC와 대화하는 경로는 품질 유지를 위해 기존 대화 컨텍스트 사용

**탐정의 행동 선택과 직접 수사는 기존 LLM 컨텍스트와 시간 제한을 그대로 유지**합니다. 탐정의 증거 발견 빈도도 낮추지 않습니다.

공통 OpenAI 클라이언트는 내부 재시도를 하지 않고, 구조화 응답 실패 시 게임 상태를 멈추지 않고 fallback으로 진행합니다.

## 운영 구조

```text
Flutter Android
  ├─ Supabase Auth
  └─ HTTPS
       ↓
https://alibi-api.duckdns.org
       ↓
AWS EC2 (Amazon Linux)
  ├─ Nginx :80/:443
  └─ Docker
      └─ FastAPI :8000 (localhost only)
          ├─ Supabase PostgreSQL
          └─ OpenAI Responses API
```

Flutter는 `game_private` 스키마를 직접 읽지 않습니다.

스토리 정답, 캐릭터 비밀 프롬프트, 비공개 증거 소유 상태와 OpenAI API Key는 FastAPI 백엔드만 접근합니다.

## 인증

모바일은 Supabase access token을 `Authorization: Bearer ...`로 전송합니다.

- access token 만료 약 60초 전에 선제 갱신
- API가 401을 반환하면 `refreshSession()` 후 1회 재시도
- 일시적인 네트워크/DNS 오류를 로그아웃으로 취급하지 않음
- 실제 `signedOut` 이벤트일 때만 로그인 화면으로 이동

## 네트워크/자동 진행 보호

NPC 턴 자동 진행 중 네트워크 오류가 발생하면 무한 `/advance` 호출을 하지 않습니다.

- 재시도 백오프
- 반복 실패 시 자동 진행 일시정지
- 같은 세션의 `/advance` 서버 동시 실행 직렬화
- 완료된 게임에 대한 재호출은 엔딩 상태 유지

## Backend 로컬 실행

```bash
cd backend
cp .env.example .env

python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

필수 환경 변수 예시:

```env
DATABASE_URL=postgresql://...
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-5.6-luna
OPENAI_TIMEOUT_SECONDS=30
OPENAI_MAX_OUTPUT_TOKENS=400
```

헬스 체크:

```bash
curl http://localhost:8000/health
```

## AWS EC2 운영 배포

```bash
git clone https://github.com/ohhamin/Alibi.git
cd Alibi
bash deploy/ec2/bootstrap-amazon-linux.sh
```

운영 환경값:

```bash
nano backend/.env.production
```

시작/재배포:

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

상태 확인:

```bash
docker compose -f docker-compose.prod.yml ps
curl https://alibi-api.duckdns.org/health
```

로그:

```bash
docker compose -f docker-compose.prod.yml logs -f backend
```

## Flutter 실행

로컬 Android emulator:

```bash
flutter run \
  --dart-define=API_BASE_URL=http://10.0.2.2:8000/api/v1
```

운영 API:

```bash
flutter run \
  --dart-define=API_BASE_URL=https://alibi-api.duckdns.org/api/v1
```

## 주요 API

- `GET /health`
- `GET /api/v1/stories`
- `GET /api/v1/sessions`
- `POST /api/v1/sessions`
- `GET /api/v1/sessions/{session_id}`
- `POST /api/v1/sessions/{session_id}/actions`
- `POST /api/v1/sessions/{session_id}/advance`
- `POST /api/v1/sessions/{session_id}/final-vote`

주요 행동 타입:

- `move`
- `act`
- `search`
- `inspect`
- `ask`
- `present`
- `reply`
- `conversation_present`
- `end_conversation`
- `submit_evidence`
- `skip`

## 저장 구조

주요 테이블/스키마:

```text
public.game_sessions
public.game_turns
public.player_actions
public.session_messages
public.session_clues
public.session_locations

game_private.session_character_states
game_private.session_evidence_holdings
game_private.agent_memories
game_private.internal_events
game_private.story_clues
game_private.story_solutions
```

## CI

GitHub Actions에서 Backend와 Flutter를 검증합니다.

Backend:

- Python compile/test

Mobile:

- Android project generation
- `flutter analyze`
- Release APK build
- `alibi-apk` artifact upload

## 현재 구현 상태

현재 첫 스토리 《폐점 후의 서점》은 다음 전체 흐름까지 플레이할 수 있습니다.

**캐릭터 선택 → 초기 증거 배분 → 6라운드 수사/대화 → 2·5라운드 증거 제출·취조 → 용의자 최종 의견 → 탐정 판정 → 성공/실패 → 사건의 진실 공개**
