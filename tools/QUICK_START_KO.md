# Paper Translator 빠른 시작

## 1. 설치

### Windows
```bat
setup.bat
```

### Mac/Linux
```bash
pip install -r requirements.txt
```

## 2. DeepL API 키 준비

아래 둘 중 하나만 설정하면 됩니다.

### 방법 A: 환경 변수
```bash
# Windows CMD
set DEEPL_API_KEY=your-api-key-here

# PowerShell
$env:DEEPL_API_KEY="your-api-key-here"

# Mac/Linux
export DEEPL_API_KEY="your-api-key-here"
```

### 방법 B: 파일 저장
프로젝트 루트에 `deepl_key.txt` 파일을 만들고 API 키를 한 줄로 저장합니다.

## 3. 실행

### CLI
```bash
# 자동 방향
python paper_translator.py input.pdf

# 출력 파일 지정
python paper_translator.py input.pdf output/result.html

# 번역 방향 지정
python paper_translator.py input.pdf output/result.html en_to_ko
python paper_translator.py input.pdf output/result.html ko_to_en
```

### GUI
```bash
python paper_translator_gui.py
```

GUI에서는 `API 설정` 버튼으로 별도 팝업에서 키를 입력/저장할 수 있습니다.

## 4. 출력 확인

- 기본 출력 폴더: `output/`
- 번역 결과: `*_translated.html`
- 브라우저에서 HTML을 열어 확인합니다.

## 5. 자주 발생하는 문제

### API 키 오류
- 메시지: DeepL API 키가 없다는 오류
- 해결: `DEEPL_API_KEY`를 설정하거나 `deepl_key.txt`를 생성

### PDF 파싱 속도 지연
- 첫 실행에서 marker 모델 다운로드로 시간이 오래 걸릴 수 있습니다.

### 번역 실패 또는 느림
- DeepL 쿼터 초과 시 코드가 Google fallback 경로를 시도합니다.
- 네트워크 상태를 확인하세요.

## 6. 배포 전 체크

- `deepl_key.txt`를 Git에 올리지 않기
- `.venv/`, 캐시, 디버그 산출물 제외
- README와 사용법 문서 최신화
