# 어쩌다지식 AI 파이프라인

> **일상 속 숨겨진 지식을 AI가 자동으로 영상으로 만들어주는 파이프라인**

한국 유튜브 채널 **어쩌다지식**을 위한 완전 자동화 영상 제작 시스템입니다.
Claude AI로 스크립트를 생성하고, Google Cloud TTS로 나레이션을 합성하고,
Imagen 3로 일러스트를 만들어 완성된 영상을 유튜브에 업로드합니다.

---

## 파이프라인 구조

```
┌─────────────────────────────────────────────────────────────────┐
│                     어쩌다지식 AI Pipeline                        │
│                                                                   │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐  │
│  │  TOPIC   │───▶│  SCRIPT  │───▶│   TTS    │───▶│  IMAGE   │  │
│  │ 주제 선택  │    │스크립트 생성│    │ 나레이션  │    │일러스트 생성│  │
│  │topic_mgr │    │ Claude   │    │Google TTS│    │ Imagen 3 │  │
│  └──────────┘    └──────────┘    └──────────┘    └──────────┘  │
│                                                         │         │
│                                                         ▼         │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐  │
│  │ YOUTUBE  │◀───│  REVIEW  │◀───│ASSEMBLE  │◀───│  scenes  │  │
│  │ 유튜브 업로드│   │Telegram  │    │영상 조립   │    │audio+img │  │
│  │ YouTube  │    │ 승인/반려  │    │moviepy   │    │+ intro   │  │
│  │   API    │    │ Drive 저장│    │+ BGM+SRT │    │+ BGM     │  │
│  └──────────┘    └──────────┘    └──────────┘    └──────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 프로젝트 구조

```
어쩌다지식/
├── pipeline/
│   ├── main.py              # 메인 오케스트레이터 (CLI 진입점)
│   ├── topic_manager.py     # 주제 큐 관리
│   ├── script_generator.py  # Claude로 스크립트 생성
│   ├── tts_generator.py     # Google TTS 나레이션 합성
│   ├── image_generator.py   # Vertex AI Imagen 일러스트 생성
│   ├── video_assembler.py   # moviepy 영상 조립
│   ├── review_gate.py       # Telegram 리뷰 게이트 + Drive 업로드
│   └── youtube_uploader.py  # YouTube 업로드
├── config/
│   └── settings.yaml        # 채널 설정
├── data/
│   ├── topic_queue.json     # 주제 목록 (20개 시드 포함)
│   ├── pending_approvals.json  # 검토 대기 영상
│   ├── youtube_token.json   # YouTube OAuth 토큰 (자동 생성)
│   └── runs/                # 실행별 상태 저장
│       └── run_YYYYMMDD_*/
│           ├── audio/       # 씬별 MP3
│           ├── images/      # 씬별 JPG
│           ├── output_*.mp4 # 완성 영상
│           ├── *.srt        # 자막 파일
│           └── *.json       # 실행 상태
├── assets/
│   ├── intro.mp4            # 채널 인트로 (직접 준비)
│   └── bgm/
│       ├── calm/            # 심리학 BGM
│       ├── upbeat/          # 생활잡학 BGM
│       └── electronic/      # IT/테크 BGM
├── logs/
│   └── pipeline.log
├── .github/
│   └── workflows/
│       └── pipeline.yml     # GitHub Actions 자동화
├── requirements.txt
├── .env.example
└── README.md
```

---

## 설정 방법

### 1. 저장소 클론 및 의존성 설치

```bash
git clone <your-repo-url>
cd 어쩌다지식

# Python 3.11 권장
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

pip install -r requirements.txt
```

### 2. 시스템 패키지 설치

```bash
# Ubuntu/Debian
sudo apt-get install ffmpeg fonts-nanum

# macOS
brew install ffmpeg
```

### 3. 환경 변수 설정

```bash
cp .env.example .env
# .env 파일을 열어 각 값을 채워주세요
```

### 4. Google Cloud 프로젝트 설정

#### 4-1. GCP 프로젝트 생성
1. [GCP Console](https://console.cloud.google.com) 접속
2. 새 프로젝트 생성 또는 기존 프로젝트 선택

#### 4-2. API 활성화
다음 API를 활성화해야 합니다:
```
Cloud Text-to-Speech API
Vertex AI API
Google Drive API
YouTube Data API v3
```

GCP Console > API 및 서비스 > 라이브러리에서 검색하여 활성화하세요.

#### 4-3. 서비스 계정 생성 (TTS + Imagen + Drive용)
```
GCP Console > IAM 및 관리자 > 서비스 계정 > 새 서비스 계정 만들기

역할:
- Cloud Text-to-Speech API 사용자
- Vertex AI 사용자
- Google Drive API (파일 생성 권한)
```

서비스 계정 생성 후 JSON 키 다운로드:
```
서비스 계정 선택 > 키 > 키 추가 > JSON 다운로드
```

`.env`에 경로 설정:
```env
GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account-key.json
```

#### 4-4. YouTube OAuth2 설정

YouTube는 서비스 계정이 아닌 **OAuth2 사용자 인증**이 필요합니다:

```
GCP Console > API 및 서비스 > 사용자 인증 정보
> OAuth 2.0 클라이언트 ID 만들기
> 애플리케이션 유형: 데스크톱 앱
> JSON 다운로드
```

`.env`에 설정:
```env
YOUTUBE_CLIENT_SECRETS_FILE=/path/to/client_secrets.json
```

**첫 실행 시** 브라우저가 열리며 Google 계정 로그인을 요청합니다.
YouTube 채널 소유 계정으로 인증하면 토큰이 `data/youtube_token.json`에 저장됩니다.

### 5. Telegram 봇 설정

```
1. Telegram에서 @BotFather 검색
2. /newbot 명령 실행
3. 봇 이름과 username 입력
4. 발급된 Token을 TELEGRAM_BOT_TOKEN에 저장

5. 봇을 개인 채팅이나 그룹에 추가
6. https://api.telegram.org/bot{TOKEN}/getUpdates 접속
7. 응답에서 "chat": {"id": ...} 값을 TELEGRAM_CHAT_ID에 저장
```

### 6. 에셋 준비

`assets/` 폴더에 다음을 추가하세요 (자세한 내용은 [assets/README.md](assets/README.md) 참조):
- `assets/intro.mp4` — 채널 인트로 영상 (5~10초)
- `assets/bgm/calm/` — 심리학 영상용 BGM MP3
- `assets/bgm/upbeat/` — 생활잡학 영상용 BGM MP3
- `assets/bgm/electronic/` — IT/테크 영상용 BGM MP3

---

## 실행 방법

### 로컬 실행

```bash
# 가상환경 활성화
source venv/bin/activate

# 전체 파이프라인 실행 (주제 자동 선택)
python pipeline/main.py

# 특정 주제로 실행
python pipeline/main.py --topic-id topic_001

# 특정 단계부터 재개 (오류 복구 시)
python pipeline/main.py --skip-to tts --run-id run_20240101_120000_abc123

# 드라이런 (API 호출 없이 흐름 확인)
python pipeline/main.py --dry-run

# 도움말
python pipeline/main.py --help
```

### GitHub Actions 자동 실행

자동 실행: **월/수/금 오전 9시 KST** (0시 UTC)

수동 실행:
```
GitHub 저장소 > Actions 탭 > 어쩌다지식 AI 파이프라인 > Run workflow
```

---

## GitHub Actions Secrets 설정

저장소 Settings > Secrets and variables > Actions에 다음 시크릿을 추가하세요:

| 시크릿 이름 | 값 |
|------------|-----|
| `ANTHROPIC_API_KEY` | Anthropic API 키 |
| `GOOGLE_CLOUD_PROJECT` | GCP 프로젝트 ID |
| `GOOGLE_APPLICATION_CREDENTIALS_JSON` | 서비스 계정 JSON **전체 내용** (파일 경로 아님) |
| `GOOGLE_DRIVE_FOLDER_ID` | Drive 검토 폴더 ID |
| `TELEGRAM_BOT_TOKEN` | Telegram 봇 토큰 |
| `TELEGRAM_CHAT_ID` | Telegram 채팅 ID |
| `YOUTUBE_CLIENT_SECRETS_JSON` | OAuth2 클라이언트 시크릿 JSON **전체 내용** |

---

## 주제 관리

### 주제 목록 확인
```bash
python pipeline/topic_manager.py
```

### 새 주제 추가 (Python)
```python
from pipeline.topic_manager import TopicManager

tm = TopicManager()
tm.add_topic(
    title_idea="스마트폰 보면서 걷는 사람들의 심리 - 터널 시각이란?",
    category="psychology",  # psychology / life / tech
    keywords=["스마트폰", "터널시각", "주의", "안전", "보행"],
    hook="길에서 폰 보면서 걷다가 사람 부딪혀보신 적 있나요?",
    priority=5,  # 낮을수록 먼저 선택
)
```

---

## 비용 추정 (월)

| 서비스 | 사용량 (월 12영상 기준) | 예상 비용 |
|--------|----------------------|---------|
| Claude claude-opus-4-7 API | 스크립트 12회 × ~4000 토큰 | ~$2 |
| Google TTS Neural2 | ~12만 자 | ~$2 |
| Vertex AI Imagen 3 | 12영상 × 10씬 = 120회 | ~$3 |
| Google Drive API | 무료 (서비스 계정) | $0 |
| YouTube Data API | 무료 (일일 할당량 내) | $0 |
| **합계** | | **~$7/월** |

> Budget 한도($50/월) 내에서 충분히 운영 가능합니다.

---

## 리뷰 프로세스

1. 파이프라인이 영상 제작 완료 후 Google Drive에 업로드
2. Telegram으로 알림 발송 (제목, 카테고리, 드라이브 링크 포함)
3. 검토자가 드라이브에서 영상 시청
4. **✅ 승인** 버튼: YouTube에 자동 업로드
5. **❌ 반려** 버튼: 업로드 중단, 재작업 필요 (새 실행 필요)
6. 24시간 내 응답 없으면 타임아웃 — 수동 업로드 안내

---

## 문제 해결

### 자주 발생하는 오류

**TTS 실패**
```
인증 오류: GOOGLE_APPLICATION_CREDENTIALS 경로 확인
API 미활성: GCP Console에서 Text-to-Speech API 활성화
```

**Imagen 실패 (Safety filter)**
```
image_generator.py의 _sanitize_prompt() 가 자동 처리
Placeholder 이미지로 대체됩니다 (영상 제작은 계속됨)
```

**YouTube 업로드 실패 (Quota)**
```
YouTube Data API는 일일 할당량이 있습니다 (기본 10,000 유닛)
업로드 = 1,600 유닛 → 하루 약 6회 업로드 가능
GCP Console에서 할당량 증가 신청 가능
```

**파이프라인 중단 후 재개**
```bash
# 실행 ID 확인
ls data/runs/

# 특정 단계부터 재개
python pipeline/main.py --skip-to assemble --run-id run_20240101_120000_abc123
```

---

## 라이선스

이 프로젝트는 어쩌다지식 채널 전용으로 제작된 내부 도구입니다.
