#!/usr/bin/env bash
# ============================================================
# Google Cloud Run 안전 배포 스크립트 (Secret Manager 완전 연동)
# ============================================================
set -euo pipefail

# 설정 변수
PROJECT_ID="${GCP_PROJECT_ID:-iceu-songpa15}"
REGION="${GCP_REGION:-asia-northeast3}"  # 서울 리전 (또는 us-central1)
SERVICE_NAME="gemini-chatbot"
SECRET_NAME="GEMINI_API_KEY"

echo "============================================================"
echo "🚀 [Cloud Run 배포 시작] 서비스명: ${SERVICE_NAME}"
echo "📍 GCP 프로젝트: ${PROJECT_ID} | 리전: ${REGION}"
echo "🔒 시크릿 연동: Secret Manager (${SECRET_NAME})"
echo "============================================================"

# 1. gcloud 프로젝트 설정 확인
gcloud config set project "${PROJECT_ID}"

# 2. 필수 GCP API 활성화 (Cloud Run, Cloud Build, Secret Manager, Artifact Registry)
echo "📦 [1/3] 필수 GCP API 활성화 상태 확인..."
gcloud services enable \
    run.googleapis.com \
    cloudbuild.googleapis.com \
    secretmanager.googleapis.com \
    artifactregistry.googleapis.com \
    --project="${PROJECT_ID}"

# 3. Cloud Run 서비스 계정에 Secret Manager 접근 권한 부여 (필요 시)
echo "🔐 [2/3] Cloud Run 서비스 계정 Secret 접근 권한 확인..."
PROJECT_NUMBER=$(gcloud projects describe "${PROJECT_ID}" --format="value(projectNumber)")
COMPUTE_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

gcloud secrets add-iam-policy-binding "${SECRET_NAME}" \
    --project="${PROJECT_ID}" \
    --member="serviceAccount:${COMPUTE_SA}" \
    --role="roles/secretmanager.secretAccessor" \
    --condition=None 2>/dev/null || true

# 4. 소스코드 기반 Cloud Build 및 Cloud Run 안전 배포
# (이미지 내부에 비밀키가 전혀 들어가지 않고, 런타임에 Secret Manager에서 안전하게 주입됨)
echo "🚀 [3/3] Cloud Run 빌드 및 안전 배포 실행..."
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
    --set-secrets="GEMINI_API_KEY=projects/${PROJECT_NUMBER}/secrets/${SECRET_NAME}:latest"

echo "============================================================"
echo "🎉 배포가 성공적으로 완료되었습니다!"
SERVICE_URL=$(gcloud run services describe "${SERVICE_NAME}" --platform=managed --region="${REGION}" --format="value(status.url)")
echo "🌐 접속 주소: ${SERVICE_URL}"
echo "============================================================"
