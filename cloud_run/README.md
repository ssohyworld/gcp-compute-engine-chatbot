# ☁️ GCP Cloud Run 기반 Gemini AI 챗봇 배포 가이드

Google Cloud Platform(GCP)의 완전 관리형 서버리스 컨테이너 플랫폼인 **Cloud Run**에 안전하게 배포된 **FastAPI 기반 Gemini 챗봇** 서비스입니다.

---

## 🔒 보안 아키텍처 및 무결점 설계 (Zero-Exposure Security)

본 프로젝트는 **보안 모범 사례(Security Best Practices)**를 철저히 준수하여 구축되었습니다:

1. **Docker 이미지 내 비밀정보 0% 격리**:
   - Dockerfile 빌드 단계에서 API 키, 프로젝트 시크릿 등 민감 정보를 일절 포함하지 않습니다.
   - `.dockerignore`를 통해 `.env`, Git 설정, 로컬 캐시 등의 유입을 원천 차단합니다.
2. **런타임 시크릿 다이렉트 마운팅 (`--set-secrets`)**:
   - 컨테이너가 배포되어 가동될 때, GCP Secret Manager (`projects/404380364167/secrets/GEMINI_API_KEY`)로부터 비공개 내부 네트워크를 통해 **컨테이너 메모리 상의 환경변수(`GEMINI_API_KEY`)로만 안전하게 주입**됩니다.
   - 디스크에 키를 쓰거나 이미지 레이어에 남기지 않습니다.
3. **IAM 최소 권한 원칙**:
   - 오직 Cloud Run 서비스 계정(`404380364167-compute@developer.gserviceaccount.com`)에만 Secret Accessor 권한을 부여합니다.

---

## 📁 디렉터리 구성

```
cloud_run/
├── main.py              # FastAPI 서버, SSE 스트리밍, Secret Manager 안전 로더
├── server.py            # Uvicorn 진입점
├── requirements.txt     # Python 패키지 의존성 (google-cloud-secret-manager 포함)
├── Dockerfile           # Cloud Run 최적화 경량 컨테이너 이미지
├── .dockerignore        # 보안 차단 규칙 (.env, .git, 민감파일 제외)
├── .env.example         # 로컬 테스트용 템플릿
├── deploy.sh            # Cloud Run 자동 빌드 & 배포 스크립트
├── static/              # 프론트엔드 UI (index.html, style.css, app.js)
└── data/                # 세션 데이터 저장소
```

---

## 🚀 배포 방법

### 방법 1. 자동 배포 스크립트 실행 (추천)

```bash
cd cloud_run
./deploy.sh
```

### 방법 2. gcloud 명령어로 직접 배포

```bash
cd cloud_run

gcloud run deploy gemini-chatbot \
    --source=. \
    --region=asia-northeast3 \
    --project=iceu-songpa15 \
    --platform=managed \
    --allow-unauthenticated \
    --port=8080 \
    --set-secrets="GEMINI_API_KEY=projects/404380364167/secrets/GEMINI_API_KEY:latest"
```

---

## 🧪 로컬 테스트 방법 (선택)

```bash
cd cloud_run
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
export GEMINI_API_KEY="your_api_key"
python3 main.py
```
브라우저에서 `http://localhost:8080` 접속
