# Colab 노트북 사용 가이드

GPT-SoVITS 목소리 클로닝 + Wan2.1 AI 영상 생성을 위한 Google Colab 설정 및 실행 가이드입니다.

---

## 1. Google Drive 폴더 구조 설정

### 폴더 생성

Google Drive에서 아래 구조로 폴더를 만드세요:

```
MyDrive/
└── 어쩌다지식/
    ├── voice_sample.wav          ← 본인 목소리 샘플 (필수)
    ├── gpt_sovits_model/         ← 학습 완료 후 모델 저장 위치
    └── runs/                     ← main.py가 자동 생성 (수동 생성 불필요)
```

### voice_sample.wav 업로드 방법

1. **녹음**: 조용한 환경에서 본인 목소리로 1~5분 분량 녹음
   - 내용: 책, 뉴스 기사, 대본 등 자연스러운 문장을 읽으세요
   - 형식: WAV 또는 MP3 (44100Hz, 모노/스테레오 모두 가능)
   - 잡음 없이 깨끗한 음질일수록 클로닝 품질이 높아집니다
2. **업로드**: Google Drive → `어쩌다지식/` 폴더에 `voice_sample.wav` 이름으로 업로드

---

## 2. 처음 사용할 때 (모델 학습)

GPT-SoVITS를 처음 사용한다면 본인 목소리 모델을 먼저 학습해야 합니다.

### 학습 단계

1. **Notebook 01 열기**: `colab/01_gpt_sovits_tts.ipynb`를 Colab에서 열기
2. **설정 변경**:
   ```python
   USE_PRETRAINED = False   # 처음 학습 시 False로 설정
   ```
3. **셀 5 실행**: ASR(자동 음성 인식) 전처리 시작
4. **GPT-SoVITS 공식 가이드 참조**: 전처리 완료 후 학습은 GPT-SoVITS 공식 문서에 따라 진행
   - 학습 완료 후 생성된 모델 파일:
     - `gpt_weights.ckpt`
     - `sovits_weights.pth`
5. **모델 저장**: 생성된 파일을 Drive의 `어쩌다지식/gpt_sovits_model/` 폴더에 저장
6. **다음 실행부터는** `USE_PRETRAINED = True`로 변경하면 학습 없이 바로 사용 가능

---

## 3. 매번 사용할 때 (영상 생성)

파이프라인이 실행되면 Colab 노트북을 순서대로 실행합니다.

### 전체 워크플로우

```
1. 로컬 터미널에서 실행:
   python pipeline/main.py

   → topic 선택 → script 생성 → TTS(ClovaVoice) → 이미지 생성 완료

   출력 예시:
   ============================================================
   🎬 Colab 처리 단계 (선택사항)
   ============================================================
   Run ID: run_20240522_143000_a1b2c3
   이미지 8개 생성 완료

   더 높은 품질을 원하면 Colab 노트북 실행:
     1. colab/01_gpt_sovits_tts.ipynb → 목소리 클로닝 TTS
     2. colab/02_wan21_video.ipynb    → AI 영상 클립 생성
   ============================================================

2. Notebook 01 실행 (TTS):
   - colab/01_gpt_sovits_tts.ipynb를 Colab에서 열기
   - RUN_ID = "run_20240522_143000_a1b2c3"  ← main.py 출력 값 입력
   - 셀을 위에서부터 순서대로 모두 실행
   - 완료 시 Drive에 audio/ 폴더가 생성됨

3. Notebook 02 실행 (영상):
   - colab/02_wan21_video.ipynb를 Colab에서 열기
   - RUN_ID = "run_20240522_143000_a1b2c3"  ← 동일한 run_id 입력
   - 셀을 위에서부터 순서대로 모두 실행
   - 완료 시 Drive에 video_clips/ 폴더가 생성됨

4. 로컬에서 조합 및 완성:
   python pipeline/main.py --skip-to assemble --run-id run_20240522_143000_a1b2c3
```

> **팁**: Notebook 02는 선택사항입니다. Notebook 01만 실행하고 바로 assemble 단계로
> 진행해도 됩니다. Wan2.1 클립이 없는 씬은 자동으로 Ken Burns 효과로 대체됩니다.

---

## 4. GPU 선택 가이드

### Colab 무료 (T4 GPU)

- **Wan2.1 모델**: 1.3B (소형 모델 자동 선택)
- **품질**: 보통 — 간단한 움직임, 약간 흐릿할 수 있음
- **속도**: 씬당 약 3~5분
- **제한**: 세션이 90분~12시간 후 자동 종료될 수 있음
- **권장 설정**: `KEY_SCENES_ONLY = True`로 핵심 씬만 처리

### Colab Pro ($10/월, 권장)

- **Wan2.1 모델**: 14B (고품질 모델 자동 선택)
- **GPU**: L4 또는 A100 (설정에서 선택 가능)
- **품질**: 높음 — 자연스러운 움직임, 선명한 영상
- **속도**: 씬당 약 1~2분 (A100 기준)
- **장점**: 세션 끊김 거의 없음, 더 큰 VRAM으로 안정적 실행

### GPU 수동 선택 방법 (Colab Pro)

Colab 상단 메뉴 → 런타임 → 런타임 유형 변경 → GPU → A100 선택

---

## 5. 비용 예상

| 옵션 | 비용 | Wan2.1 모델 | 권장 여부 |
|------|------|-------------|-----------|
| Colab 무료 | $0 | 1.3B | 테스트용 |
| Colab Pro | $10/월 | 14B | 추천 |
| Colab Pro+ | $50/월 | 14B | 전문가용 |

- **Colab Pro ($10/월)** 이면 14B 고품질 모델로 영상 클립을 빠르게 생성할 수 있어 추천합니다.
- **무료 Colab**도 가능하지만 세션이 중간에 끊길 수 있으며 1.3B 모델 품질에 한계가 있습니다.
- GPT-SoVITS TTS(Notebook 01)는 T4에서도 빠르게 실행되므로 무료 Colab으로 충분합니다.

---

## 트러블슈팅

**Q: "Run state not found" 오류가 발생합니다.**
- `main.py`를 먼저 로컬에서 실행해 run_id를 생성하세요.
- Drive의 `어쩌다지식/runs/` 폴더에 `{run_id}.json` 파일이 있는지 확인하세요.
- 로컬의 `data/runs/{run_id}.json`을 Drive에 수동으로 복사해도 됩니다.

**Q: 이미지 디렉토리가 비어 있습니다 (Notebook 02).**
- 로컬의 `data/runs/{run_id}/images/` 폴더를 Drive의 `어쩌다지식/runs/{run_id}/images/`로 복사하세요.

**Q: Colab 세션이 끊겼습니다.**
- 이미 생성된 파일은 Drive에 저장되어 있으므로 노트북을 재실행하면 캐시로 건너뜁니다.
- `out_path.exists()` 체크로 이미 완료된 씬은 자동 스킵됩니다.

**Q: GPT-SoVITS 모델이 없습니다 (USE_PRETRAINED=True인데 파일 없음).**
- `USE_PRETRAINED = False`로 변경하고 목소리 학습을 먼저 진행하세요.
- 학습 완료 후 모델을 Drive에 저장하고 다시 `USE_PRETRAINED = True`로 설정하세요.
