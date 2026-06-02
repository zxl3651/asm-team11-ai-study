#!/bin/bash

echo "🎓 소마 메이트 (SoMa Mate) 시작"
echo "================================"

# 백엔드 의존성 확인
if ! command -v python3 &>/dev/null; then
  echo "❌ Python3가 설치되지 않았습니다."
  exit 1
fi

cd "$(dirname "$0")/backend" || exit 1

# .env 파일 확인
if [ ! -f .env ]; then
  if [ -f .env.example ]; then
    cp .env.example .env
    echo "⚠️  .env 파일이 없어 .env.example을 복사했습니다."
    echo "   ANTHROPIC_API_KEY를 .env에 설정해주세요."
    echo ""
  fi
fi

# 의존성 설치
if [ ! -d venv ]; then
  echo "📦 가상환경 생성 중..."
  python3 -m venv venv
fi

source venv/bin/activate
pip install -q -r requirements.txt

echo ""
echo "🚀 백엔드 서버 시작 (http://localhost:8000)"
echo "   크롬 확장 프로그램을 로드한 후 사용하세요."
echo "   종료: Ctrl+C"
echo ""

python main.py
