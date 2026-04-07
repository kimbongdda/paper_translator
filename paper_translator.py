"""
논문 번역 프로그램 v2 - marker-pdf 기반
- PDF 파싱: marker-pdf (레이아웃 AI — 수식/표/그림/의사코드 위치 그대로 추출)
- 번역: DeepL API (월 50만자 무료, pip install deepl)
- 수식 렌더링: MathJax (LaTeX 그대로 HTML에 삽입)
- 이미지: marker가 추출한 그림 base64 인라인 삽입

사용법:
  python paper_translator.py paper.pdf
  python paper_translator.py paper.pdf output.html
  DEEPL_API_KEY=xxxxxxx python paper_translator.py paper.pdf
"""

import re
import sys
import io
import base64
import time
import os
from pathlib import Path

import PIL.Image

OUTPUT_DIR = Path(__file__).parent / "output"

# DeepL API 키 로드 (우선순위: 환경변수 > deepl_key.txt)
def _load_deepl_key() -> str:
    key = os.environ.get("DEEPL_API_KEY", "").strip()
    if key:
        return key
    key_file = Path(__file__).parent / "deepl_key.txt"
    if key_file.exists():
        key = key_file.read_text(encoding="utf-8").strip()
        if key:
            return key
    raise RuntimeError(
        "DeepL API 키가 없습니다.\n"
        "  방법1: deepl_key.txt 파일에 키 입력\n"
        "  방법2: DEEPL_API_KEY 환경변수 설정"
    )


class PaperTranslator:

    # ─────────────────────────────────────────
    # marker 모델 로드 (버전 자동 감지)
    # ─────────────────────────────────────────
    def _load_marker(self):
        import torch
        device = "cuda" if torch.cuda.is_available() else "cpu"
        if device == "cuda":
            print(f"  GPU 사용: {torch.cuda.get_device_name(0)}")
        else:
            print("  CPU 사용 (GPU 미감지 - CUDA PyTorch 설치 시 빨라짐)")

        try:
            # marker >= 1.0 API
            from marker.converters.pdf import PdfConverter
            from marker.models import create_model_dict
            print("  marker 1.x 감지")
            self._marker_ver = 2
            self._converter = PdfConverter(artifact_dict=create_model_dict(device=device))
        except (ImportError, AttributeError):
            # marker 0.x API
            import os
            os.environ.setdefault("TORCH_DEVICE", device)
            from marker.models import load_all_models
            print("  marker 0.x 감지")
            self._marker_ver = 1
            self._marker_models = load_all_models()

    def _prepare_paths(self, input_path: str, output_html: str = None) -> tuple[Path, Path]:
        input_path = Path(input_path)
        if not input_path.exists():
            raise FileNotFoundError(f"PDF를 찾을 수 없습니다: {input_path}")

        if output_html is None:
            OUTPUT_DIR.mkdir(exist_ok=True)
            output_html = OUTPUT_DIR / (input_path.stem + "_translated.html")

        output_path = Path(output_html)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        return input_path, output_path

    def _load_translator(self) -> None:
        import deepl as _deepl
        self._deepl_translator = _deepl.Translator(_load_deepl_key())

    def _extract_document(self, input_path: Path) -> tuple[str, dict]:
        print("[2/4] PDF 파싱 중... (수식/표/그림/의사코드 추출)")
        t_parse = time.perf_counter()
        raw_md, images = self._run_marker(str(input_path))
        raw_md = self._clean_ocr_artifacts(raw_md)
        # marker-pdf 내부 앵커/외부 링크 제거 → 링크 텍스트만 남김
        # (?<!!) 로 이미지 링크 ![...](...) 는 제외
        _link_pat = re.compile(r'(?<!!)\[((?:[^\[\]]|\[[^\[\]]*\])*)\]\([^\)]*\)')
        for _ in range(4):  # 중첩이 깊을 경우 반복
            raw_md = _link_pat.sub(r'\1', raw_md)
        raw_md = self._normalize_markdown_escapes(raw_md)
        print(f"  추출 완료 - 이미지 {len(images)}개, 텍스트 {len(raw_md):,}자")
        print(f"  PDF 파싱 시간: {time.perf_counter() - t_parse:.1f}초")
        return raw_md, images

    def _determine_direction(self, raw_md: str, direction: str) -> tuple[str, str]:
        detected = self._detect_lang(raw_md[:3000])
        if direction == 'auto':
            direction = 'en_to_ko' if detected == 'en' else 'ko_to_en'
        src, tgt = direction.split('_to_')
        return src, tgt

    def _save_debug_markdown(self, output_html: Path, raw_md: str) -> Path:
        debug_path = output_html.parent / (output_html.stem.replace('_translated','') + '_debug_processed.md')
        debug_path.write_text(raw_md, encoding='utf-8')
        print(f"  [디버그] 전처리 완료 마크다운 저장: {debug_path.name}")
        return debug_path

    def _render_document(self, raw_md: str, src: str, tgt: str, images: dict) -> str:
        print(f"[3/4] 번역 중... {src.upper()} -> {tgt.upper()}")
        t_trans = time.perf_counter()
        translated_md = self._protect_and_translate(raw_md, src, tgt)
        print(f"  번역 시간: {time.perf_counter() - t_trans:.1f}초")

        print("[4/4] HTML 생성 중...")
        t_html = time.perf_counter()
        final_md = self._embed_images(translated_md, images)
        final_md = self._postprocess_md(final_md)
        body_html = self._md_to_html(final_md)
        # HTML 후처리: 수식 스팬/블록 바깥에 남은 달러 기호만 제거
        body_html = re.sub(
            r'\$+\s*(<(?:span|div) class="arithmatex">[\s\S]*?</(?:span|div)>)\s*\$+',
            r'\1',
            body_html,
        )
        print(f"  HTML 생성 시간: {time.perf_counter() - t_html:.1f}초")
        return body_html

    def _run_marker(self, pdf_path: str):
        """PDF → (markdown_str, images_dict)"""
        if self._marker_ver == 2:
            from marker.output import text_from_rendered
            rendered = self._converter(pdf_path)
            text, _, images = text_from_rendered(rendered)
            return text, images
        else:
            from marker.convert import convert_single_pdf
            text, images, _ = convert_single_pdf(
                pdf_path, self._marker_models, langs=["English"]
            )
            return text, images

    # ─────────────────────────────────────────
    # 언어 감지
    # ─────────────────────────────────────────
    def _detect_lang(self, text: str) -> str:
        korean = len(re.findall(r'[가-힣]', text))
        total  = len(re.findall(r'[a-zA-Z가-힣]', text))
        return 'ko' if total and korean / total > 0.5 else 'en'

    # ─────────────────────────────────────────
    # OCR 반복 아티팩트 제거
    # ─────────────────────────────────────────
    def _clean_ocr_artifacts(self, text: str) -> str:
        """
        marker OCR 아티팩트 정리:
        1. 라인 내 짧은 패턴 반복 압축
        2. 연속 중복 라인 제거
        3. 단락 수준 중복 제거
        """
        # 1) 라인 내 반복 패턴 압축
        def collapse_line(line: str) -> str:
            n = len(line)
            if n < 40:
                return line
            for unit_len in range(4, min(61, n // 5 + 1)):
                unit = line[:unit_len]
                i, reps = 0, 0
                while i + unit_len <= n and line[i:i + unit_len] == unit:
                    reps += 1
                    i += unit_len
                if reps >= 5:
                    return unit.rstrip()
            return line

        lines = [collapse_line(l) for l in text.split('\n')]

        # 2) 연속 중복 라인 제거
        deduped_lines = []
        prev, rep = None, 0
        for line in lines:
            if line == prev and line.strip():
                rep += 1
                if rep < 2:
                    deduped_lines.append(line)
            else:
                rep = 0
                deduped_lines.append(line)
            prev = line
        text = '\n'.join(deduped_lines)

        # 3) 단락 수준 중복 제거
        paragraphs = text.split('\n\n')
        seen: set[str] = set()
        unique_paras = []
        for para in paragraphs:
            key = para.strip()[:100]
            if len(key) > 60 and key in seen:
                continue
            if len(key) > 60:
                seen.add(key)
            unique_paras.append(para)
        return '\n\n'.join(unique_paras)

    def _normalize_markdown_escapes(self, text: str) -> str:
        """
        marker/번역기 계열에서 자주 남는 markdown escape를 정리한다.
        수식 토큰은 별도 보호되므로 일반 텍스트의 이스케이프는 복원해도 안전하다.
        """
        text = re.sub(r'\\([()\[\]{}_%#&*])', r'\1', text)
        text = text.replace('\\\\', '\\')
        return text

    def _normalize_math_wrappers(self, text: str) -> str:
        """
        marker 출력에서 자주 생기는 불필요한 바깥 괄호/대괄호를 수식 내용에서 제거한다.
        예: $(r_i^m)$ -> $r_i^m$, $$[x]$$ -> $$x$$
        """
        def unwrap_inline(m):
            content = m.group(1).strip()
            if len(content) >= 2 and content[0] == '(' and content[-1] == ')':
                inner = content[1:-1].strip()
                if inner:
                    content = inner
            elif len(content) >= 2 and content[0] == '[' and content[-1] == ']':
                inner = content[1:-1].strip()
                if inner:
                    content = inner
            return '$' + content + '$'

        def unwrap_block(m):
            content = m.group(1).strip()
            if len(content) >= 2 and content[0] == '[' and content[-1] == ']':
                inner = content[1:-1].strip()
                if inner:
                    content = inner
            return '$$' + content + '$$'

        text = re.sub(r'\$\$([\s\S]*?)\$\$', unwrap_block, text)
        text = re.sub(r'(?<!\$)\$([^\n$]{1,1000}?)\$(?!\$)', unwrap_inline, text)
        return text

    # 번역 단계에서 보호 토큰을 식별하기 위한 정규식
    _STASH_RE = re.compile(r'\x00ST(\d+)ST\x00')

    def _protect_and_translate(self, text: str, src: str, tgt: str) -> str:
        """
        수식·코드블록·표를 내부 토큰으로 스태시.
        번역 시 토큰은 절대 번역기로 보내지 않고, 복원 후 원문 삽입.
        """
        vault = {}
        idx = [0]

        def stash(m):
            token = f"\x00ST{idx[0]}ST\x00"
            vault[token] = m.group(0)
            idx[0] += 1
            return token

        s = text
        s = re.sub(r'\$\$[\s\S]*?\$\$', stash, s)           # 블록 수식 $$
        s = re.sub(r'\\\[[\s\S]*?\\\]', stash, s)            # 블록 수식 \[
        s = re.sub(r'```[\s\S]*?```', stash, s)              # 코드 펜스
        s = re.sub(
            r'<\/?(?:sup|sub|span|em|strong|b|i|br|figure|figcaption|code|pre|table|thead|tbody|tr|th|td|a|img|p|div|section|article|header|footer|ul|ol|li|math|mrow|mi|mo|mn|msup|msub|h[1-6])(?:\s+[^>]*)?>',
            stash,
            s,
        )  # 원시 HTML 태그
        s = re.sub(r'(?m)^(\|[^\n]+\n)+', stash, s)          # 표
        # \(...\) stash 제거: marker는 $...$로 수식 출력, \(는 Fig.\(a), abbr 등에 오인식됨

        # 단락 단위로 번역 — 토큰은 절대 번역기로 보내지 않음
        paragraphs = s.split('\n\n')
        total_paras = len(paragraphs)
        result_paras = []
        text_buf = []  # 순수 텍스트 단락 버퍼 (배치 번역용)
        _translated_count = [0]

        def flush_text_buf():
            if not text_buf:
                return
            combined = '\n\n'.join(text_buf)
            text_buf.clear()
            _translated_count[0] += 1
            if _translated_count[0] % 5 == 0:
                print(f"  [{_translated_count[0]}/{total_paras}] 번역 중... ({len(combined)}자)")
            translated = self._call_translate(combined, src, tgt) if combined.strip() else combined
            # 번역 실패 감지: 한국어가 0%면 경고
            if combined.strip() and translated == combined:
                print(f"  [미번역] {combined[:80]!r}")
            result_paras.append(translated)

        for para in paragraphs:
            real = self._STASH_RE.sub('', para).strip()
            has_token = bool(self._STASH_RE.search(para))

            if not real:
                # 토큰만 있는 단락 → 번역 없이 보존
                flush_text_buf()
                result_paras.append(para)
            elif not has_token:
                # 순수 텍스트 → 버퍼에 누적
                text_buf.append(para)
                if sum(len(p) for p in text_buf) >= 2500:
                    flush_text_buf()
            else:
                # 텍스트 + 토큰 혼재 → 토큰 경계로 쪼개서 텍스트 부분만 번역
                flush_text_buf()
                result_paras.append(self._translate_mixed(para, src, tgt))

        flush_text_buf()

        translated = '\n\n'.join(result_paras)

        # 스태시 복원
        for token, original in vault.items():
            translated = translated.replace(token, original)

        return translated

    # 번역기가 보존하는 마커 형식 (인용 참조처럼 보여 번역기가 건드리지 않음)
    _MARKER_RE = re.compile(r'\[MQ(\d+)\]')

    def _translate_mixed(self, para: str, src: str, tgt: str) -> str:
        """
        텍스트+토큰 혼재 단락: 토큰을 [MQ0] 형태 마커로 임시 교체 후
        단락 전체를 한 번에 번역 → 문맥이 유지되어 자연스러운 번역.
        번역기가 마커를 훼손한 경우 분절 번역으로 폴백.
        """
        token_ids = self._STASH_RE.findall(para)  # ['3', '7', ...]
        if not token_ids:
            return self._call_translate(para, src, tgt) or para

        # 스태시 토큰 → [MQ0], [MQ1] ... 로 치환
        marker_map = {}   # marker → 원래 stash token
        def to_marker(m):
            n = m.group(1)
            marker = f"[MQ{len(marker_map)}]"
            marker_map[marker] = f"\x00ST{n}ST\x00"
            return marker

        marked = self._STASH_RE.sub(to_marker, para)

        # 실제 번역할 텍스트가 있는지 확인
        if not self._MARKER_RE.sub('', marked).strip():
            return para

        translated = self._call_translate(marked, src, tgt) or marked

        # 마커가 모두 살아있으면 복원
        if all(m in translated for m in marker_map):
            for marker, token in marker_map.items():
                translated = translated.replace(marker, token)
            return translated

        # 마커가 훼손된 경우: 분절 번역 폴백 (줄바꿈 보존)
        parts = self._STASH_RE.split(para)
        ids   = self._STASH_RE.findall(para)
        result = []
        for i, part in enumerate(parts):
            stripped = part.strip()
            if stripped:
                leading  = part[:len(part) - len(part.lstrip('\n '))]
                trailing = part[len(part.rstrip('\n ')):]
                result.append(leading + (self._call_translate(stripped, src, tgt) or stripped) + trailing)
            else:
                result.append(part)
            if i < len(ids):
                result.append(f"\x00ST{ids[i]}ST\x00")
        return ''.join(result)

    def _call_translate(self, text: str, src: str, tgt: str) -> str:
        if not text.strip():
            return text
        fast_mode = getattr(self, '_fast_mode', False)

        def is_bad_translation(x: str) -> bool:
            if not x:
                return True
            return (
                'Error 500 (Server Error)' in x
                or "That's an error" in x
                or 'Please try again later' in x
            )

        # 1순위: DeepL
        if getattr(self, '_deepl_ok', True):
            try:
                result = self._deepl_translator.translate_text(
                    text, source_lang=src.upper(), target_lang=tgt.upper())
                return result.text if result else text
            except Exception as e:
                err_str = str(e)
                if 'Quota' in err_str or 'quota' in err_str or '456' in err_str:
                    print("  [DeepL] 월 한도 초과 - Google Translate로 전환합니다")
                    self._deepl_ok = False  # 이후 호출은 바로 Google로
                else:
                    print(f"  [DeepL 오류] {err_str[:100]}")

        # 2순위: Google Translate (무료, API 키 불필요)
        from deep_translator import GoogleTranslator
        print("  [Fallback] Google Translate 경로 사용")

        google_translator = GoogleTranslator(source=src, target=tgt)
        chunk_translator = GoogleTranslator(source='auto', target=tgt)

        def translate_long_text_with_fallback(source_text: str) -> str:
            citation_vault = {}

            def stash_citation(m):
                token = f"[[CT{len(citation_vault)}]]"
                citation_vault[token] = m.group(0)
                return token

            prepared_text = re.sub(r'\((?=[^)]*\b\d{4}\b)[^()]{1,140}\)', stash_citation, source_text)
            sentence_chunks = re.split(r'(?<=[.!?;:])\s+', prepared_text)
            rebuilt = []
            buffer = ''

            def flush_buffer() -> None:
                nonlocal buffer
                if not buffer.strip():
                    return
                try:
                    chunk_result = chunk_translator.translate(buffer)
                except Exception:
                    chunk_result = buffer
                rebuilt.append(chunk_result if chunk_result is not None else buffer)
                buffer = ''

            for sentence in sentence_chunks:
                sentence = sentence.strip()
                if not sentence:
                    continue
                if len(buffer) + len(sentence) + 1 > 700:
                    flush_buffer()
                if len(sentence) > 1200:
                    fragments = re.split(r',\s+', sentence)
                    for fragment in fragments:
                        fragment = fragment.strip()
                        if not fragment:
                            continue
                        if len(buffer) + len(fragment) + 1 > 700:
                            flush_buffer()
                        buffer = fragment if not buffer else buffer + ' ' + fragment
                else:
                    buffer = sentence if not buffer else buffer + ' ' + sentence

            flush_buffer()
            joined = ' '.join(rebuilt).strip()
            for token, original in citation_vault.items():
                joined = joined.replace(token, original)
            # 번역기가 대괄호를 건드린 경우까지 복원
            for i, original in enumerate(citation_vault.values()):
                joined = re.sub(rf'\[?\[?CT{i}\]?\]?', original, joined)
            return joined

        max_attempts = 2 if fast_mode else 3
        base_retry_delay = 8 if fast_mode else 15

        for attempt in range(max_attempts):
            try:
                result = google_translator.translate(text)
                if result is not None and result != text and not is_bad_translation(result):
                    return result

                # 긴 문단이 그대로 반환되면 문장 단위로 쪼개서 재시도
                if len(text) > 300 and re.search(r'[A-Za-z]{4,}', text):
                    joined = translate_long_text_with_fallback(text)
                    if joined and joined != text and not is_bad_translation(joined):
                        return joined

                return result if result is not None else text
            except Exception as e:
                err_str = str(e)
                retry_delay = base_retry_delay
                m = re.search(r'retryDelay[\'"]?\s*[:=]\s*[\'"]?(\d+)', err_str)
                if m:
                    retry_delay = min(int(m.group(1)) + 3, 20 if fast_mode else 30)
                if '429' in err_str or 'quota' in err_str.lower() or 'RESOURCE_EXHAUSTED' in err_str:
                    if attempt < max_attempts - 1:
                        print(f"  [Google 429] {retry_delay}초 대기... ({attempt+1}/{max_attempts})")
                        time.sleep(retry_delay)
                    else:
                            print(f"  [Warning] 번역 실패 (429): {err_str[:80]}")
                            break
                elif attempt < max_attempts - 1:
                    time.sleep(0.3 if fast_mode else 1)
                else:
                    print(f"  [Warning] 번역 실패: {err_str[:80]}")
                    break

        if len(text) > 300 and re.search(r'[A-Za-z]{4,}', text):
            joined = translate_long_text_with_fallback(text)
            if joined and joined != text and not is_bad_translation(joined):
                return joined
        return text

    # ─────────────────────────────────────────
    # 이미지 참조 → base64 인라인
    # ─────────────────────────────────────────
    def _embed_images(self, md: str, images: dict) -> str:
        """
        marker가 생성한 ![alt](path) 참조를 base64 <figure>로 교체.
        images 딕셔너리: { 'path/name.png': PIL.Image | bytes }
        """
        def replace_img(m):
            alt = m.group(1)
            src_path = m.group(2)

            img_obj = images.get(src_path)
            if img_obj is None:
                # 파일명만으로 재탐색
                needle = Path(src_path).name
                for k, v in images.items():
                    if Path(k).name == needle:
                        img_obj = v
                        break

            if img_obj is None:
                return m.group(0)  # 못 찾으면 원문 유지

            if isinstance(img_obj, PIL.Image.Image):
                buf = io.BytesIO()
                img_obj.save(buf, format='PNG')
                b64 = base64.b64encode(buf.getvalue()).decode()
                mime = 'image/png'
            elif isinstance(img_obj, bytes):
                b64 = base64.b64encode(img_obj).decode()
                mime = 'image/png'
            else:
                return m.group(0)

            cap = f'<figcaption>{alt}</figcaption>' if alt else ''
            return (
                f'\n\n<figure style="text-align:center;margin:2em 0">'
                f'<img src="data:{mime};base64,{b64}" '
                f'style="max-width:100%;border-radius:6px;'
                f'box-shadow:0 2px 12px rgba(0,0,0,0.12)">'
                f'{cap}</figure>\n\n'
            )

        return re.sub(r'!\[([^\]]*)\]\(([^\)]+)\)', replace_img, md)

    # ─────────────────────────────────────────
    # 최종 마크다운 후처리
    # ─────────────────────────────────────────
    def _postprocess_md(self, md: str) -> str:
        """
        번역 후 잔여 아티팩트 제거 및 수식 주변 정리.
        """
        def normalize_left_right(math_text: str) -> str:
            def normalize_cases_block(text: str) -> str:
                def rebuild(m):
                    content = m.group(1).strip()
                    if not content:
                        return m.group(0)

                    # 케이스 항목은 보통 ', \ j = ...' 형태로 이어지므로 그 경계를 기준으로 분할한다.
                    clauses = [
                        c.strip().rstrip(',').rstrip('.')
                        for c in re.split(r',\s*\\\s*(?=[A-Za-z]\s*=)', content)
                        if c.strip()
                    ]

                    parts = [
                        re.sub(r'^\\\s*', '', p).strip()
                        for p in clauses
                        if p
                    ]

                    seen_lhs = set()
                    rebuilt_parts = []
                    for part in parts:
                        lhs = re.match(r'([A-Za-z][A-Za-z0-9_]*)\s*=', part)
                        if lhs:
                            key = lhs.group(1)
                            if key in seen_lhs:
                                continue
                            seen_lhs.add(key)
                        rebuilt_parts.append(part)

                    if not rebuilt_parts:
                        return m.group(0)
                    return r'\begin{cases} ' + r',\ '.join(rebuilt_parts) + r' \end{cases}'

                return re.sub(r'\\begin\{cases\}([\s\S]*?)\\end\{cases\}', rebuild, text)

            # 번역기가 백슬래시를 떨어뜨린 left/right를 수식 명령으로 복구
            math_text = re.sub(r'(?<!\\)\bleft\b', r'\\left', math_text)
            math_text = re.sub(r'(?<!\\)\bright\b', r'\\right', math_text)
            # 중괄호 delimiter는 \{ / \} 형태여야 MathJax가 인식한다.
            math_text = re.sub(r'\\left\s*\{', r'\\left\\{', math_text)
            math_text = re.sub(r'\\right\s*\}', r'\\right\\}', math_text)
            # 케이스 블록에서 자주 생기는 중복/마침표 아티팩트 정리
            math_text = re.sub(
                r'(\\k\s*=\s*1,\s*\\dots,\s*K,\s*)\\k\s*=\s*1,\s*\\dots,\s*K,\s*',
                r'\1',
                math_text,
            )
            math_text = re.sub(r',\s*\\end\{cases\}', r' \\end{cases}', math_text)
            math_text = re.sub(r'\\end\{cases\}\s*\.', r'\\end{cases}', math_text)
            math_text = normalize_cases_block(math_text)
            return math_text

        def normalize_math_segments(text: str) -> str:
            text = re.sub(
                r'\$\$([\s\S]*?)\$\$',
                lambda m: '$$' + normalize_left_right(m.group(1)) + '$$',
                text,
            )
            text = re.sub(
                r'\\\(([\s\S]*?)\\\)',
                lambda m: r'\(' + normalize_left_right(m.group(1)) + r'\)',
                text,
            )
            text = re.sub(
                r'\\\[([\s\S]*?)\\\]',
                lambda m: r'\[' + normalize_left_right(m.group(1)) + r'\]',
                text,
            )
            text = re.sub(
                r'(?<!\$)\$([^\n$]{1,1000}?)\$(?!\$)',
                lambda m: '$' + normalize_left_right(m.group(1)) + '$',
                text,
            )
            return text

        # 복원 실패한 스태시 토큰 제거
        md = re.sub(r'\x00ST\d+ST\x00', '', md)

        # 번역기가 훼손한 [MQ0] 마커 잔여 제거
        md = re.sub(r'\[MQ\d+\]', '', md)

        # MDPI/marker 계열에서 자주 남는 마크다운 이스케이프 정리
        # 수식은 이미 보호된 뒤라, 일반 텍스트의 escaped 괄호/언더스코어를 복원해도 안전하다.
        md = re.sub(r'\\([()\[\]{}_%#&*])', r'\1', md)
        md = normalize_math_segments(md)
        md = self._normalize_math_wrappers(md)

        # 과도한 괄호로 남은 수식 토큰을 인라인 수식으로 정규화
        # 예: ((C(i))) -> $C(i)$, (F_{m-1}(f_i)) -> $F_{m-1}(f_i)$
        md = re.sub(
            r'\(\(([A-Za-z][A-Za-z0-9_\\^{}]*(?:\([^\)]*\))?)\)\)',
            r'$\1$',
            md,
        )

        # 블록 수식의 괄호 깨짐 보정
        md = re.sub(r'=\s*\[\[([^\]\n]+)\]\]', r'= [\1]', md)
        md = re.sub(r'\\right\s+(\\tag\{\d+\})', r'\\right] \1', md)

        # 이미 \tag가 들어간 블록 수식에서 바깥 대괄호만 제거
        def unwrap_tagged_block(m):
            content = m.group(1).strip()
            tag = m.group(2) or ''
            if content.startswith('['):
                content = content[1:].lstrip()
            if content.endswith(']'):
                content = content[:-1].rstrip()
            return '$$' + content + (' ' + tag if tag else '') + '$$'

        md = re.sub(r'\$\$([\s\S]*?)\s*(\\tag\{\d+\})\$\$', unwrap_tagged_block, md)

        # 수식번호 (N) → 수식 내 \tag{N} 삽입 (MathJax가 우측에 번호 자동 렌더링)
        # 단일행: $$...$$  (25)
        # 다중행: $$\n...\n$$  (25)
        def insert_tag(m):
            content = m.group(1).rstrip()
            if content.startswith('['):
                content = content[1:].lstrip()
            if content.endswith(']'):
                content = content[:-1].rstrip()
            num = m.group(2)
            if r'\tag' not in content:  # 이미 tag 있으면 건드리지 않음
                content = content + r' \tag{' + num + '}'
            return '$$' + content + '$$'
        md = re.sub(r'\$\$([\s\S]*?)\$\$\s*\((\d+)\)', insert_tag, md)

        return md

    # ─────────────────────────────────────────
    # Markdown → HTML body
    # ─────────────────────────────────────────
    def _md_to_html(self, md: str) -> str:
        import markdown as md_lib
        math_vault = {}
        token_idx = [0]

        def stash_math(html: str) -> str:
            token = f"\x00MATH{token_idx[0]}MATH\x00"
            math_vault[token] = html
            token_idx[0] += 1
            return token

        protected = md

        def stash_display(m):
            content = m.group(1).strip()
            return stash_math(f'<div class="arithmatex">\\[{content}\\]</div>')

        def stash_inline_paren(m):
            content = m.group(1).strip()
            return stash_math(f'<span class="arithmatex">\\({content}\\)</span>')

        def stash_inline_dollar(m):
            content = m.group(1).strip()
            if '\n' in content or r'\begin' in content or r'\end' in content:
                return stash_math(f'<div class="arithmatex">\\[{content}\\]</div>')
            return stash_math(f'<span class="arithmatex">\\({content}\\)</span>')

        protected = re.sub(r'(?<!\\)\$\$([\s\S]*?)\$\$', stash_display, protected)
        protected = re.sub(r'(?<!\\)\\\[([\s\S]*?)\\\]', stash_display, protected)
        protected = re.sub(r'(?<!\\)\\\(([^\n]*?)\\\)', stash_inline_paren, protected)
        protected = re.sub(r'(?<!\\)\$(?!\$)([\s\S]{1,1000}?)\$(?!\$)', stash_inline_dollar, protected)

        try:
            html = md_lib.markdown(protected, extensions=['fenced_code', 'tables'])
        except Exception:
            html = md_lib.markdown(protected)

        for token, replacement in math_vault.items():
            html = html.replace(token, replacement)
        return html

    # ─────────────────────────────────────────
    # 전체 처리
    # ─────────────────────────────────────────
    def translate_document(self, input_path: str, output_html: str = None,
                           direction: str = 'auto', fast_mode: bool = False) -> None:
        self._fast_mode = fast_mode
        t0 = time.perf_counter()
        input_path = Path(input_path)
        if not input_path.exists():
            raise FileNotFoundError(f"PDF를 찾을 수 없습니다: {input_path}")

        if output_html is None:
            OUTPUT_DIR.mkdir(exist_ok=True)
            output_html = OUTPUT_DIR / (input_path.stem + "_translated.html")
        output_html = Path(output_html)
        output_html.parent.mkdir(parents=True, exist_ok=True)

        import deepl as _deepl
        self._deepl_translator = _deepl.Translator(_load_deepl_key())

        print(f"[PDF] {input_path.name}")
        print("[1/4] marker 모델 로드 중... (처음 실행 시 모델 자동 다운로드, 수 분 소요)")
        t_marker = time.perf_counter()
        self._load_marker()
        print(f"  marker 로드 시간: {time.perf_counter() - t_marker:.1f}초")

        print("[2/4] PDF 파싱 중... (수식/표/그림/의사코드 추출)")
        t_parse = time.perf_counter()
        raw_md, images = self._run_marker(str(input_path))
        raw_md = self._clean_ocr_artifacts(raw_md)
        # marker-pdf 내부 앵커/외부 링크 제거 → 링크 텍스트만 남김
        # (?<!!) 로 이미지 링크 ![...](...) 는 제외
        _link_pat = re.compile(r'(?<!!)\[((?:[^\[\]]|\[[^\[\]]*\])*)\]\([^\)]*\)')
        for _ in range(4):  # 중첩이 깊을 경우 반복
            raw_md = _link_pat.sub(r'\1', raw_md)
        raw_md = self._normalize_markdown_escapes(raw_md)
        print(f"  추출 완료 - 이미지 {len(images)}개, 텍스트 {len(raw_md):,}자")
        print(f"  PDF 파싱 시간: {time.perf_counter() - t_parse:.1f}초")

        detected = self._detect_lang(raw_md[:3000])
        if direction == 'auto':
            direction = 'en_to_ko' if detected == 'en' else 'ko_to_en'
        src, tgt = direction.split('_to_')
        # 속도 우선 모드에서는 디버그 파일 저장 I/O를 생략
        if fast_mode:
            print("  [디버그] fast 모드: 전처리 마크다운 저장 생략")
        else:
            debug_path = output_html.parent / (output_html.stem.replace('_translated','') + '_debug_processed.md')
            debug_path.write_text(raw_md, encoding='utf-8')
            print(f"  [디버그] 전처리 완료 마크다운 저장: {debug_path.name}")

        print(f"[3/4] 번역 중... {src.upper()} -> {tgt.upper()}")
        t_trans = time.perf_counter()
        translated_md = self._protect_and_translate(raw_md, src, tgt)
        print(f"  번역 시간: {time.perf_counter() - t_trans:.1f}초")

        print("[4/4] HTML 생성 중...")
        t_html = time.perf_counter()
        final_md = self._embed_images(translated_md, images)
        final_md = self._postprocess_md(final_md)
        body_html = self._md_to_html(final_md)
        # HTML 후처리: 수식 스팬/블록 바깥에 남은 달러 기호만 제거
        body_html = re.sub(
            r'\$+\s*(<(?:span|div) class="arithmatex">[\s\S]*?</(?:span|div)>)\s*\$+',
            r'\1',
            body_html,
        )
        self._write_html(body_html, str(output_html))
        print(f"  HTML 생성 시간: {time.perf_counter() - t_html:.1f}초")
        print(f"  총 소요 시간: {time.perf_counter() - t0:.1f}초")
        print(f"[완료] {output_html}")

    # ─────────────────────────────────────────
    # HTML 템플릿
    # ─────────────────────────────────────────
    def _write_html(self, body_html: str, output_path: str) -> None:
        html = f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>논문 번역</title>
<script>
MathJax = {{
  tex: {{
    inlineMath: [['\\\\(','\\\\)'], ['$','$']],
    displayMath: [['\\\\[','\\\\]'], ['$$','$$']],
    processEscapes: true,
    tags: 'ams'
  }},
  options: {{ skipHtmlTags: ['script','noscript','style','textarea','pre'] }}
}};
</script>
<script src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-chtml.js" async></script>
<style>
  body {{
    font-family: 'Segoe UI', 'Malgun Gothic', sans-serif;
    max-width: 920px;
    margin: 40px auto;
    padding: 0 24px 80px;
    line-height: 1.9;
    color: #1a1a1a;
    background: #fff;
  }}
  h1 {{ font-size: 1.65em; border-bottom: 2px solid #1a56db; padding-bottom: 10px; color: #1a1a2e; margin-top: 1.6em; }}
  h2 {{ font-size: 1.28em; border-bottom: 1px solid #cbd5e0; padding-bottom: 6px; color: #1a1a2e; margin-top: 2em; }}
  h3 {{ font-size: 1.08em; color: #2d3748; margin-top: 1.4em; }}
  p  {{ margin: 0.75em 0; }}
  hr {{ border: none; border-top: 1px solid #e2e8f0; margin: 2.5em 0; }}
  figure {{ margin: 2em auto; text-align: center; }}
  figure img {{ max-width: 100%; border-radius: 6px; box-shadow: 0 2px 12px rgba(0,0,0,0.12); }}
  figcaption {{ color: #555; font-size: 0.88em; margin-top: 0.5em; font-style: italic; }}
  table {{ border-collapse: collapse; width: 100%; margin: 1.4em 0; font-size: 0.94em; }}
  th, td {{ border: 1px solid #cbd5e0; padding: 9px 14px; text-align: left; }}
  th {{ background: #ebf4ff; font-weight: 600; }}
  tr:nth-child(even) {{ background: #f7fafc; }}
  pre, code {{ font-family: 'Consolas', 'D2Coding', monospace; }}
  pre {{
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-left: 4px solid #1a56db;
    padding: 16px 20px;
    border-radius: 6px;
    overflow-x: auto;
    font-size: 0.87em;
    line-height: 1.65;
  }}
  code {{ background: #f1f5f9; padding: 2px 6px; border-radius: 4px; font-size: 0.9em; }}
  .MathJax {{ font-size: 1.05em !important; }}
</style>
</head>
<body>
{body_html}
</body>
</html>"""

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html)


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────
def main():
    args = sys.argv[1:]
    fast_mode = False
    if "--fast" in args:
        fast_mode = True
        args = [a for a in args if a != "--fast"]

    if len(args) < 1:
        print("사용법: python paper_translator.py <pdf파일> [출력.html] [방향] [--fast]")
        print("방향: auto(기본) | en_to_ko | ko_to_en")
        sys.exit(1)

    pdf_file    = args[0]
    output_file = args[1] if len(args) > 1 else None
    direction   = args[2] if len(args) > 2 else 'auto'

    try:
        PaperTranslator().translate_document(pdf_file, output_file, direction, fast_mode=fast_mode)
    except (ValueError, FileNotFoundError, RuntimeError) as e:
        print(f"[Error] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
