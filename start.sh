#!/bin/bash

echo "🎓 소마 메이트 (SoMa Mate) 시작"
echo "================================"

# 호환되는 파이썬 버전 탐색 (3.9 ~ 3.13)
PYTHON_BIN=""
for cmd in python3.12 python3.11 python3.10 python3.13 python3; do
  if command -v "$cmd" &>/dev/null; then
    # 버전을 체크하여 3.14 미만인지 확인
    py_ver=$("$cmd" -c 'import sys; print(sys.version_info.minor)')
    if [ "$py_ver" -lt 14 ]; then
      PYTHON_BIN="$cmd"
      break
    fi
  fi
done

if [ -z "$PYTHON_BIN" ]; then
  echo "❌ 호환되는 Python3 버전(3.9 ~ 3.13)을 찾을 수 없습니다."
  echo "   현재 시스템에 설치된 python3는 3.14 이상으로 pydantic-core 빌드를 지원하지 않습니다."
  exit 1
fi

echo "🐍 사용 중인 파이썬: $($PYTHON_BIN --version) ($PYTHON_BIN)"

cd "$(dirname "$0")/backend" || exit 1

# .env 파일 확인
if [ ! -f .env ]; then
  if [ -f .env.example ]; then
    cp .env.example .env
    echo "⚠️  .env 파일이 없어 .env.example을 복사했습니다."
    echo "   UPSTAGE_API_KEY를 .env에 설정해주세요."
    echo ""
  fi
fi

# 의존성 설치
if [ ! -d venv ]; then
  echo "📦 가상환경 생성 중..."
  $PYTHON_BIN -m venv venv
fi

source venv/bin/activate
pip install -q -r requirements.txt

echo ""
echo "🚀 백엔드 서버 시작 (http://localhost:8000)"
echo "   크롬 확장 프로그램을 로드한 후 사용하세요."
echo "   종료: Ctrl+C"
echo ""

python main.py

