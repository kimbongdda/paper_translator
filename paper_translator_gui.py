import os
import sys
import threading
import queue
import subprocess
from dataclasses import dataclass
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox


@dataclass(frozen=True)
class TranslationRequest:
    input_pdf: str
    output_html: str
    direction: str
    api_key: str
    save_key: bool
    fast_mode: bool


class TranslatorGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Paper Translator")
        self.root.geometry("980x720")
        self.root.minsize(900, 620)

        self.base_dir = Path(__file__).parent
        self.cli_path = self.base_dir / "paper_translator.py"
        self.key_file = self.base_dir / "deepl_key.txt"

        self.log_queue: queue.Queue[str] = queue.Queue()
        self.proc: subprocess.Popen | None = None

        self.input_var = tk.StringVar()
        self.output_var = tk.StringVar()
        self.direction_var = tk.StringVar(value="auto")
        self.api_var = tk.StringVar(value=self._initial_api_value())
        self.save_key_var = tk.BooleanVar(value=False)
        self.fast_mode_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="Ready")
        self.api_state_var = tk.StringVar(value=self._api_state_text())

        self._configure_style()
        self._build_ui()
        self._poll_logs()

    def _configure_style(self) -> None:
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except Exception:
            pass

        style.configure("Title.TLabel", font=("Segoe UI", 16, "bold"))
        style.configure("Sub.TLabel", font=("Segoe UI", 10), foreground="#4b5563")
        style.configure("Section.TLabelframe", padding=10)
        style.configure("Section.TLabelframe.Label", font=("Segoe UI", 10, "bold"))
        style.configure("Primary.TButton", font=("Segoe UI", 10, "bold"))

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root, padding=14)
        outer.pack(fill="both", expand=True)

        header = ttk.Frame(outer)
        header.pack(fill="x", pady=(0, 10))
        ttk.Label(header, text="Paper Translator GUI", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            header,
            text="PDF 선택 → API 설정 팝업 → 번역 실행 → 결과 HTML 확인",
            style="Sub.TLabel",
        ).pack(anchor="w", pady=(2, 0))

        cfg = ttk.LabelFrame(outer, text="Translation Setup", style="Section.TLabelframe")
        cfg.pack(fill="x")

        # Input PDF
        ttk.Label(cfg, text="Input PDF").grid(row=0, column=0, sticky="w")
        input_entry = ttk.Entry(cfg, textvariable=self.input_var)
        input_entry.grid(row=1, column=0, sticky="ew", padx=(0, 8))
        ttk.Button(cfg, text="Browse", command=self._browse_input).grid(row=1, column=1, sticky="ew")

        # Output HTML
        ttk.Label(cfg, text="Output HTML").grid(row=2, column=0, sticky="w", pady=(10, 0))
        output_entry = ttk.Entry(cfg, textvariable=self.output_var)
        output_entry.grid(row=3, column=0, sticky="ew", padx=(0, 8))
        ttk.Button(cfg, text="Browse", command=self._browse_output).grid(row=3, column=1, sticky="ew")

        # Direction
        ttk.Label(cfg, text="Direction").grid(row=4, column=0, sticky="w", pady=(10, 0))
        direction_box = ttk.Combobox(
            cfg,
            textvariable=self.direction_var,
            values=["auto", "en_to_ko", "ko_to_en"],
            state="readonly",
            width=18,
        )
        direction_box.grid(row=5, column=0, sticky="w")

        ttk.Button(cfg, text="API 설정", command=self._open_api_dialog).grid(row=5, column=1, sticky="ew")
        ttk.Label(cfg, textvariable=self.api_state_var, style="Sub.TLabel").grid(row=6, column=0, sticky="w", pady=(8, 0))
        ttk.Checkbutton(cfg, text="속도 우선 모드", variable=self.fast_mode_var).grid(row=7, column=0, sticky="w", pady=(6, 0))

        cfg.columnconfigure(0, weight=1)

        actions = ttk.Frame(outer)
        actions.pack(fill="x", pady=(10, 8))

        self.run_btn = ttk.Button(actions, text="Run Translation", style="Primary.TButton", command=self._run_translation)
        self.run_btn.pack(side="left")

        self.stop_btn = ttk.Button(actions, text="Stop", command=self._stop_translation, state="disabled")
        self.stop_btn.pack(side="left", padx=(8, 0))

        ttk.Button(actions, text="Open Output Folder", command=self._open_output_folder).pack(side="left", padx=(8, 0))
        ttk.Button(actions, text="Open Output HTML", command=self._open_output_html).pack(side="left", padx=(8, 0))

        self.progress = ttk.Progressbar(actions, mode="indeterminate", length=180)
        self.progress.pack(side="right")

        status_bar = ttk.Frame(outer)
        status_bar.pack(fill="x", pady=(0, 8))
        ttk.Label(status_bar, text="Status:", style="Sub.TLabel").pack(side="left")
        ttk.Label(status_bar, textvariable=self.status_var).pack(side="left", padx=(6, 0))

        log_box = ttk.LabelFrame(outer, text="Log", style="Section.TLabelframe")
        log_box.pack(fill="both", expand=True)

        self.log_text = tk.Text(
            log_box,
            height=22,
            wrap="word",
            bg="#0f172a",
            fg="#e2e8f0",
            insertbackground="#e2e8f0",
            relief="flat",
            padx=8,
            pady=8,
            font=("Consolas", 10),
        )
        self.log_text.pack(side="left", fill="both", expand=True)

        scrollbar = ttk.Scrollbar(log_box, orient="vertical", command=self.log_text.yview)
        scrollbar.pack(side="right", fill="y")
        self.log_text.configure(yscrollcommand=scrollbar.set)

    def _initial_api_value(self) -> str:
        env_key = os.environ.get("DEEPL_API_KEY", "").strip()
        if env_key:
            return env_key
        if self.key_file.exists():
            return self.key_file.read_text(encoding="utf-8").strip()
        return ""

    def _api_state_text(self) -> str:
        if self.api_var.get().strip():
            return "API 상태: 세션 키 입력됨"
        if self.key_file.exists():
            return "API 상태: deepl_key.txt 사용"
        if os.environ.get("DEEPL_API_KEY", "").strip():
            return "API 상태: 환경변수 사용"
        return "API 상태: 미설정"

    def _refresh_api_state(self) -> None:
        self.api_state_var.set(self._api_state_text())

    def _set_running(self) -> None:
        self.status_var.set("Running")
        self.run_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.progress.start(10)

    def _set_idle(self) -> None:
        self.status_var.set("Ready")
        self.run_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        self.progress.stop()

    def _collect_request(self) -> TranslationRequest:
        return TranslationRequest(
            input_pdf=self.input_var.get().strip(),
            output_html=self.output_var.get().strip(),
            direction=self.direction_var.get().strip() or "auto",
            api_key=self.api_var.get().strip(),
            save_key=self.save_key_var.get(),
            fast_mode=self.fast_mode_var.get(),
        )

    def _validate_request(self, request: TranslationRequest) -> bool:
        if not request.input_pdf:
            messagebox.showwarning("Missing Input", "Please select an input PDF.")
            return False
        if not Path(request.input_pdf).exists():
            messagebox.showerror("Invalid Input", "Input PDF does not exist.")
            return False
        if not request.output_html:
            messagebox.showwarning("Missing Output", "Please choose an output HTML path.")
            return False
        if not self.cli_path.exists():
            messagebox.showerror("Missing Script", f"Cannot find CLI script: {self.cli_path}")
            return False
        if not request.api_key and not self.key_file.exists() and not os.environ.get("DEEPL_API_KEY", "").strip():
            messagebox.showwarning("Missing API Key", "DeepL API 키를 입력하거나 deepl_key.txt를 준비해주세요.")
            return False
        return True

    def _prepare_output_dir(self, request: TranslationRequest) -> None:
        Path(request.output_html).parent.mkdir(parents=True, exist_ok=True)

    def _store_api_key_if_needed(self, request: TranslationRequest) -> None:
        if not request.api_key or not request.save_key:
            self._refresh_api_state()
            return
        try:
            self.key_file.write_text(request.api_key, encoding="utf-8")
            self._refresh_api_state()
        except Exception as e:
            messagebox.showerror("Key Save Error", str(e))
            raise

    def _build_command(self, request: TranslationRequest) -> list[str]:
        cmd = [
            sys.executable,
            "-u",
            str(self.cli_path),
            request.input_pdf,
            request.output_html,
            request.direction,
        ]
        if request.fast_mode:
            cmd.append("--fast")
        return cmd

    def _build_env(self, request: TranslationRequest) -> dict[str, str]:
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        if request.api_key:
            env["DEEPL_API_KEY"] = request.api_key
        return env

    def _log_request(self, request: TranslationRequest) -> None:
        self.log_text.delete("1.0", tk.END)
        self._append_log("[GUI] Starting translation...\n")
        self._append_log(f"[GUI] Input: {request.input_pdf}\n")
        self._append_log(f"[GUI] Output: {request.output_html}\n")
        self._append_log(f"[GUI] Direction: {request.direction}\n\n")
        self._append_log(f"[GUI] Fast mode: {'ON' if request.fast_mode else 'OFF'}\n\n")

    def _open_api_dialog(self) -> None:
        dialog = tk.Toplevel(self.root)
        dialog.title("DeepL API 설정")
        dialog.geometry("520x220")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()

        local_api_var = tk.StringVar(value=self.api_var.get())
        local_show_var = tk.BooleanVar(value=False)
        local_save_var = tk.BooleanVar(value=self.save_key_var.get())

        wrap = ttk.Frame(dialog, padding=14)
        wrap.pack(fill="both", expand=True)

        ttk.Label(wrap, text="DeepL API Key").grid(row=0, column=0, sticky="w")
        entry = ttk.Entry(wrap, textvariable=local_api_var, show="*")
        entry.grid(row=1, column=0, sticky="ew", padx=(0, 8), pady=(4, 0))
        ttk.Checkbutton(
            wrap,
            text="Show",
            variable=local_show_var,
            command=lambda: entry.configure(show="" if local_show_var.get() else "*"),
        ).grid(row=1, column=1, sticky="w", pady=(4, 0))

        ttk.Checkbutton(
            wrap,
            text="deepl_key.txt에 저장",
            variable=local_save_var,
        ).grid(row=2, column=0, sticky="w", pady=(10, 0))

        ttk.Label(
            wrap,
            text="저장하지 않으면 이번 실행에서만 사용됩니다.",
            style="Sub.TLabel",
        ).grid(row=3, column=0, sticky="w", pady=(4, 0))

        btns = ttk.Frame(wrap)
        btns.grid(row=4, column=0, columnspan=2, sticky="e", pady=(14, 0))

        def apply_and_close() -> None:
            self.api_var.set(local_api_var.get().strip())
            self.save_key_var.set(local_save_var.get())
            self._refresh_api_state()
            dialog.destroy()

        ttk.Button(btns, text="취소", command=dialog.destroy).pack(side="right")
        ttk.Button(btns, text="적용", command=apply_and_close).pack(side="right", padx=(0, 8))

        wrap.columnconfigure(0, weight=1)
        entry.focus_set()

    def _browse_input(self) -> None:
        file_path = filedialog.askopenfilename(
            title="Select PDF",
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")],
        )
        if not file_path:
            return

        self.input_var.set(file_path)
        p = Path(file_path)
        default_output = self.base_dir / "output" / f"{p.stem}_translated.html"
        self.output_var.set(str(default_output))

    def _browse_output(self) -> None:
        file_path = filedialog.asksaveasfilename(
            title="Save translated HTML",
            defaultextension=".html",
            filetypes=[("HTML files", "*.html"), ("All files", "*.*")],
        )
        if file_path:
            self.output_var.set(file_path)

    def _run_translation(self) -> None:
        if self.proc is not None:
            return

        request = self._collect_request()
        if not self._validate_request(request):
            return

        try:
            self._store_api_key_if_needed(request)
        except Exception:
            return

        self._prepare_output_dir(request)
        self._log_request(request)

        self._set_running()

        cmd = self._build_command(request)
        env = self._build_env(request)

        worker = threading.Thread(
            target=self._run_process_thread,
            args=(cmd, env, request.output_html),
            daemon=True,
        )
        worker.start()

    def _run_process_thread(self, cmd: list[str], env: dict[str, str], output_html: str) -> None:
        try:
            self.proc = subprocess.Popen(
                cmd,
                cwd=str(self.base_dir),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )

            assert self.proc.stdout is not None
            for line in self.proc.stdout:
                self.log_queue.put(line)

            rc = self.proc.wait()
            if rc == 0:
                self.log_queue.put(f"\n[GUI] Done. Output: {output_html}\n")
            else:
                self.log_queue.put(f"\n[GUI] Failed with exit code {rc}.\n")
        except Exception as e:
            self.log_queue.put(f"\n[GUI] Error: {e}\n")
        finally:
            self.proc = None
            self.log_queue.put("__GUI_FINISHED__")

    def _stop_translation(self) -> None:
        if self.proc is None:
            return
        try:
            self.proc.terminate()
            self._append_log("\n[GUI] Termination requested.\n")
            self.status_var.set("Stopping...")
        except Exception as e:
            self._append_log(f"\n[GUI] Stop error: {e}\n")

    def _poll_logs(self) -> None:
        while not self.log_queue.empty():
            msg = self.log_queue.get_nowait()
            if msg == "__GUI_FINISHED__":
                self._set_idle()
            else:
                self._append_log(msg)
        self.root.after(120, self._poll_logs)

    def _append_log(self, text: str) -> None:
        self.log_text.insert(tk.END, text)
        self.log_text.see(tk.END)

    def _open_output_folder(self) -> None:
        out_dir = self.base_dir / "output"
        out_dir.mkdir(exist_ok=True)
        try:
            os.startfile(str(out_dir))  # type: ignore[attr-defined]
        except Exception as e:
            messagebox.showerror("Open Folder Error", str(e))

    def _open_output_html(self) -> None:
        output_html = self.output_var.get().strip()
        if not output_html:
            messagebox.showwarning("No Output", "출력 HTML 경로가 비어 있습니다.")
            return
        path = Path(output_html)
        if not path.exists():
            messagebox.showwarning("Missing Output", "아직 출력 HTML이 생성되지 않았습니다.")
            return
        try:
            os.startfile(str(path))  # type: ignore[attr-defined]
        except Exception as e:
            messagebox.showerror("Open HTML Error", str(e))


def main() -> None:
    root = tk.Tk()
    TranslatorGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
