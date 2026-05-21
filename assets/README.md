# assets/ — 어쩌다지식 채널 에셋 폴더

이 폴더에는 영상 제작에 필요한 고정 에셋들을 배치합니다.
아래 안내에 따라 파일을 준비해주세요.

---

## 폴더 구조

```
assets/
├── intro.mp4           ← 채널 인트로 클립 (필수 권장)
├── bgm/
│   ├── calm/           ← 심리학 영상용 배경음악 (잔잔한 분위기)
│   ├── upbeat/         ← 생활잡학 영상용 배경음악 (경쾌한 분위기)
│   └── electronic/     ← IT/테크 영상용 배경음악 (일렉트로닉 분위기)
└── README.md           ← 이 파일
```

---

## intro.mp4 — 채널 인트로 클립

### 사양
- **파일명**: `assets/intro.mp4` (고정)
- **길이**: 5~10초 권장
- **해상도**: 1920×1080 (Full HD 16:9)
- **형식**: MP4 (H.264 + AAC)

### 내용 가이드
- 채널명 "어쩌다지식" 로고 또는 텍스트 애니메이션
- 짧고 임팩트 있는 브랜딩
- 배경음악이나 효과음 포함 권장

### 제작 방법
- Adobe After Effects, CapCut, Canva 등 영상 편집 툴 활용
- 파이프라인이 자동으로 모든 영상 앞에 prepend 합니다
- 파일이 없으면 인트로 없이 영상이 시작됩니다 (오류 없음)

---

## bgm/ — 배경음악 라이브러리

배경음악은 파이프라인에서 주제 카테고리에 따라 자동 선택됩니다.

| 카테고리 | 폴더 | 분위기 | BPM 권장 |
|---------|------|--------|---------|
| 심리학 (psychology) | `bgm/calm/` | 차분하고 몽환적 | 60~90 |
| 생활잡학 (life) | `bgm/upbeat/` | 경쾌하고 활기찬 | 100~130 |
| IT/테크 (tech) | `bgm/electronic/` | 일렉트로닉/테크 | 110~140 |

### 파일 사양
- **형식**: MP3 또는 WAV
- **길이**: 2~5분 권장 (파이프라인이 자동으로 루프/트림)
- **인코딩**: 44.1kHz, 128kbps 이상 권장

### 저작권 무료 BGM 소스
아래 사이트에서 상업적 사용 가능한 무료 음원을 구할 수 있습니다:

- **YouTube Audio Library**: https://studio.youtube.com/channel/UC/music
  - YouTube 스튜디오 > 오디오 보관함
  - 필터: "귀속 없음" 선택

- **Pixabay Music**: https://pixabay.com/music/
  - 무료 상업 사용 가능

- **Free Music Archive**: https://freemusicarchive.org/
  - Creative Commons 라이선스 확인 필수

- **Bensound**: https://www.bensound.com/
  - 유튜브 채널 등록 후 무료 사용 가능

### bgm/calm/ 추천 검색어
- "ambient calm piano", "lofi chill", "soft background music",
  "peaceful instrumental", "meditation background"

### bgm/upbeat/ 추천 검색어
- "upbeat background music", "happy corporate", "fun pop instrumental",
  "cheerful background", "positive energy music"

### bgm/electronic/ 추천 검색어
- "electronic technology background", "futuristic music",
  "tech corporate", "digital innovation music", "cyber background"

---

## 주의사항

1. **저작권**: 반드시 상업적 사용 허가된 음원만 사용하세요
2. **파일명**: 한글, 공백, 특수문자 없이 영문/숫자/하이픈만 사용 권장
   - 예: `calm-piano-01.mp3`, `upbeat-pop-loop.mp3`
3. **볼륨**: 파이프라인에서 BGM을 자동으로 15% 볼륨으로 낮춥니다
4. **최소 파일 수**: 각 폴더에 최소 1개 이상 있어야 BGM이 적용됩니다
   - 여러 개 있으면 랜덤 선택됩니다 (다양성!)

---

## 예시 파일 목록

```
assets/
├── intro.mp4
├── bgm/
│   ├── calm/
│   │   ├── calm-piano-01.mp3
│   │   ├── lofi-chill-02.mp3
│   │   └── ambient-relax-03.mp3
│   ├── upbeat/
│   │   ├── happy-pop-01.mp3
│   │   ├── cheerful-corporate-02.mp3
│   │   └── fun-background-03.mp3
│   └── electronic/
│       ├── tech-electronic-01.mp3
│       ├── futuristic-corporate-02.mp3
│       └── digital-beat-03.mp3
└── README.md
```
