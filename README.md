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

## 운영 구조

```text
Flutter
  ├─ Supabase Auth
  └─ HTTP/HTTPS
       ↓
AWS EC2
  ├─ Nginx :80/:443
  └─ Docker
      └─ FastAPI :8000 (localhost only)
          ├─ Supabase PostgreSQL
          └─ OpenAI Responses API
```

Flutter는 `game_private`를 직접 읽지 않습니다. 게임의 비밀 설정, 캐릭터 프롬프트, 정답과 OpenAI API Key는 FastAPI 서버만 접근합니다.

모바일은 Supabase 로그인 토큰을 `Authorization: Bearer ...`로 백엔드에 전달하고, 백엔드는 Supabase Auth에서 토큰을 검증한 뒤 모든 세션 접근에 `user_id` 소유권 조건을 적용합니다.

## 1. 로컬 Backend 실행

```bash
cd backend
cp .env.example .env

# DATABASE_URL / OPENAI_API_KEY 입력

python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

확인:

```bash
curl http://localhost:8000/health
```

OpenAI 키가 정상 주입되어 있으면 `openai_configured: true`가 표시됩니다.

## 2. AWS EC2 배포

권장 MVP 구성:

- Amazon Linux 2023
- 작은 burstable EC2 인스턴스
- gp3 EBS
- Security Group
  - TCP 80: 인터넷 공개
  - TCP 443: 인터넷 공개
  - TCP 22: 필요할 때만 본인 IP /32
- 가능하면 SSH 대신 AWS Systems Manager Session Manager 사용
- FastAPI 8000 포트는 외부에 공개하지 않음

### 서버 최초 세팅

EC2에 접속한 뒤:

```bash
git clone https://github.com/ohhamin/Alibi.git
cd Alibi

bash deploy/ec2/bootstrap-amazon-linux.sh
```

bootstrap 스크립트가 다음을 설치/설정합니다.

- Git
- Docker
- Docker Compose
- Nginx
- 저장소 최신 `master`
- Nginx → `127.0.0.1:8000` reverse proxy
- `backend/.env.production` 템플릿 생성

### 운영 비밀값 입력

```bash
cd ~/Alibi
nano backend/.env.production
```

필수:

```env
DATABASE_URL=postgresql://...
OPENAI_API_KEY=sk-...
```

`backend/.env.production`은 Git에 커밋되지 않습니다.

### Backend 시작

```bash
cd ~/Alibi
docker compose -f docker-compose.prod.yml up -d --build
```

또는 이후 배포부터:

```bash
bash deploy/ec2/deploy.sh
```

상태 확인:

```bash
docker compose -f docker-compose.prod.yml ps
curl http://127.0.0.1:8000/health
curl http://localhost/health
```

예상 응답:

```json
{
  "status": "ok",
  "environment": "production",
  "openai_configured": true
}
```

로그:

```bash
docker compose -f docker-compose.prod.yml logs -f backend
```

## 3. Nginx

기본 설정:

`deploy/nginx/alibi.conf`

현재는 EC2 Public IP로 바로 테스트할 수 있도록 `server_name _;` 입니다.

도메인을 연결하면:

```nginx
server_name api.example.com;
```

형태로 바꾸고 HTTPS 인증서를 연결하면 됩니다.

FastAPI의 8000 포트는 Docker가 `127.0.0.1:8000`에만 바인딩하므로 인터넷에서 직접 접근할 수 없습니다.

## 4. Flutter 연결

로컬 개발:

```bash
flutter run \
  --dart-define=API_BASE_URL=http://10.0.2.2:8000/api/v1
```

EC2 Public IP 테스트:

```bash
flutter run \
  --dart-define=API_BASE_URL=http://<EC2_PUBLIC_IP>/api/v1
```

도메인 + HTTPS 적용 후:

```bash
flutter run \
  --dart-define=API_BASE_URL=https://api.example.com/api/v1
```

최종 앱 배포에서는 HTTPS를 사용합니다.

## OpenAI 호출 정책

- OpenAI API Key는 백엔드에만 존재
- 캐릭터별 격리된 비공개 프롬프트/기억만 전달
- 타 캐릭터 비밀이나 미발견 증거는 전달하지 않음
- timeout 기본 30초
- 최대 출력 400 tokens
- OpenAI 일시 장애 시 deterministic fallback 대사 사용

환경 변수:

```env
OPENAI_API_KEY=
OPENAI_MODEL=gpt-5.6-luna
OPENAI_TIMEOUT_SECONDS=30
OPENAI_MAX_OUTPUT_TOKENS=400
```

## API

- `GET /health`
- `GET /api/v1/stories`
- `GET /api/v1/sessions`
- `POST /api/v1/sessions`
- `GET /api/v1/sessions/{session_id}`
- `POST /api/v1/sessions/{session_id}/actions`
- `POST /api/v1/sessions/{session_id}/accuse`

행동 타입은 현재 `move`, `search`, `inspect`, `ask`, `present`를 지원합니다.

## 배포 관련 파일

```text
docker-compose.prod.yml
backend/.env.production.example
deploy/
├─ ec2/
│  ├─ bootstrap-amazon-linux.sh
│  └─ deploy.sh
└─ nginx/
   └─ alibi.conf
```

## 다음 개발 우선순위

1. EC2 실제 인스턴스 배포 + 도메인/HTTPS
2. NPC/탐정의 라운드 종료 자동 행동 및 `scripted_events`
3. 증거 제시에 따른 인물별 스트레스/신뢰도 변화
4. 강해진 탐정의 독립 추리 및 범인 지목
5. `llm_runs` 및 OpenAI 토큰/비용 추적
6. 스토리 커버 이미지, 효과음, 타이핑/대화 연출
