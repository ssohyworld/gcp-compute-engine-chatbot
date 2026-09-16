#!/usr/bin/env bash
# ============================================================
# Google Cloud ADC (애플리케이션 기본 사용자 인증 정보) 설정 스크립트
#
# 참고: capture.png (Google Agent Platform 공식 안내)
# "bash <(curl -sSL https://storage.googleapis.com/cloud-samples-data/adc/setup_adc.sh)"
# ============================================================
set -euo pipefail

PROJECT_ID="${GCP_PROJECT_ID:-iceu-songpa15}"

echo "============================================================"
echo "🛡️  Google Cloud ADC (Application Default Credentials) 설정"
echo "📍 대상 GCP 프로젝트 ID: ${PROJECT_ID}"
echo "============================================================"

# 1. gcloud 설치 확인
if ! command -v gcloud >/dev/null 2>&1; then
    echo "❌ gcloud CLI가 설치되어 있지 않습니다."
    echo "Google Cloud SDK를 먼저 설치해 주세요: https://cloud.google.com/sdk/docs/install"
    exit 1
fi

# 2. gcloud 기본 프로젝트 설정
echo "⚙️  [1/4] gcloud 기본 프로젝트를 '${PROJECT_ID}'(으)로 설정합니다..."
gcloud config set project "${PROJECT_ID}"

# 3. ADC 로그인 수행
echo ""
echo "🔑 [2/4] ADC(애플리케이션 기본 사용자 인증 정보) 로그인을 진행합니다..."
echo "웹 브라우저가 열리면 Google Cloud 계정으로 로그인해 주세요."
gcloud auth application-default login

# 4. Quota 프로젝트 설정
echo ""
echo "🏷️  [3/4] 할당량 프로젝트(Quota Project)를 설정합니다..."
gcloud auth application-default set-quota-project "${PROJECT_ID}"

# 5. 필수 API 활성화 (Vertex AI API)
echo ""
echo "🔌 [4/4] Vertex AI API (aiplatform.googleapis.com) 활성화 확인..."
gcloud services enable aiplatform.googleapis.com --project="${PROJECT_ID}"

echo ""
echo "============================================================"
echo "🎉 ADC 인증 설정이 성공적으로 완료되었습니다!"
echo "📁 자격증명 저장 위치: ~/.config/gcloud/application_default_credentials.json"
echo "🚀 이제 API 키 없이 'python3 main.py' 또는 'uvicorn main:app'을 실행할 수 있습니다."
echo "============================================================"
