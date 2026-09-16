#!/usr/bin/env bash

# Gemini 3.8 Flash & 3.7 Flash Web Chatbot 실행 스크립트
echo "============================================================"
echo "✨ Gemini Web Chatbot (Gemini 3.8 Flash / 3.7 Flash)"
echo "============================================================"

# 환경변수 확인
if [ -n "$GEMINI_API_KEY" ]; then
    echo "✅ 환경변수 GEMINI_API_KEY가 안전하게 설정되어 있습니다."
elif [ -n "$GOOGLE_API_KEY" ]; then
    echo "✅ 환경변수 GOOGLE_API_KEY가 안전하게 설정되어 있습니다."
else
    echo "⚠️  경고: GEMINI_API_KEY 또는 GOOGLE_API_KEY 환경변수가 설정되지 않았습니다."
    echo "   실행 전 'export GEMINI_API_KEY=your_key'를 입력해 주세요."
fi

PORT=${PORT:-8000}
echo "🌐 로컬 서버 주소: http://localhost:${PORT}"
echo "============================================================"

# 서버 실행
exec python3 -m uvicorn main:app --host 0.0.0.0 --port "$PORT" --reload
