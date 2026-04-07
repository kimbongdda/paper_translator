@echo off
REM Paper Translator Setup Script for Windows

echo.
echo ========================================
echo Paper Translator 설치 스크립트
echo ========================================
echo.

REM Python 버전 확인
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python이 설치되어 있지 않습니다!
    echo. 
    echo https://www.python.org/downloads/ 에서 Python 3.8 이상을 설치해주세요.
    pause
    exit /b 1
)

echo ✅ Python이 설치되어 있습니다.
python --version
echo.

REM 필수 패키지 설치
echo 📦 필수 패키지를 설치하겠습니다...
pip install -r requirements.txt

if errorlevel 1 (
    echo ❌ 패키지 설치를 실패했습니다!
    pause
    exit /b 1
)

echo ✅ 패키지 설치가 완료되었습니다!
echo.

REM DeepL API KEY 설정 안내
echo ⚙️  DeepL API 키를 설정해야 합니다.
echo.
echo 1. https://www.deepl.com/pro-api 접속
echo 2. API 키 발급 후 아래 방법 중 하나로 설정:
echo.
echo    set DEEPL_API_KEY=your-api-key-here
echo.
echo    또는 deepl_key.txt 파일에 API 키 1줄 저장
echo.
echo (GUI에서도 API 키 입력 및 저장이 가능합니다)
echo.
echo ========================================
echo 설치 완료!
echo.
echo 📖 사용법:
echo    python paper_translator.py input.pdf output.html
echo.
echo 🖥️ GUI 실행:
echo    python paper_translator_gui.py
echo.
echo 자세한 정보는 tools\\README_paper_translator.md를 참고하세요.
echo ========================================
echo.
pause
