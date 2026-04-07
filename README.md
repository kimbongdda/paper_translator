# Paper Translator (PDF -> Translated HTML)

논문 PDF를 읽어 번역하고, 수식을 유지한 HTML 결과를 생성하는 도구입니다.

## Features

- marker-pdf 기반 PDF 구조 추출
- DeepL 우선 번역 + fallback 경로
- 수식/코드/표 보호 처리
- MathJax 렌더링 HTML 생성
- GUI 지원 (`paper_translator_gui.py`)

## Quick Start

1. 설치

```bash
pip install -r requirements.txt
```

2. API 키 설정

```bash
# Windows PowerShell
$env:DEEPL_API_KEY="your-api-key"
```

또는 루트에 `deepl_key.txt` 생성 후 키 1줄 입력.

3. 실행

```bash
python paper_translator.py input.pdf
python paper_translator_gui.py
```

## CLI

```bash
python paper_translator.py <pdf파일> [출력.html] [방향]
```

- 방향: `auto`, `en_to_ko`, `ko_to_en`

## GUI

- `API 설정` 버튼으로 별도 팝업에서 키 입력/저장
- 실행 로그 및 상태 표시
- 출력 폴더/출력 HTML 바로 열기

## Output

- 기본 출력 폴더: `output/`
- 번역 결과: `*_translated.html`

## Security

- `deepl_key.txt`는 절대 공개 저장소에 올리지 마세요.
- `.gitignore`에서 제외하도록 설정되어 있습니다.

## Docs

- 빠른 시작: `tools/QUICK_START_KO.md`
- 상세 문서: `tools/README_paper_translator.md`

## License

- 이 프로젝트 코드는 MIT License로 배포됩니다.
- 자세한 내용은 `LICENSE` 파일을 참고하세요.
- 외부 의존 라이브러리는 각 라이브러리의 개별 라이선스를 따릅니다.
