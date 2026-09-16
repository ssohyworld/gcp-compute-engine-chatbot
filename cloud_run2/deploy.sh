#!/usr/bin/env bash
# ============================================================
# Google Cloud Run 안전 배포 스크립트 (ADC 기반 인증)
#
# 🛡️ ADC 장점:
#   - API Key나 Secret Manager 주입(--set-secrets)이 불필요합니다.
#   - Cloud Run 인스턴스 서비스 계정의 IAM 역할(roles/aiplatform.user)로
#     메타데이터 서버를 통해 가장 안전하게 Vertex AI Gemini를 호출합니다.
# ============================================================
set -euo pipefail

# 설정 변수
PROJECT_ID="${GCP_PROJECT_ID:-iceu-songpa15}"
REGION="${GCP_REGION:-asia-northeast3}"  # Cloud Run 배포 리전 (서울)
LOCATION="${VERTEX_LOCATION:-global}"    # Vertex AI Gemini 모델 호출 위치 (global)
SERVICE_NAME="gemini-chatbot-adc"

echo "============================================================"
echo "🚀 [Cloud Run 배포 시작] 서비스명: ${SERVICE_NAME}"
echo "📍 GCP 프로젝트: ${PROJECT_ID} | 배포 리전: ${REGION}"
echo "🛡️  인증 방식: ADC (Application Default Credentials)"
echo "🤖 Vertex AI 위치: ${LOCATION}"
echo "============================================================"

# 1. gcloud 프로젝트 설정 확인
echo "⚙️  [1/4] gcloud 활성 프로젝트 설정..."
gcloud config set project "${PROJECT_ID}"

# 2. 필수 GCP API 활성화 (Cloud Run, Cloud Build, Vertex AI, Artifact Registry)
echo "📦 [2/4] 필수 GCP API 활성화 상태 확인..."
gcloud services enable \
    run.googleapis.com \
    cloudbuild.googleapis.com \
    aiplatform.googleapis.com \
    artifactregistry.googleapis.com \
    --project="${PROJECT_ID}"

# 3. Cloud Run 서비스 계정에 Vertex AI 사용자 권한(roles/aiplatform.user) 부여
echo "🔐 [3/4] Cloud Run 서비스 계정에 Vertex AI IAM 권한 확인 및 부여..."
PROJECT_NUMBER=$(gcloud projects describe "${PROJECT_ID}" --format="value(projectNumber)")
COMPUTE_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

echo "   -> 서비스 계정: ${COMPUTE_SA}"
echo "   -> 권한 부여: roles/aiplatform.user (Vertex AI User)"

gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${COMPUTE_SA}" \
    --role="roles/aiplatform.user" \
    --condition=None 2>/dev/null || true

# 4. 소스코드 기반 Cloud Build 및 Cloud Run 배포 (API Key / 시크릿 주입 불필요!)
echo "🚀 [4/4] Cloud Run 빌드 및 ADC 기반 안전 배포 실행..."
gcloud run deploy "${SERVICE_NAME}" \
    --source=. \
    --region="${REGION}" \
    --project="${PROJECT_ID}" \
    --platform=managed \
    --allow-unauthenticated \
    --port=8080 \
    --min-instances=0 \
    --max-instances=5 \
    --memory=512Mi \
    --cpu=1 \
    --set-env-vars="GOOGLE_CLOUD_PROJECT=${PROJECT_ID},GOOGLE_CLOUD_LOCATION=${LOCATION},GOOGLE_GENAI_USE_VERTEXAI=true"

echo "============================================================"
echo "🎉 ADC 기반 Cloud Run 배포가 성공적으로 완료되었습니다!"
SERVICE_URL=$(gcloud run services describe "${SERVICE_NAME}" --platform=managed --region="${REGION}" --format="value(status.url)")
echo "🌐 서비스 접속 URL: ${SERVICE_URL}"
echo "============================================================"
