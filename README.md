# ALIBI

AI 캐릭터와 대화하며 사건을 푸는 턴제 추리게임 MVP입니다.

현재 첫 스토리 **《폐점 후의 서점》** 기준으로 다음 흐름이 연결되어 있습니다.

- Supabase Auth 이메일 로그인/가입
- 공개 스토리 목록 및 진행 중 세션 불러오기
- 4명의 용의자 중 플레이 캐릭터 선택
- 선택한 캐릭터의 개인 배경/목표/비밀만 플레이어에게 공개
- 6라운드, 라운드당 핵심 행동 2회
- 장소 이동(무료), 수색, 조사, AI 인물 심문
- 발견한 증거를 인물에게 제시하고 AI 반응 확인
- 발견 증거/메시지/턴 상태 자동 저장
- 캐릭터별 `agent_memories` 격리
- 최종 지목 및 엔딩/정답 공개

## 구조

```text
Flutter
  ├─ Supabase Auth
  └─ HTTPS
       ↓
AWS App Runner
  └─ FastAPI
      ├─ Supabase PostgreSQL
      └─ OpenAI Responses API
```

Flutter는 `game_private`를 직접 읽지 않습니다. 게임의 비밀 설정, 캐릭터 프롬프트, 정답과 OpenAI API Key는 FastAPI 서버만 접근합니다. 모바일은 Supabase 로그인 토큰을 `Authorization: Bearer ...`로 백엔드에 전달하고, 백엔드는 Supabase Auth에서 토큰을 검증한 뒤 모든 세션 접근에 `user_id` 소유권 조건을 적용합니다.

## 1. 로컬 Backend 실행

Supabase Dashboard에서 **Project Settings > Database > Connection string**의 Pooler 연결 문자열을 복사합니다.

```bash
cd backend
cp .env.example .env
# .env 의 DATABASE_URL 비밀번호를 실제 값으로 변경
# AI 대화를 사용하려면 OPENAI_API_KEY도 설정

python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

확인:

```bash
curl http://localhost:8000/health
```

OpenAI 키가 정상 주입되어 있으면 `openai_configured: true`가 표시됩니다. 키가 없거나 OpenAI 호출이 실패하면 게임 진행이 멈추지 않도록 deterministic fallback 대사를 사용합니다.

## 2. AWS App Runner 배포

저장소의 `backend/apprunner.yaml`을 사용합니다. App Runner에서 GitHub 저장소 `ohhamin/Alibi`를 연결하고 다음처럼 설정합니다.

1. AWS Console → **App Runner → Create service**
2. Source: **Source code repository / GitHub**
3. Repository: `ohhamin/Alibi`, Branch: `master`
4. Source directory: `backend`
5. Deployment: **Automatic**
6. Build settings: **Use a configuration file**
7. Configuration file: `apprunner.yaml`
8. Health check path: `/health`

### AWS Secrets Manager

다음 값은 GitHub나 Flutter에 넣지 않고 Secrets Manager에 저장한 뒤 App Runner 런타임 환경 변수로 연결합니다.

- `DATABASE_URL`: Supabase Pooler PostgreSQL 연결 문자열
- `OPENAI_API_KEY`: OpenAI API Key

App Runner의 **Environment variables → Secrets**에서 각각 위 이름으로 매핑합니다.

일반 환경 변수는 `apprunner.yaml`에 기본값이 있습니다.

- `ENVIRONMENT=production`
- `OPENAI_MODEL=gpt-5.6-luna`
- `OPENAI_TIMEOUT_SECONDS=30`
- `OPENAI_MAX_OUTPUT_TOKENS=400`
- `CORS_ORIGINS=*`

배포 후:

```bash
curl https://<app-runner-domain>/health
```

예상 응답:

```json
{
  "status": "ok",
  "environment": "production",
  "openai_configured": true
}
```

## 3. Flutter 실행

저장소에는 앱 소스 중심으로 들어 있습니다. 최초 1회 네이티브 Android/iOS scaffold를 생성합니다.

```bash
cd mobile
./tool/bootstrap_platforms.sh
```

Android Emulator + 로컬 백엔드라면 기본값 `http://10.0.2.2:8000/api/v1`을 그대로 쓸 수 있습니다.

AWS App Runner 배포 후에는 App Runner HTTPS URL을 넣습니다.

```bash
flutter run \
  --dart-define=API_BASE_URL=https://<app-runner-domain>/api/v1
```

Supabase URL과 publishable key는 공개 클라이언트 값이라 기본값을 넣어두었고, 필요하면 `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY` dart-define으로 덮어쓸 수 있습니다.

## OpenAI 호출 정책

- OpenAI API Key는 백엔드에만 존재합니다.
- 캐릭터마다 해당 캐릭터 전용 비공개 프롬프트/기억만 전달합니다.
- 타 캐릭터 비밀이나 미발견 증거는 전달하지 않습니다.
- 요청 타임아웃 기본값은 30초입니다.
- 응답 출력 상한은 기본 400 tokens입니다.
- OpenAI 일시 장애 시 게임 흐름을 보존하기 위해 fallback 대사를 사용합니다.

## API

- `GET /health`
- `GET /api/v1/stories`
- `GET /api/v1/sessions`
- `POST /api/v1/sessions`
- `GET /api/v1/sessions/{session_id}`
- `POST /api/v1/sessions/{session_id}/actions`
- `POST /api/v1/sessions/{session_id}/accuse`

행동 타입은 현재 `move`, `search`, `inspect`, `ask`, `present`를 지원합니다.

## 다음 개발 우선순위

1. NPC/탐정의 라운드 종료 자동 행동 및 `scripted_events` 처리
2. 증거 제시에 따른 인물별 스트레스/신뢰도 변화
3. 강해진 탐정의 독립 추리 및 범인 지목 로직 고도화
4. `llm_runs` 기록과 OpenAI 토큰/비용 추적
5. 스토리 커버 이미지, 효과음, 타이핑/대화 연출
6. 소셜 로그인 및 프로필 UI
