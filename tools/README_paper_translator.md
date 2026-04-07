# Paper Translator

PDF 논문을 Markdown으로 추출한 뒤 번역하여 HTML로 생성하는 도구입니다.

## 주요 구성

- `paper_translator.py`: CLI 번역 엔진
- `paper_translator_gui.py`: Tkinter GUI
- `setup.bat`: Windows 설치 스크립트
- `output/`: 번역 결과물 저장 폴더

## 동작 개요

1. marker-pdf로 PDF를 Markdown + 이미지로 추출
2. DeepL API로 우선 번역
3. DeepL 실패 시 Google fallback 경로 시도
4. 수식/코드/표를 보호한 뒤 HTML 생성
5. MathJax로 수식 렌더링

## 요구 사항

- Python 3.9+
- `pip install -r requirements.txt`

## API 키 설정

아래 둘 중 하나를 사용합니다.

### 1) 환경 변수

```bash
# Windows CMD
set DEEPL_API_KEY=your-api-key

# PowerShell
$env:DEEPL_API_KEY="your-api-key"

# Mac/Linux
export DEEPL_API_KEY="your-api-key"
```

### 2) 파일

프로젝트 루트 `deepl_key.txt`에 API 키를 1줄로 저장.

## CLI 사용법

```bash
python paper_translator.py <pdf파일> [출력.html] [방향]
```

- 방향: `auto`(기본), `en_to_ko`, `ko_to_en`

예시:

```bash
python paper_translator.py paper.pdf
python paper_translator.py paper.pdf output/paper_ko.html en_to_ko
```

## GUI 사용법

```bash
python paper_translator_gui.py
```

- 입력 PDF/출력 경로 선택
- `API 설정` 팝업에서 키 입력
- 필요 시 `deepl_key.txt` 저장
- 실행 로그 실시간 확인

## 출력 파일

- 기본 출력 폴더: `output/`
- 번역 HTML: `*_translated.html`
- 디버그 Markdown: `*_debug_processed.md` (디버그용)

## 문제 해결

### DeepL API 키가 없다는 오류

- `DEEPL_API_KEY` 또는 `deepl_key.txt`를 확인하세요.

### 번역이 느린 경우

- 첫 실행 시 marker 모델 다운로드/초기화 시간이 큽니다.
- 대형 PDF는 처리 시간이 오래 걸릴 수 있습니다.

### DeepL 쿼터 초과

- 코드가 fallback 경로를 시도하지만 품질/속도 차이가 있을 수 있습니다.

## 보안 주의

- `deepl_key.txt`는 Git에 업로드하지 마세요.
- 공개 저장소에서는 `.gitignore`로 제외하세요.
