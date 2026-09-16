# Gemini Web Chatbot (Cloud Run - ADC 인증 모드)

> **Google Cloud 권장 인증 방식(ADC - Application Default Credentials) 적용 버전**  
> Google Agent Platform 및 Vertex AI의 표준 보안 가이드라인에 따라 API Key나 Secret Manager 주입 없이, **환경의 기본 ID(Service Account / gcloud ADC)**를 통해 안전하게 Gemini 모델을 호출합니다.

---

## 📌 1. 기존 `cloud_run` vs `cloud_run2` 비교

| 항목 | 기존 `cloud_run` | 신규 `cloud_run2` (본 프로젝트) |
| :--- | :--- | :--- |
| **인증 방식** | `GEMINI_API_KEY` (Secret Manager 또는 환경변수) | **ADC (애플리케이션 기본 사용자 인증 정보)** |
| **보안 메커니즘** | Secret Manager에 시크릿 저장 및 `--set-secrets` 주입 필요 | **키리스(Keyless)**: 메타데이터 서버를 통한 IAM 기반 자동 인증 |
| **자격 증명 노출 위험** | API 키 유출 위험 존재 | **비밀키가 코드나 이미지, 설정에 전혀 존재하지 않음** |
| **로컬 개발 인증** | `.env` 파일에 발급받은 API 키 직접 입력 | `gcloud auth application-default login` 1회 실행 |
| **Cloud Run 배포** | Secret Manager 접근 권한 및 시크릿 볼륨 마운트 필요 | `roles/aiplatform.user` IAM 권한만 서비스 계정에 부여 |
| **백엔드 엔진** | Gemini Developer API | **Google Cloud Vertex AI (Agent Platform)** |

---

## 🚀 2. 빠른 시작 (로컬 실행)

### 사전 준비 (@capture 참고)
Google Cloud 공식 안내에 따라 로컬 환경에서 ADC 로그인을 완료합니다:

```bash
# 방법 1: Google Cloud SDK 기본 명령어로 ADC 로그인 (권장)
gcloud auth application-default login
gcloud auth application-default set-quota-project iceu-songpa15

# 방법 2: Google 공식 원라인 셋업 스크립트 실행 (capture.png 가이드)
bash <(curl -sSL https://storage.googleapis.com/cloud-samples-data/adc/setup_adc.sh)

# 방법 3: 동봉된 셋업 스크립트 실행
chmod +x setup_adc.sh
./setup_adc.sh
```

### 가상환경 및 패키지 설치
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 로컬 서버 실행
```bash
python3 server.py
# 또는
uvicorn main:app --host 0.0.0.0 --port 8080 --reload
```
웹 브라우저에서 `http://localhost:8080`으로 접속하면, 하단 상태창에 **`ADC (iceu-songpa15) 연결됨`** 상태가 표시되며 대화를 시작할 수 있습니다.

---

## ☁️ 3. Google Cloud Run 배포

### 배포 원리
1. Cloud Run 인스턴스가 생성되면 기본 Compute Engine 서비스 계정(`{PROJECT_NUMBER}-compute@developer.gserviceaccount.com`)이 부여됩니다.
2. 해당 서비스 계정에 `roles/aiplatform.user` (Vertex AI 사용자) 역할이 있으면 별도의 API 키 없이도 메타데이터 서버(`169.254.169.254`)를 통해 인증 토큰을 자동으로 발급받아 통신합니다.

### 원클릭 자동 배포 스크립트
```bash
chmod +x deploy.sh
./deploy.sh
```

### 수동 gcloud 배포 명령어
```bash
# 1. 필수 API 활성화
gcloud services enable run.googleapis.com cloudbuild.googleapis.com aiplatform.googleapis.com

# 2. 서비스 계정에 Vertex AI 권한 부여
PROJECT_ID=$(gcloud config get-value project)
PROJECT_NUMBER=$(gcloud projects describe ${PROJECT_ID} --format="value(projectNumber)")
COMPUTE_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${COMPUTE_SA}" \
    --role="roles/aiplatform.user"

# 3. Cloud Run 배포 (--set-secrets 필요 없음!)
gcloud run deploy gemini-chatbot-adc \
    --source=. \
    --region=asia-northeast3 \
    --platform=managed \
    --allow-unauthenticated \
    --port=8080 \
    --set-env-vars="GOOGLE_CLOUD_PROJECT=${PROJECT_ID},GOOGLE_CLOUD_LOCATION=global,GOOGLE_GENAI_USE_VERTEXAI=true"
```

---

## 📂 4. 프로젝트 구조

```
cloud_run2/
├── Dockerfile              # Cloud Run 최적화 경량 컨테이너 (비밀키 미포함)
├── deploy.sh               # ADC & IAM 기반 Cloud Run 원클릭 배포 스크립트
├── setup_adc.sh            # 로컬 개발자를 위한 ADC 환경 설정 스크립트
├── main.py                 # FastAPI 백엔드 (ADC/Vertex AI 자동 감지 및 SSE 스트리밍)
├── server.py               # Uvicorn 진입점
├── requirements.txt        # 핵심 의존성 패키지 목록
├── .dockerignore           # 컨테이너 빌드 제외 파일
├── .env.example            # 환경 변수 예시 가이드
├── README.md               # 서비스 문서
├── data/
│   └── sessions.json       # 사용자별 세션 영속 저장소
└── static/
    ├── index.html          # Gemini 스타일 반응형 웹 UI (ADC 상태 표시)
    ├── app.js              # 실시간 SSE 스트리밍 및 클라이언트 로직
    └── style.css           # 모던 글래스모피즘 디자인 시스템
```

---

## 🛠️ 5. API 명세

| Method | Endpoint | 설명 |
| :--- | :--- | :--- |
| `GET` | `/healthz`, `/api/health` | Liveness & Startup 헬스체크 (Cloud Run 프로브용) |
| `GET` | `/api/status` | ADC 인증 상태, 프로젝트 ID, IAM 주체 정보 반환 |
| `GET` | `/api/models` | 사용 가능한 최신 Gemini 모델 목록 (`gemini-3.8-flash` 등) |
| `POST` | `/api/chat/stream` | SSE 기반 실시간 답변 스트리밍 + Google Search 그라운딩 |
| `GET` | `/api/sessions` | 사용자별 대화 세션 목록 조회 |
| `POST` | `/api/sessions` | 대화 세션 생성 및 저장 |
| `DELETE`| `/api/sessions/{id}` | 특정 세션 삭제 |
