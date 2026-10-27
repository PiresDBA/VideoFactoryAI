#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Interface gráfica do VideoFactoryAI.

A GUI é uma camada de controle: chama agent.py como subprocesso, não duplica
nem altera a lógica do pipeline. Execute a partir da pasta do projeto.
"""
from __future__ import annotations

import os
import queue
import shutil
import signal
import subprocess
import sys
import threading
import time
import re
import unicodedata
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

APP_TITLE = "VideoFactoryAI — Estúdio de Produção"


class VideoFactoryGUI(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1040x860")
        self.minsize(900, 740)
        self.configure(padx=12, pady=10)
        self.project_dir = tk.StringVar(value=str(Path(__file__).resolve().parent))
        self.script_path = tk.StringVar()
        self.mode = tk.StringVar(value="script")
        self.topic = tk.StringVar()
        self.duration = tk.StringVar(value="5")
        self.channel = tk.StringVar(value="documentario")
        self.voice = tk.StringVar(value="pt-BR-AntonioNeural")
        self.tts_engine = tk.StringVar(value="edge-tts")
        # Arquivo de referência usado pelo XTTS para clonar a voz.
        self.xtts_reference = tk.StringVar(value="")
        self.whisper_model = tk.StringVar(value="base")
        self.art_director = tk.StringVar(value="standard")
        self.youtube_mode = tk.StringVar(value="cc")
        self.authorized_video = tk.StringVar()
        self.source_url = tk.StringVar()
        self.rights_confirmed = tk.BooleanVar(value=False)
        self.subtitles = tk.BooleanVar(value=True)
        self.resume = tk.BooleanVar(value=False)
        self.checkpoint = tk.BooleanVar(value=True)
        self.status = tk.StringVar(value="Pronto para configurar uma produção.")
        self.proc: subprocess.Popen | None = None
        self.log_queue: queue.Queue[str] = queue.Queue()
        self.worker: threading.Thread | None = None
        self._build_ui()
        self.after(100, self._drain_log_queue)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self) -> None:
        header = ttk.Frame(self)
        header.pack(fill="x", pady=(0, 10))
        ttk.Label(header, text="VideoFactoryAI", font=("Segoe UI", 20, "bold")).pack(anchor="w")
        ttk.Label(header, text="Crie documentários a partir de um roteiro ou de um tema. A interface acompanha o processo e mostra os logs.").pack(anchor="w", pady=(2, 0))

        project = ttk.LabelFrame(self, text="1. Pasta do projeto")
        project.pack(fill="x", pady=5)
        ttk.Entry(project, textvariable=self.project_dir).pack(side="left", fill="x", expand=True, padx=8, pady=8)
        ttk.Button(project, text="Escolher pasta…", command=self._browse_project).pack(side="left", padx=(0, 8), pady=8)
        ttk.Button(project, text="Abrir saída", command=self._open_output).pack(side="left", padx=(0, 8), pady=8)

        # Gerenciador explícito de projetos interrompidos: retomar checkpoint ou
        # remover somente os artefatos daquele projeto, nunca o roteiro de origem.
        manage = ttk.LabelFrame(self, text="Projetos existentes / produções interrompidas")
        manage.pack(fill="x", pady=(2, 5))
        ttk.Label(manage, text="Projeto:").pack(side="left", padx=(8, 4), pady=7)
        self.project_choice = tk.StringVar(value="")
        self.project_combo = ttk.Combobox(manage, textvariable=self.project_choice, state="readonly", width=32)
        self.project_combo.pack(side="left", padx=(0, 6), pady=7)
        ttk.Button(manage, text="Atualizar lista", command=self._refresh_projects).pack(side="left", padx=3, pady=7)
        self.resume_btn = ttk.Button(manage, text="↻ Retomar selecionado", command=self._resume_selected)
        self.resume_btn.pack(side="left", padx=3, pady=7)
        self.delete_btn = ttk.Button(manage, text="Excluir projeto…", command=self._delete_selected_project)
        self.delete_btn.pack(side="left", padx=3, pady=7)

        main = ttk.Frame(self)
        main.pack(fill="x", pady=5)
        source = ttk.LabelFrame(main, text="2. Entrada do documentário")
        source.pack(side="left", fill="both", expand=True, padx=(0, 5))
        ttk.Radiobutton(source, text="Usar roteiro .txt existente", variable=self.mode, value="script", command=self._update_mode).pack(anchor="w", padx=8, pady=(7, 2))
        row = ttk.Frame(source); row.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Entry(row, textvariable=self.script_path).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Selecionar…", command=self._browse_script).pack(side="left", padx=(5, 0))
        ttk.Radiobutton(source, text="Gerar roteiro automaticamente a partir de um tema", variable=self.mode, value="topic", command=self._update_mode).pack(anchor="w", padx=8, pady=(2, 4))
        ttk.Label(source, text="Tema").pack(anchor="w", padx=8)
        self.topic_entry = ttk.Entry(source, textvariable=self.topic)
        self.topic_entry.pack(fill="x", padx=8, pady=(2, 8))
        row = ttk.Frame(source); row.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Label(row, text="Duração (min):").pack(side="left")
        self.duration_entry = ttk.Entry(row, textvariable=self.duration, width=8)
        self.duration_entry.pack(side="left", padx=5)
        ttk.Label(row, text="Canal:").pack(side="left", padx=(12, 3))
        ttk.Combobox(row, textvariable=self.channel, values=["documentario", "historia", "geopolitica", "tecnologia"], width=16).pack(side="left")

        settings = ttk.LabelFrame(main, text="3. Narração, validação e fontes")
        settings.pack(side="left", fill="both", expand=True, padx=(5, 0))
        grid = ttk.Frame(settings); grid.pack(fill="x", padx=8, pady=8)
        ttk.Label(grid, text="Motor TTS").grid(row=0, column=0, sticky="w", pady=3)
        self.tts_combo = ttk.Combobox(grid, textvariable=self.tts_engine, values=["edge-tts", "xtts", "f5-tts", "openai"], state="readonly", width=16)
        self.tts_combo.grid(row=0, column=1, sticky="w", padx=6)
        self.tts_combo.bind("<<ComboboxSelected>>", self._update_tts_controls)
        ttk.Label(grid, text="Voz (Edge/OpenAI)").grid(row=1, column=0, sticky="w", pady=3)
        self.voice_combo = ttk.Combobox(grid, textvariable=self.voice, values=["pt-BR-AntonioNeural", "pt-BR-FranciscaNeural", "pt-BR-ThalitaNeural"], width=24)
        self.voice_combo.grid(row=1, column=1, sticky="w", padx=6)
        ttk.Label(grid, text="Áudio-base XTTS").grid(row=2, column=0, sticky="w", pady=3)
        ref_row = ttk.Frame(grid)
        ref_row.grid(row=2, column=1, sticky="ew", padx=6, pady=3)
        self.xtts_reference_entry = ttk.Entry(ref_row, textvariable=self.xtts_reference, width=25)
        self.xtts_reference_entry.pack(side="left", fill="x", expand=True)
        self.xtts_reference_button = ttk.Button(ref_row, text="Escolher WAV…", command=self._browse_xtts_reference)
        self.xtts_reference_button.pack(side="left", padx=(5, 0))
        ttk.Label(settings, text="XTTS clona a voz a partir deste áudio (recomendado: WAV limpo de 10–30 segundos, sem música).", wraplength=460).pack(anchor="w", padx=8, pady=(0, 5))
        ttk.Label(grid, text="Whisper").grid(row=3, column=0, sticky="w", pady=3)
        ttk.Combobox(grid, textvariable=self.whisper_model, values=["tiny", "base", "small", "medium", "large"], state="readonly", width=16).grid(row=3, column=1, sticky="w", padx=6)
        ttk.Label(grid, text="Diretor de Arte").grid(row=4, column=0, sticky="w", pady=3)
        ttk.Combobox(grid, textvariable=self.art_director, values=["standard", "strict", "off"], state="readonly", width=16).grid(row=4, column=1, sticky="w", padx=6)
        ttk.Label(grid, text="Fonte YouTube").grid(row=5, column=0, sticky="w", pady=3)
        ttk.Combobox(grid, textvariable=self.youtube_mode, values=["off", "cc", "authorized", "both"], state="readonly", width=16).grid(row=5, column=1, sticky="w", padx=6)
        ttk.Checkbutton(settings, text="Gerar e incluir legendas", variable=self.subtitles).pack(anchor="w", padx=8, pady=2)
        ttk.Checkbutton(settings, text="Usar checkpoint ao iniciar (retomada)", variable=self.resume).pack(anchor="w", padx=8, pady=2)
        ttk.Checkbutton(settings, text="Salvar checkpoints (recomendado)", variable=self.checkpoint).pack(anchor="w", padx=8, pady=2)

        auth = ttk.LabelFrame(self, text="4. Vídeo local autorizado (opcional; somente para YouTube = authorized/both)")
        auth.pack(fill="x", pady=5)
        row = ttk.Frame(auth); row.pack(fill="x", padx=8, pady=6)
        ttk.Entry(row, textvariable=self.authorized_video).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Escolher vídeo…", command=self._browse_authorized_video).pack(side="left", padx=(5, 0))
        row2 = ttk.Frame(auth); row2.pack(fill="x", padx=8, pady=(0, 6))
        ttk.Label(row2, text="URL de origem (opcional):").pack(side="left")
        ttk.Entry(row2, textvariable=self.source_url).pack(side="left", fill="x", expand=True, padx=5)
        ttk.Checkbutton(auth, text="Confirmo que tenho autorização/licença para reutilizar esse arquivo", variable=self.rights_confirmed).pack(anchor="w", padx=8, pady=(0, 6))

        controls = ttk.Frame(self); controls.pack(fill="x", pady=(7, 4))
        self.start_btn = ttk.Button(controls, text="▶  Iniciar produção", command=self._start)
        self.start_btn.pack(side="left")
        self.stop_btn = ttk.Button(controls, text="■  Cancelar execução", command=self._stop, state="disabled")
        self.stop_btn.pack(side="left", padx=6)
        ttk.Button(controls, text="Limpar log", command=self._clear_log).pack(side="left")
        ttk.Label(controls, textvariable=self.status).pack(side="left", padx=12)

        log_frame = ttk.LabelFrame(self, text="Progresso e mensagens do programa")
        log_frame.pack(fill="both", expand=True, pady=(4, 0))
        self.log_text = tk.Text(log_frame, height=15, wrap="word", state="disabled", font=("Consolas", 9), background="#101418", foreground="#e4e8eb", insertbackground="white")
        scroll = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scroll.set)
        self.log_text.pack(side="left", fill="both", expand=True, padx=(6, 0), pady=6)
        scroll.pack(side="right", fill="y", padx=(0, 6), pady=6)
        self._update_mode()
        self._load_xtts_reference_from_config()
        self._update_tts_controls()
        self._refresh_projects()

    def _update_mode(self) -> None:
        script_mode = self.mode.get() == "script"
        self.topic_entry.configure(state="disabled" if script_mode else "normal")
        self.duration_entry.configure(state="disabled" if script_mode else "normal")

    def _browse_project(self) -> None:
        p = filedialog.askdirectory(title="Selecione a pasta que contém agent.py", initialdir=self.project_dir.get() or str(Path.home()))
        if p:
            self.project_dir.set(p)
            self._load_xtts_reference_from_config()

    def _load_xtts_reference_from_config(self) -> None:
        """Preenche o áudio-base a partir do config.yaml, se o arquivo existir."""
        if self.xtts_reference.get().strip() and Path(self.xtts_reference.get()).is_file():
            return
        project = Path(self.project_dir.get()).expanduser()
        config = project / "config.yaml"
        configured = ""
        try:
            try:
                import yaml  # type: ignore
                with config.open("r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                configured = str((data.get("tts") or {}).get("xtts_speaker_wav") or "")
            except ImportError:
                # Fallback simples para instalações sem PyYAML no ambiente da GUI.
                import re
                if config.is_file():
                    match = re.search(r"(?m)^\s*xtts_speaker_wav\s*:\s*['\"]?([^#\r\n'\"]+)", config.read_text(encoding="utf-8"))
                    if match:
                        configured = match.group(1).strip()
        except Exception:
            configured = ""
        candidates = []
        if configured:
            cp = Path(configured).expanduser()
            candidates.extend([cp] if cp.is_absolute() else [project / cp, project.parent / cp])
        candidates.extend([project / "voice" / "xtts" / "ale.wav", project.parent / "voice" / "xtts" / "ale.wav"])
        for candidate in candidates:
            if candidate.is_file():
                self.xtts_reference.set(str(candidate.resolve()))
                return

    def _browse_xtts_reference(self) -> None:
        start = self.project_dir.get() or str(Path.home())
        p = filedialog.askopenfilename(
            title="Selecione o áudio da sua voz para clonagem XTTS",
            initialdir=start,
            filetypes=[("Áudio WAV (recomendado)", "*.wav"), ("Todos os arquivos", "*.*")],
        )
        if p:
            self.xtts_reference.set(str(Path(p).expanduser().resolve()))

    def _update_tts_controls(self, _event=None) -> None:
        is_xtts = self.tts_engine.get().strip().lower() in ("xtts", "xtts-v2", "xtts_v2", "clone")
        state = "normal" if is_xtts else "disabled"
        self.xtts_reference_entry.configure(state=state)
        self.xtts_reference_button.configure(state=state)
        self.voice_combo.configure(state="disabled" if is_xtts else "normal")

    def _browse_script(self) -> None:
        p = filedialog.askopenfilename(title="Selecione o roteiro", filetypes=[("Arquivos de texto", "*.txt"), ("Todos os arquivos", "*.*")], initialdir=self.project_dir.get())
        if p:
            self.script_path.set(p); self.mode.set("script"); self._update_mode()

    def _browse_authorized_video(self) -> None:
        p = filedialog.askopenfilename(title="Selecione um arquivo de vídeo autorizado", filetypes=[("Vídeos", "*.mp4 *.mkv *.mov *.webm *.avi"), ("Todos os arquivos", "*.*")], initialdir=self.project_dir.get())
        if p: self.authorized_video.set(p)

    def _root_dir(self) -> Path:
        """ROOT_DIR do agent.py: a pasta pai da pasta que contém agent.py."""
        return Path(self.project_dir.get()).expanduser().resolve().parent

    @staticmethod
    def _slugify(value: str) -> str:
        clean = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
        clean = re.sub(r"[^\w\s-]", "", clean).strip().lower()
        clean = re.sub(r"[-\s]+", "_", clean)
        return clean[:45] or "documentario"

    def _project_slug_from_current_input(self) -> str | None:
        if self.mode.get() == "topic":
            topic = self.topic.get().strip()
            return self._slugify(topic) if topic else None
        raw = self.script_path.get().strip()
        if not raw:
            return None
        script = Path(raw).expanduser()
        if not script.is_file():
            return None
        slug = self._slugify(script.stem)
        if slug in ("roteiro", "roteiros"):
            try:
                first_line = next((line.strip() for line in script.read_text(encoding="utf-8-sig").splitlines() if line.strip()), "")
                if first_line:
                    slug = self._slugify(first_line)
            except Exception:
                pass
        return slug

    def _refresh_projects(self) -> None:
        try:
            projects_dir = self._root_dir() / "projetos"
            projects_dir.mkdir(parents=True, exist_ok=True)
            # Lista todos os workspaces, inclusive projetos que falharam antes
            # do primeiro checkpoint (estes podem ser excluídos, mas não retomados).
            names = sorted(p.name for p in projects_dir.iterdir() if p.is_dir())
            self.project_combo["values"] = names
            current = self.project_choice.get()
            if current not in names:
                self.project_choice.set(names[0] if names else "")
            self._append_log(f"[GUI] Pastas de projeto encontradas: {len(names)}\n")
        except Exception as exc:
            self._append_log(f"[GUI] Não foi possível listar projetos: {exc}\n")

    def _resume_selected(self) -> None:
        if self.proc and self.proc.poll() is None:
            messagebox.showwarning("Produção em andamento", "Cancele ou aguarde a produção atual antes de retomar outro projeto.")
            return
        slug = self.project_choice.get().strip()
        if not slug:
            messagebox.showinfo("Retomar produção", "Não há projeto selecionado com checkpoint salvo.")
            return
        root = self._root_dir()
        project_path = (root / "projetos" / slug).resolve()
        checkpoint = project_path / "ckpts" / "last_run.json"
        if not checkpoint.is_file():
            messagebox.showerror("Checkpoint não encontrado", f"Não existe checkpoint para o projeto selecionado:\n{checkpoint}")
            self._refresh_projects()
            return

        # Prefere o roteiro correspondente em ROOT_DIR/roteiros, pois esse é o
        # local padrão do pipeline. Isso também permite retomar projetos criados por tema.
        candidate = root / "roteiros" / f"{slug}.txt"
        if candidate.is_file():
            self.script_path.set(str(candidate.resolve()))
            self.mode.set("script")
            self._update_mode()
        elif self._project_slug_from_current_input() != slug:
            messagebox.showwarning(
                "Selecione o roteiro original",
                "Para retomar com segurança, selecione o mesmo roteiro usado na produção original "
                "ou informe o mesmo tema.\n\n"
                f"Projeto selecionado: {slug}\n"
                "Não encontrei automaticamente um roteiro correspondente em ROOT_DIR/roteiros."
            )
            return

        self.resume.set(True)
        self.checkpoint.set(True)
        self._append_log(f"[GUI] Retomada solicitada para o projeto '{slug}' a partir do checkpoint.\n")
        self._start()

    def _delete_selected_project(self) -> None:
        if self.proc and self.proc.poll() is None:
            messagebox.showwarning("Produção em andamento", "Cancele ou aguarde a produção antes de excluir um projeto.")
            return
        slug = self.project_choice.get().strip()
        if not slug:
            messagebox.showinfo("Excluir projeto", "Selecione um projeto na lista.")
            return
        root = self._root_dir().resolve()
        projects_dir = (root / "projetos").resolve()
        target = (projects_dir / slug).resolve()
        # Proteção: somente permite remover uma pasta filha direta de ROOT_DIR/projetos.
        if target.parent != projects_dir or target == projects_dir or not target.is_dir():
            messagebox.showerror("Exclusão bloqueada", "O caminho selecionado não é uma pasta de projeto válida.")
            return
        exports_dir = (root / "saida").resolve()
        export_candidates = [
            exports_dir / f"{slug}.mp4",
            exports_dir / f"{slug}_thumbnail.jpg",
            exports_dir / f"{slug}_quality_report.json",
            exports_dir / f"{slug}_metadata.json",
        ]
        answer = messagebox.askyesno(
            "Excluir projeto permanentemente?",
            f"Será removida a pasta de trabalho deste projeto:\n{target}\n\n"
            "Também serão removidos, se existirem, o vídeo exportado e os relatórios/thumbnail "
            f"associados a '{slug}' na pasta saida.\n\n"
            "O roteiro original em roteiros NÃO será apagado. Esta ação não pode ser desfeita.\n\n"
            "Deseja continuar?"
        )
        if not answer:
            return
        try:
            shutil.rmtree(target)
            removed_exports = []
            for item in export_candidates:
                # Não segue links e só remove nomes exatos da lista acima.
                if item.is_file() and item.parent.resolve() == exports_dir:
                    item.unlink()
                    removed_exports.append(item.name)
            self._append_log(f"[GUI] Projeto '{slug}' excluído. Arquivos exportados removidos: {', '.join(removed_exports) or 'nenhum'}.\n")
            self.status.set(f"Projeto '{slug}' excluído.")
            self._refresh_projects()
        except Exception as exc:
            messagebox.showerror("Falha ao excluir projeto", f"Não foi possível excluir o projeto:\n{exc}")

    def _open_output(self) -> None:
        base = self._root_dir()
        out = base / "saida"
        target = out if out.exists() else base
        try:
            if os.name == "nt": os.startfile(str(target))  # type: ignore[attr-defined]
            elif sys.platform == "darwin": subprocess.Popen(["open", str(target)])
            else: subprocess.Popen(["xdg-open", str(target)])
        except Exception as exc:
            messagebox.showerror("Não foi possível abrir a pasta", str(exc))

    def _build_command(self) -> tuple[list[str], Path]:
        project = Path(self.project_dir.get()).expanduser().resolve()
        agent = project / "agent.py"
        if not agent.is_file(): raise ValueError(f"Não encontrei agent.py na pasta selecionada:\n{project}")
        cmd = [sys.executable, "-u", str(agent)]
        if self.mode.get() == "script":
            if not self.script_path.get().strip(): raise ValueError("Selecione um roteiro .txt ou escolha gerar roteiro por tema.")
            script = Path(self.script_path.get()).expanduser().resolve()
            if not script.is_file(): raise ValueError(f"O roteiro não existe:\n{script}")
            cmd.append(str(script))
        else:
            topic = self.topic.get().strip()
            if not topic: raise ValueError("Digite o tema do documentário.")
            try: duration = float(self.duration.get().replace(",", "."))
            except ValueError: raise ValueError("A duração deve ser um número, por exemplo 5 ou 7,5.")
            if duration <= 0: raise ValueError("A duração precisa ser maior que zero.")
            cmd.extend(["--topic", topic, "--duration", str(duration)])
        if self.channel.get().strip(): cmd.extend(["--channel", self.channel.get().strip()])
        if self.voice.get().strip(): cmd.extend(["--voice", self.voice.get().strip()])
        if self.tts_engine.get().strip(): cmd.extend(["--tts-engine", self.tts_engine.get().strip()])
        if self.tts_engine.get().strip().lower() in ("xtts", "xtts-v2", "xtts_v2", "clone"):
            reference = self.xtts_reference.get().strip()
            if not reference:
                raise ValueError("Você selecionou XTTS, mas não escolheu o áudio-base da sua voz. Clique em ‘Escolher WAV…’ e selecione uma gravação sua.")
            ref_path = Path(reference).expanduser().resolve()
            if not ref_path.is_file():
                raise ValueError(f"O áudio-base selecionado não existe:\n{ref_path}")
            if ref_path.suffix.lower() != ".wav":
                raise ValueError("Para o XTTS, selecione um arquivo .wav. Se a gravação estiver em MP3/M4A, converta-a para WAV antes.")
        if self.whisper_model.get().strip(): cmd.extend(["--whisper-model", self.whisper_model.get().strip()])
        cmd.extend(["--art-director", self.art_director.get(), "--youtube-mode", self.youtube_mode.get()])
        if self.subtitles.get(): cmd.append("--subtitles")
        else: cmd.append("--no-subtitles")
        if self.resume.get(): cmd.append("--resume")
        if not self.checkpoint.get(): cmd.append("--no-checkpoint")
        if self.youtube_mode.get() in ("authorized", "both"):
            video = self.authorized_video.get().strip()
            if not video: raise ValueError("Escolha um arquivo de vídeo local autorizado para este modo do YouTube.")
            if not Path(video).expanduser().is_file(): raise ValueError("O arquivo de vídeo selecionado não existe.")
            if not self.rights_confirmed.get(): raise ValueError("Confirme que você tem autorização/licença para reutilizar o arquivo.")
            cmd.extend(["--youtube-authorized-file", str(Path(video).expanduser().resolve()), "--youtube-rights-confirmed"])
            if self.source_url.get().strip(): cmd.extend(["--youtube-source-url", self.source_url.get().strip()])
        return cmd, project

    def _start(self) -> None:
        if self.proc and self.proc.poll() is None: return
        try: cmd, cwd = self._build_command()
        except Exception as exc:
            messagebox.showerror("Confira as configurações", str(exc)); return
        summary = " ".join(self._quote(x) for x in cmd)
        self._append_log(f"\n{'='*72}\nIniciando em: {cwd}\nComando: {summary}\n{'='*72}\n")
        self.start_btn.configure(state="disabled"); self.stop_btn.configure(state="normal")
        self.status.set("Executando pipeline…")
        child_env = os.environ.copy()
        if self.tts_engine.get().strip().lower() in ("xtts", "xtts-v2", "xtts_v2", "clone"):
            # O caminho absoluto selecionado na GUI tem prioridade sobre config.yaml.
            child_env["VF_XTTS_SPEAKER"] = str(Path(self.xtts_reference.get()).expanduser().resolve())
            # Evita que uma falha do XTTS seja silenciosamente mascarada por Edge-TTS.
            child_env["VF_XTTS_SEM_FALLBACK"] = "1"
            self._append_log("[GUI] XTTS selecionado: a narração usará o áudio-base indicado. Se o XTTS falhar, a execução exibirá erro em vez de trocar de voz silenciosamente.\n")
        self.worker = threading.Thread(target=self._run_process, args=(cmd, cwd, child_env), daemon=True)
        self.worker.start()

    @staticmethod
    def _quote(value: str) -> str:
        if any(ch.isspace() for ch in value) or '"' in value:
            return '"' + value.replace('"', '\\"') + '"'
        return value

    def _run_process(self, cmd: list[str], cwd: Path, env: dict[str, str] | None = None) -> None:
        try:
            kwargs = dict(cwd=str(cwd), env=env or os.environ.copy(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", bufsize=1)
            if os.name == "nt": kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
            self.proc = subprocess.Popen(cmd, **kwargs)  # type: ignore[arg-type]
            assert self.proc.stdout is not None
            for line in iter(self.proc.stdout.readline, ""):
                self.log_queue.put(line)
            code = self.proc.wait()
            self.log_queue.put(f"\nProcesso encerrado com código {code}.\n")
            self.log_queue.put("__DONE_OK__" if code == 0 else "__DONE_ERROR__")
        except Exception as exc:
            self.log_queue.put(f"\n[ERRO AO EXECUTAR] {exc}\n__DONE_ERROR__")

    def _drain_log_queue(self) -> None:
        try:
            while True:
                item = self.log_queue.get_nowait()
                if item == "__DONE_OK__":
                    self.start_btn.configure(state="normal"); self.stop_btn.configure(state="disabled")
                    self.status.set("Concluído. Confira os arquivos e relatórios na pasta de saída.")
                    self._refresh_projects()
                elif item == "__DONE_ERROR__":
                    self.start_btn.configure(state="normal"); self.stop_btn.configure(state="disabled")
                    self.status.set("Terminou com erro/interrupção. Leia o log acima.")
                    self._refresh_projects()
                else:
                    self._append_log(item)
        except queue.Empty:
            pass
        self.after(100, self._drain_log_queue)

    def _append_log(self, value: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", value)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _clear_log(self) -> None:
        self.log_text.configure(state="normal"); self.log_text.delete("1.0", "end"); self.log_text.configure(state="disabled")

    def _stop(self) -> None:
        proc = self.proc
        if not proc or proc.poll() is not None:
            return
        if not messagebox.askyesno(
            "Cancelar produção",
            "Deseja cancelar a produção em andamento?\n\n"
            "O checkpoint mais recente será preservado quando já tiver sido salvo, "
            "permitindo tentar retomar depois. Processos filhos como FFmpeg também serão encerrados."
        ):
            return
        self.status.set("Cancelando produção…")
        self._append_log("\n[GUI] Cancelamento solicitado; tentando encerrar o pipeline e processos filhos…\n")
        try:
            if os.name == "nt":
                # O processo foi iniciado em grupo próprio. Tenta primeiro um sinal
                # cooperativo; se não encerrar, _force_stop_process_tree fará fallback.
                try:
                    proc.send_signal(signal.CTRL_BREAK_EVENT)
                except Exception:
                    proc.terminate()
                threading.Thread(target=self._force_stop_process_tree, args=(proc,), daemon=True).start()
            else:
                proc.terminate()
        except Exception as exc:
            messagebox.showerror("Falha ao cancelar", str(exc))

    @staticmethod
    def _force_stop_process_tree(proc: subprocess.Popen) -> None:
        """Dá alguns segundos para encerrar; no Windows, mata também filhos órfãos."""
        try:
            proc.wait(timeout=5)
            return
        except subprocess.TimeoutExpired:
            pass
        if os.name == "nt" and proc.pid:
            try:
                subprocess.run(
                    ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    timeout=10, check=False,
                )
                return
            except Exception:
                pass
        try:
            proc.kill()
        except Exception:
            pass

    def _on_close(self) -> None:
        if self.proc and self.proc.poll() is None:
            if not messagebox.askyesno("Produção em andamento", "O pipeline ainda está rodando. Fechar a interface não é recomendado. Deseja fechar mesmo assim?"):
                return
        self.destroy()


def main() -> None:
    try:
        app = VideoFactoryGUI()
        app.mainloop()
    except Exception as exc:
        try: messagebox.showerror("VideoFactoryAI", str(exc))
        except Exception: print(exc, file=sys.stderr)
        raise


if __name__ == "__main__":
    main()
