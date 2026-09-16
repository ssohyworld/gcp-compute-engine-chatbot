# ============================================================
# Google Cloud Run 최적화 Dockerfile
# 보안 원칙: 이미지 내부에 API Key, 시크릿, 민감정보 절대 미포함
# ============================================================
FROM python:3.11-slim

# 파이썬 출력 버퍼링 비활성화 및 바이트코드 캐시 방지
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

# 작업 디렉터리 생성
WORKDIR /app

# 시스템 빌드 의존성 및 패키지 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 애플리케이션 코드 및 정적 리소스 복사
COPY . .

# 세션 데이터 저장 디렉터리 생성
RUN mkdir -p /app/data

# Cloud Run 기본 포트 개방
EXPOSE 8080

# Cloud Run 실행 커맨드 (환경변수 PORT를 수신하도록 쉘 형태로 실행)
CMD exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}
