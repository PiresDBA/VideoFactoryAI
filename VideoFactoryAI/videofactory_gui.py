#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Interface gráfica do VideoFactoryAI.

A GUI é uma camada de controle: chama agent.py como subprocesso, não duplica
nem altera a lógica do pipeline. Execute a partir da pasta do projeto.
"""
from __future__ import annotations

import json
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
MEDIA_SOURCE_MODES = (
    ("local_only", "Somente biblioteca local"),
    ("local_then_online", "Biblioteca local → internet / WebChat"),
    ("webchat_only", "Somente WebChat (geração por navegador)"),
    ("internet_images", "Somente imagens da internet (bancos/Openverse)"),
)


class VideoFactoryGUI(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1500x960")
        self.minsize(1120, 720)
        self.configure(padx=14, pady=12)
        self._apply_theme()
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
        self.image_provider = tk.StringVar(value="gemini")
        self.authorized_video = tk.StringVar()
        self.source_url = tk.StringVar()
        self.rights_confirmed = tk.BooleanVar(value=False)
        self.subtitle_mode = tk.StringVar(value="burn")
        self.resume = tk.BooleanVar(value=True)
        self.checkpoint = tk.BooleanVar(value=True)
        self.reuse_audio = tk.BooleanVar(value=True)
        self.reuse_approved_images = tk.BooleanVar(value=True)
        self.revalidate_images = tk.BooleanVar(value=False)
        self.force_regeneration = tk.BooleanVar(value=False)
        self.gemini_only = tk.BooleanVar(value=False)
        self.web_research_before_generation = tk.BooleanVar(value=True)
        self.prefer_real_media = tk.BooleanVar(value=True)
        self.gemini_fallback = tk.BooleanVar(value=True)
        self.debug_verbose = tk.BooleanVar(value=True)
        self.ignore_cache = tk.BooleanVar(value=False)
        self.review_local_media = tk.BooleanVar(value=True)
        self.media_source_mode = tk.StringVar(value="local_only")
        self.media_source_display = tk.StringVar(value="Somente biblioteca local")
        self.local_media_folder = tk.StringVar(value="")
        self._local_media_folder_manual = False
        self.min_local_images = tk.StringVar(value="0")
        self.status = tk.StringVar(value="Pronto para configurar uma produção.")
        self.proc: subprocess.Popen | None = None
        self.log_queue: queue.Queue[str] = queue.Queue()
        self.worker: threading.Thread | None = None
        self._build_ui()
        self._load_media_source_settings()
        self.after(100, self._drain_log_queue)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _apply_theme(self) -> None:
        """Apply a consistent dark studio theme without changing widget behavior."""
        palette = {
            "bg": "#101820", "panel": "#17232d", "field": "#0d151c",
            "text": "#edf4f7", "muted": "#a7bac2", "accent": "#16a085",
            "accent_active": "#12806b", "border": "#344752",
        }
        self.palette = palette
        self.configure(background=palette["bg"])
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TFrame", background=palette["bg"])
        style.configure("Card.TFrame", background=palette["panel"])
        style.configure("TLabel", background=palette["bg"], foreground=palette["text"], font=("Segoe UI", 9))
        style.configure("TLabelframe", background=palette["panel"], foreground=palette["text"], bordercolor=palette["border"], relief="solid", padding=8)
        style.configure("TLabelframe.Label", background=palette["panel"], foreground="#67d7bd", font=("Segoe UI Semibold", 10))
        style.configure("TButton", background="#243540", foreground=palette["text"], bordercolor=palette["border"], padding=(10, 7), font=("Segoe UI Semibold", 9))
        style.map("TButton", background=[("active", palette["accent_active"]), ("pressed", palette["accent"])], foreground=[("disabled", palette["muted"])])
        style.configure("TEntry", fieldbackground=palette["field"], foreground=palette["text"], insertcolor=palette["text"], bordercolor=palette["border"], padding=5)
        style.configure("TCombobox", fieldbackground=palette["field"], foreground=palette["text"], arrowcolor=palette["text"], bordercolor=palette["border"], padding=4)
        style.map("TCombobox", fieldbackground=[("readonly", palette["field"])], foreground=[("readonly", palette["text"])], selectbackground=[("readonly", palette["accent"])], selectforeground=[("readonly", "white")])
        style.configure("TRadiobutton", background=palette["panel"], foreground=palette["text"])
        style.map("TRadiobutton", background=[("active", palette["panel"])])
        style.configure("TCheckbutton", background=palette["panel"], foreground=palette["text"])
        style.map("TCheckbutton", background=[("active", palette["panel"])])
        style.configure("Vertical.TScrollbar", background="#344752", troughcolor=palette["field"], bordercolor=palette["field"])

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        header = ttk.Frame(self)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        ttk.Label(header, text="VideoFactoryAI", font=("Segoe UI", 22, "bold"), foreground="#67d7bd").pack(anchor="w")
        ttk.Label(header, text="Estúdio de produção  /  configure à esquerda, acompanhe a execução à direita", foreground=self.palette["muted"]).pack(anchor="w", pady=(1, 0))

        split = ttk.Panedwindow(self, orient="horizontal")
        split.grid(row=1, column=0, sticky="nsew")
        left_host = ttk.Frame(split)
        right = ttk.Frame(split)
        split.add(left_host, weight=5)
        split.add(right, weight=6)

        # A coluna de configuração pode conter mais opções do que a altura da
        # janela. Ela rola independentemente do monitor, sem esconder ações.
        left_canvas = tk.Canvas(
            left_host, background=self.palette["bg"], highlightthickness=0,
            borderwidth=0, yscrollincrement=24,
        )
        left_scroll = ttk.Scrollbar(left_host, orient="vertical", command=left_canvas.yview)
        left_canvas.configure(yscrollcommand=left_scroll.set)
        left_scroll.pack(side="right", fill="y")
        left_canvas.pack(side="left", fill="both", expand=True)
        left = ttk.Frame(left_canvas)
        left_window = left_canvas.create_window((0, 0), window=left, anchor="nw")

        def sync_left_scroll(_event=None) -> None:
            left_canvas.configure(scrollregion=left_canvas.bbox("all"))

        def resize_left_content(event) -> None:
            left_canvas.itemconfigure(left_window, width=event.width)

        left.bind("<Configure>", sync_left_scroll)
        left_canvas.bind("<Configure>", resize_left_content)
        left_canvas.bind("<MouseWheel>", lambda event: left_canvas.yview_scroll(-int(event.delta / 120), "units"))

        project = ttk.LabelFrame(left, text="1. Pasta do projeto")
        project.pack(fill="x", pady=(0, 5))
        ttk.Entry(project, textvariable=self.project_dir).pack(side="left", fill="x", expand=True, padx=8, pady=8)
        ttk.Button(project, text="Escolher pasta…", command=self._browse_project).pack(side="left", padx=(0, 8), pady=8)
        ttk.Button(project, text="Abrir saída", command=self._open_output).pack(side="left", padx=(0, 8), pady=8)

        # Gerenciador explícito de projetos interrompidos: retomar checkpoint ou
        # remover somente os artefatos daquele projeto, nunca o roteiro de origem.
        manage = ttk.LabelFrame(left, text="Projetos existentes / produções interrompidas")
        manage.pack(fill="x", pady=(0, 7))
        manage_select = ttk.Frame(manage)
        manage_select.pack(fill="x", padx=8, pady=(5, 2))
        ttk.Label(manage_select, text="Projeto:").pack(side="left", padx=(0, 4))
        self.project_choice = tk.StringVar(value="")
        self.project_combo = ttk.Combobox(manage_select, textvariable=self.project_choice, state="readonly", width=24)
        self.project_combo.pack(side="left", fill="x", expand=True, padx=(0, 5))
        ttk.Button(manage_select, text="Atualizar", command=self._refresh_projects).pack(side="left")
        manage_actions = ttk.Frame(manage)
        manage_actions.pack(fill="x", padx=8, pady=(2, 6))
        self.resume_btn = ttk.Button(manage_actions, text="↻ Retomar projeto", command=self._resume_selected)
        self.resume_btn.pack(side="left")
        self.delete_btn = ttk.Button(manage_actions, text="Excluir projeto…", command=self._delete_selected_project)
        self.delete_btn.pack(side="left", padx=5)

        main = ttk.Frame(left)
        main.pack(fill="x", pady=(0, 5))
        source = ttk.LabelFrame(main, text="2. Entrada do documentário")
        source.pack(fill="both", expand=True, padx=(0, 0), pady=(0, 5))
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

        media_sources = ttk.LabelFrame(main, text="3. Origem das imagens")
        media_sources.pack(fill="x", pady=(0, 6))
        source_modes = MEDIA_SOURCE_MODES
        ttk.Label(media_sources, text="Estratégia de busca").grid(
            row=0, column=0, sticky="w", padx=6, pady=(5, 3)
        )
        self.media_source_combo = ttk.Combobox(
            media_sources,
            textvariable=self.media_source_display,
            values=[label for _, label in source_modes],
            state="readonly",
            width=42,
        )
        self.media_source_labels = {key: label for key, label in source_modes}
        self.media_source_by_label = {label: key for key, label in source_modes}
        self.media_source_combo.set(self.media_source_labels[self.media_source_mode.get()])
        self.media_source_combo.grid(row=0, column=1, sticky="ew", padx=6, pady=(5, 3))
        self.media_source_combo.bind("<<ComboboxSelected>>", self._select_media_source_mode)
        ttk.Label(media_sources, text="Pasta da biblioteca local").grid(
            row=1, column=0, sticky="w", padx=6, pady=3
        )
        local_folder_row = ttk.Frame(media_sources)
        local_folder_row.grid(row=1, column=1, sticky="ew", padx=6, pady=3)
        ttk.Entry(
            local_folder_row,
            textvariable=self.local_media_folder,
        ).pack(side="left", fill="x", expand=True)
        ttk.Button(
            local_folder_row,
            text="Escolher pasta…",
            command=self._browse_local_media_folder,
        ).pack(side="left", padx=(5, 0))
        ttk.Label(media_sources, text="Mínimo de imagens locais únicas").grid(
            row=2, column=0, sticky="w", padx=6, pady=3
        )
        ttk.Entry(
            media_sources,
            textvariable=self.min_local_images,
            width=10,
        ).grid(row=2, column=1, sticky="w", padx=6, pady=3)
        ttk.Label(media_sources, text="Mínimo de imagens locais únicas").grid(
            row=2, column=0, sticky="w", padx=6, pady=3
        )
        ttk.Entry(
            media_sources,
            textvariable=self.min_local_images,
            width=10,
        ).grid(row=2, column=1, sticky="w", padx=6, pady=3)
        
        # [NOVO] Checkbox para pular o Ollama e ir direto à seleção manual
        self.skip_ollama_manual = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            media_sources,
            text="Pular Ollama (Seleção manual direta de fotos)",
            variable=self.skip_ollama_manual
        ).grid(row=3, column=0, columnspan=2, sticky="w", padx=6, pady=(3, 3))

        ttk.Label(
            media_sources,
            text=(
                "O mínimo reparte imagens em cortes dentro das cenas. Em modo somente "
                "local, a produção falha se não atingir a quantidade. WebChat usa "
                "geradores no navegador; imagens da internet usa bancos e Openverse."
            ),
            wraplength=480,
            foreground="#9fb0c5",
        ).grid(row=4, column=0, columnspan=2, sticky="w", padx=6, pady=(1, 5))
        media_sources.columnconfigure(1, weight=1)

        settings = ttk.LabelFrame(main, text="4. Narração, validação e fontes")
        settings.pack(fill="both", expand=True, padx=0)
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
        ttk.Label(settings, text="CC só baixa vídeo com licença reutilizável explícita; 'authorized' usa arquivo local autorizado.", wraplength=470, foreground="#9fb0c5").pack(anchor="w", padx=8, pady=(0, 5))
        subtitles = ttk.LabelFrame(settings, text="Saída da produção")
        subtitles.pack(fill="x", padx=8, pady=(3, 5))
        ttk.Radiobutton(
            subtitles, text="Gerar SRT e incluir no vídeo",
            variable=self.subtitle_mode, value="burn",
        ).pack(anchor="w", padx=6, pady=1)
        ttk.Radiobutton(
            subtitles, text="Gerar somente SRT da narração existente (sem refazer o vídeo)",
            variable=self.subtitle_mode, value="srt_only",
        ).pack(anchor="w", padx=6, pady=1)
        ttk.Label(
            subtitles,
            text="Este modo não gera voz e exige uma narração MP3 já existente; a voz selecionada não é usada.",
            wraplength=460,
            foreground="#f3c969",
        ).pack(anchor="w", padx=6, pady=(1, 3))
        ttk.Radiobutton(
            subtitles, text="Não gerar legendas",
            variable=self.subtitle_mode, value="none",
        ).pack(anchor="w", padx=6, pady=1)
        ttk.Radiobutton(
            subtitles, text="Gerar somente narração MP3 (sem legenda nem vídeo)",
            variable=self.subtitle_mode, value="audio_only",
        ).pack(anchor="w", padx=6, pady=1)
        ttk.Label(
            subtitles, text="Nesta versão, o arquivo separado é gerado em português (PT-BR).",
            foreground="#9fb0c5",
        ).pack(anchor="w", padx=6, pady=(1, 3))
        ttk.Checkbutton(settings, text="Usar checkpoint ao iniciar (retomada)", variable=self.resume).pack(anchor="w", padx=8, pady=2)
        ttk.Checkbutton(settings, text="Salvar checkpoints (recomendado)", variable=self.checkpoint).pack(anchor="w", padx=8, pady=2)
        resume_options = ttk.LabelFrame(settings, text="Retomada e estratégia de mídia")
        resume_options.pack(fill="x", padx=8, pady=(6, 4))
        option_checks = [
            ("Continuar de onde parou (resume)", self.resume),
            ("Reutilizar narração se o roteiro não mudou", self.reuse_audio),
            ("Reutilizar imagens aprovadas", self.reuse_approved_images),
            ("Revalidar imagens existentes", self.revalidate_images),
            ("Forçar nova busca/geração de mídia", self.force_regeneration),
            ("Somente Gemini para geração", self.gemini_only),
            ("Pesquisar na web antes de gerar imagens IA", self.web_research_before_generation),
            ("Web primeiro (mídia real antes de IA)", self.prefer_real_media),
            ("Fallback para Gemini", self.gemini_fallback),
            ("Debug detalhado", self.debug_verbose),
            ("Ignorar cache de mídia", self.ignore_cache),
            ("Revisar imagens locais abaixo do limiar", self.review_local_media),
        ]
        for index, (label, variable) in enumerate(option_checks):
            ttk.Checkbutton(
                resume_options,
                text=label,
                variable=variable,
                command=self._sync_image_reuse_options,
            ).grid(row=index // 2, column=index % 2, sticky="w", padx=6, pady=2)
        resume_options.columnconfigure(0, weight=1)
        resume_options.columnconfigure(1, weight=1)
        provider_panel = ttk.LabelFrame(settings, text="Acesso e calibração dos provedores de imagem")
        provider_panel.pack(fill="x", padx=8, pady=(7, 8))
        ttk.Label(provider_panel, text="Provedor").grid(row=0, column=0, sticky="w", padx=(2, 6), pady=(2, 5))
        provider_options = [
            ("gemini", "Gemini"), ("dreamina", "CapCut Dreamina"),
            ("copilot", "Copilot"), ("chatgpt", "ChatGPT"),
            ("grok", "Grok"), ("qwen", "Qwen"),
            ("google_ai_studio", "Google AI Studio"),
        ]
        self.provider_labels = {key: label for key, label in provider_options}
        self.provider_by_label = {label: key for key, label in provider_options}
        self.provider_combo = ttk.Combobox(
            provider_panel, state="readonly", width=24,
            values=[label for _, label in provider_options],
        )
        self.provider_combo.set(self.provider_labels[self.image_provider.get()])
        self.provider_combo.grid(row=0, column=1, sticky="ew", pady=(2, 5))
        self.provider_combo.bind("<<ComboboxSelected>>", self._select_image_provider)
        provider_panel.columnconfigure(1, weight=1)
        actions = ttk.Frame(provider_panel); actions.grid(row=1, column=0, columnspan=2, sticky="ew")
        ttk.Button(actions, text="1. Abrir login", command=self._open_image_provider_login).pack(side="left", padx=(0, 5))
        ttk.Button(actions, text="2. Calibrar selecionado", command=self._calibrate_selected_image_provider).pack(side="left")
        ttk.Label(
            provider_panel,
            text="Abra o login, entre na conta e feche somente a janela do navegador. Em seguida calibre. O resultado fica registrado no monitor à direita.",
            wraplength=470, foreground=self.palette["muted"],
        ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(6, 0))

        auth = ttk.LabelFrame(left, text="4. Vídeo local autorizado (opcional)")
        auth.pack(fill="x", pady=(3, 0))
        ttk.Label(auth, text="Usado nos modos YouTube authorized/both", foreground=self.palette["muted"]).pack(anchor="w", padx=8, pady=(0, 2))
        row = ttk.Frame(auth); row.pack(fill="x", padx=8, pady=6)
        ttk.Entry(row, textvariable=self.authorized_video).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Escolher vídeo…", command=self._browse_authorized_video).pack(side="left", padx=(5, 0))
        row2 = ttk.Frame(auth); row2.pack(fill="x", padx=8, pady=(0, 6))
        ttk.Label(row2, text="URL de origem (opcional):").pack(side="left")
        ttk.Entry(row2, textvariable=self.source_url).pack(side="left", fill="x", expand=True, padx=5)
        ttk.Checkbutton(auth, text="Confirmo que tenho autorização/licença para reutilizar esse arquivo", variable=self.rights_confirmed).pack(anchor="w", padx=8, pady=(0, 6))

        controls = ttk.Frame(right); controls.pack(fill="x", pady=(0, 7))
        self.start_btn = ttk.Button(controls, text="▶  Iniciar produção", command=self._start)
        self.start_btn.pack(side="left")
        ttk.Style(self).configure("Primary.TButton", background="#117c68", foreground="white")
        self.start_btn.configure(style="Primary.TButton")
        self.stop_btn = ttk.Button(controls, text="■  Cancelar execução", command=self._stop, state="disabled")
        self.stop_btn.pack(side="left", padx=6)
        ttk.Button(controls, text="Salvar log", command=self._save_log).pack(side="left", padx=(0, 6))
        ttk.Button(controls, text="Limpar log", command=self._clear_log).pack(side="left")
        self.status_label = ttk.Label(controls, textvariable=self.status, foreground="#67d7bd")
        self.status_label.pack(side="left", padx=12)

        log_frame = ttk.LabelFrame(right, text="Monitor da produção  ·  logs em tempo real")
        log_frame.pack(fill="both", expand=True)
        self.log_text = tk.Text(log_frame, height=24, wrap="word", state="disabled", font=("Cascadia Mono", 10), background=self.palette["field"], foreground="#dce8ec", insertbackground="white", relief="flat", padx=12, pady=10, spacing1=2, spacing3=2, selectbackground="#176b5d")
        self.log_text.tag_configure("info", foreground="#b8c8ce")
        self.log_text.tag_configure("success", foreground="#67d7a8")
        self.log_text.tag_configure("warning", foreground="#f3c969")
        self.log_text.tag_configure("error", foreground="#ff817c")
        self.log_text.tag_configure("stage", foreground="#67d7bd", font=("Cascadia Mono", 10, "bold"))
        scroll = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scroll.set)
        self.log_text.pack(side="left", fill="both", expand=True, padx=(7, 0), pady=7)
        scroll.pack(side="right", fill="y", padx=(0, 7), pady=7)
        self._update_mode()
        self._load_xtts_reference_from_config()
        self._update_tts_controls()
        self._refresh_projects()

    def _update_mode(self) -> None:
        script_mode = self.mode.get() == "script"
        self.topic_entry.configure(state="disabled" if script_mode else "normal")
        self.duration_entry.configure(state="disabled" if script_mode else "normal")

    def _select_image_provider(self, _event=None) -> None:
        self.image_provider.set(self.provider_by_label.get(self.provider_combo.get(), "gemini"))

    def _open_image_provider_login(self) -> None:
        if self.proc and self.proc.poll() is None:
            messagebox.showinfo("Login indisponível", "Aguarde a produção atual terminar antes de abrir um perfil de navegador.")
            return
        provider = self.image_provider.get()
        label = self.provider_labels.get(provider, provider)
        self._append_log(f"\n[Login {label}] Abrindo navegador. Faça login e feche a janela do navegador quando terminar; a sessão ficará salva neste computador.\n")

        def run() -> None:
            try:
                from web_image_providers import open_image_provider_login
                result = open_image_provider_login(provider)
                state = "OK" if result.get("ok") else "FALHOU"
                self.log_queue.put(f"[Login {label}] {state}: {result.get('message', 'sem detalhes')}\n")
            except Exception as exc:
                self.log_queue.put(f"[Login {label}] FALHOU: {exc}\n")

        threading.Thread(target=run, name=f"login-{provider}", daemon=True).start()

    def _calibrate_selected_image_provider(self) -> None:
        provider = self.image_provider.get()
        self._calibrate_image_provider(provider)

    def _calibrate_image_provider(self, provider: str) -> None:
        if self.proc and self.proc.poll() is None:
            messagebox.showinfo("Calibração indisponível", "Aguarde a produção atual terminar antes de calibrar um perfil de navegador.")
            return
        label = self.provider_labels.get(provider, provider)
        self._append_log(f"\n[Calibração {label}] Verificando a sessão salva por até 30 segundos. A calibração não gera imagem nem consome crédito.\n")

        def run() -> None:
            try:
                from web_image_providers import calibrate_image_provider
                result = calibrate_image_provider(provider, login_wait_seconds=30)
                state = "OK" if result.get("ok") else "FALHOU"
                self.log_queue.put(f"[Calibração {label}] {state}: {result.get('message', 'sem detalhes')}\n")
            except Exception as exc:
                self.log_queue.put(f"[Calibração {label}] FALHOU: {exc}\n")

        threading.Thread(target=run, name=f"calibrar-{provider}", daemon=True).start()

    def _browse_project(self) -> None:
        p = filedialog.askdirectory(title="Selecione a pasta que contém agent.py", initialdir=self.project_dir.get() or str(Path.home()))
        if p:
            self.project_dir.set(p)
            self._load_xtts_reference_from_config()
            if not self._local_media_folder_manual:
                self._load_media_source_settings()

    def _select_media_source_mode(self, _event=None) -> None:
        selected = self.media_source_display.get()
        mode = self.media_source_by_label.get(selected)
        if mode is not None:
            self.media_source_mode.set(mode)

    def _load_media_source_settings(self) -> None:
        """Carrega o modo e a biblioteca de imagens definidos no config.yaml."""
        project = Path(self.project_dir.get()).expanduser()
        config_path = project / "config.yaml"
        data = {}
        if config_path.is_file():
            try:
                import yaml  # type: ignore
            except ImportError:
                import re
                try:
                    config_text = config_path.read_text(encoding="utf-8")
                except OSError as exc:
                    self._append_log(f"[GUI] Não foi possível ler {config_path}: {exc}\n")
                    return
                media_section = re.search(
                    r"(?ms)^media\s*:\s*\n((?:^[ \t]+.*\n?)*)",
                    config_text,
                )
                if media_section:
                    for key in (
                        "media_source_mode",
                        "local_media_mode",
                        "local_media_folder",
                        "min_local_images",
                    ):
                        match = re.search(
                            rf"(?m)^\s+{key}\s*:\s*['\"]?([^#\r\n'\"]+)",
                            media_section.group(1),
                        )
                        if match:
                            data.setdefault("media", {})[key] = match.group(1).strip()
            else:
                try:
                    with config_path.open("r", encoding="utf-8") as config_file:
                        data = yaml.safe_load(config_file) or {}
                except (OSError, yaml.YAMLError) as exc:
                    self._append_log(f"[GUI] Configuração de mídia inválida em {config_path}: {exc}\n")
                    return

        if not isinstance(data, dict):
            self._append_log(f"[GUI] A configuração de mídia em {config_path} deve ser um objeto YAML.\n")
            return
        media_cfg = data.get("media") or {}
        if not isinstance(media_cfg, dict):
            self._append_log(f"[GUI] A seção media em {config_path} deve ser um objeto YAML.\n")
            return
        configured_mode = str(media_cfg.get("media_source_mode") or "").strip()
        if not configured_mode:
            legacy_mode = str(media_cfg.get("local_media_mode", "required")).strip().lower()
            configured_mode = {
                "required": "local_only",
                "prefer": "local_then_online",
                "off": "local_then_online",
            }.get(legacy_mode, "local_only")
        if configured_mode in self.media_source_labels:
            self.media_source_mode.set(configured_mode)
            self.media_source_display.set(self.media_source_labels[configured_mode])

        configured_folder = str(media_cfg.get("local_media_folder") or "").strip()
        folder = Path(configured_folder).expanduser() if configured_folder else Path("biblioteca_local")
        if not folder.is_absolute():
            slug = self._project_slug_from_current_input()
            if not slug:
                project_choice = self.__dict__.get("project_choice")
                slug = project_choice.get().strip() if project_choice is not None else ""
            if slug:
                folder = self._root_dir() / "projetos" / slug / folder
            else:
                folder = project.parent / folder
        self.local_media_folder.set(str(folder.resolve()))
        self._local_media_folder_manual = False
        min_local_images = media_cfg.get("min_local_images", 0)
        self.min_local_images.set(str(min_local_images))

    def _browse_local_media_folder(self) -> None:
        current = self.local_media_folder.get().strip()
        initial_dir = current if current and Path(current).is_dir() else str(self._root_dir())
        selected = filedialog.askdirectory(
            title="Selecione a pasta da biblioteca local de imagens",
            initialdir=initial_dir,
        )
        if selected:
            self.local_media_folder.set(str(Path(selected).expanduser().resolve()))
            self._local_media_folder_manual = True

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

    def _sync_image_reuse_options(self) -> None:
        if self.revalidate_images.get():
            self.reuse_approved_images.set(False)
        elif self.reuse_approved_images.get():
            self.revalidate_images.set(False)

    def _browse_script(self) -> None:
        scripts_dir = self._root_dir() / "roteiros"
        initial_dir = scripts_dir if scripts_dir.is_dir() else self._root_dir()
        p = filedialog.askopenfilename(
            title="Selecione o roteiro",
            filetypes=[("Arquivos de texto", "*.txt"), ("Todos os arquivos", "*.*")],
            initialdir=str(initial_dir),
        )
        if p:
            self.script_path.set(p); self.mode.set("script"); self._update_mode()
            if not self._local_media_folder_manual:
                self._load_media_source_settings()

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
            if self.subtitle_mode.get() == "srt_only":
                raise ValueError("Para gerar legendas sem refazer a produção, selecione o roteiro original.")
            topic = self.topic.get().strip()
            if not topic: raise ValueError("Digite o tema do documentário.")
            try: duration = float(self.duration.get().replace(",", "."))
            except ValueError: raise ValueError("A duração deve ser um número, por exemplo 5 ou 7,5.")
            if duration <= 0: raise ValueError("A duração precisa ser maior que zero.")
            cmd.extend(["--topic", topic, "--duration", str(duration)])
        subtitle_mode = self.subtitle_mode.get()
        if subtitle_mode == "srt_only":
            cmd.append("--subtitles-only")
            if self.whisper_model.get().strip():
                cmd.extend(["--whisper-model", self.whisper_model.get().strip()])
            return cmd, project
        audio_only = subtitle_mode == "audio_only"
        if audio_only:
            cmd.append("--audio-only")
        media_source_setting = self.__dict__.get("media_source_mode")
        if not audio_only and media_source_setting is not None:
            selected_mode = media_source_setting.get()
            label_to_mode = {label: mode for mode, label in MEDIA_SOURCE_MODES}
            media_source_mode = label_to_mode.get(selected_mode, selected_mode)
            valid_modes = {mode for mode, _label in MEDIA_SOURCE_MODES}
            if media_source_mode not in valid_modes:
                raise ValueError(
                    f"Estratégia de origem de imagens inválida: {selected_mode}"
                )
            local_folder_setting = self.__dict__.get("local_media_folder")
            local_folder_value = (
                local_folder_setting.get().strip()
                if local_folder_setting is not None
                else ""
            )
            uses_local_library = media_source_mode in {
                "local_only", "local_then_online"
            }
            if uses_local_library and not local_folder_value:
                raise ValueError(
                    "O modo selecionado exige a pasta da biblioteca local. "
                    "Escolha a pasta da biblioteca local."
                )
            minimum_setting = self.__dict__.get("min_local_images")
            if uses_local_library and minimum_setting is not None:
                raw_minimum = minimum_setting.get().strip()
                try:
                    minimum_local_images = int(raw_minimum or "0")
                except ValueError as exc:
                    raise ValueError(
                        "O mínimo de imagens locais deve ser um número inteiro."
                    ) from exc
                if minimum_local_images < 0:
                    raise ValueError(
                        "O mínimo de imagens locais não pode ser negativo."
                    )
                if minimum_local_images:
                    cmd.extend([
                        "--min-local-images",
                        str(minimum_local_images),
                    ])
            cmd.extend(["--media-source-mode", media_source_mode])
            if local_folder_value:
                local_media_folder = Path(local_folder_value).expanduser()
                if uses_local_library and not local_media_folder.is_dir():
                    raise ValueError(
                        "A pasta da biblioteca local não existe ou não pode ser acessada:\n"
                        f"{local_media_folder}"
                    )
                cmd.extend(["--local-media-folder", str(local_media_folder.resolve())])
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
        if not audio_only and self.whisper_model.get().strip():
            cmd.extend(["--whisper-model", self.whisper_model.get().strip()])
        if not audio_only:
            cmd.extend(["--art-director", self.art_director.get(), "--youtube-mode", self.youtube_mode.get()])
        if subtitle_mode == "burn": cmd.append("--subtitles")
        elif subtitle_mode == "none": cmd.append("--no-subtitles")
        if audio_only:
            return cmd, project
        cmd.append("--resume" if self.resume.get() else "--no-resume")
        cmd.append("--reuse-existing-audio" if self.reuse_audio.get() else "--no-reuse-existing-audio")
        if self.revalidate_images.get():
            cmd.append("--revalidate-images")
        else:
            cmd.append("--reuse-approved-images" if self.reuse_approved_images.get() else "--no-reuse-approved-images")
        if self.force_regeneration.get(): cmd.append("--force-regeneration")
        cmd.append("--gemini-only" if self.gemini_only.get() else "--no-gemini-only")
        cmd.append(
            "--web-research-before-generation"
            if self.web_research_before_generation.get()
            else "--no-web-research-before-generation"
        )
        cmd.append("--prefer-real-media" if self.prefer_real_media.get() else "--no-prefer-real-media")
        cmd.append("--gemini-fallback" if self.gemini_fallback.get() else "--no-gemini-fallback")
        cmd.append("--debug" if self.debug_verbose.get() else "--no-debug")
        review_setting = self.__dict__.get("review_local_media")
        if review_setting is not None and review_setting.get():
            cmd.append("--review-local-media")
        if self.ignore_cache.get(): cmd.append("--ignore-cache")
        if not self.checkpoint.get(): cmd.append("--no-checkpoint")
        if self.skip_ollama_manual.get():
            cmd.append("--skip-ollama")
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
        if self.review_local_media.get():
            child_env["VF_LOCAL_MEDIA_REVIEW_GUI"] = "1"
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
            kwargs = dict(cwd=str(cwd), env=env or os.environ.copy(), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", bufsize=1)
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
                elif item.startswith("__LOCAL_MEDIA_REVIEW__"):
                    self._handle_local_media_review_event(item)
                else:
                    self._append_log(item)
        except queue.Empty:
            pass
        self.after(100, self._drain_log_queue)

    def _handle_local_media_review_event(self, line: str) -> None:
        marker = "__LOCAL_MEDIA_REVIEW__"
        try:
            request = json.loads(line[len(marker):])
            approved = self._show_local_media_review(request)
            if not self.proc or not self.proc.stdin:
                raise RuntimeError("O processo não está aguardando uma decisão de revisão.")
            self.proc.stdin.write("aprovar\n" if approved else "rejeitar\n")
            self.proc.stdin.flush()
        except (OSError, ValueError, RuntimeError, KeyError, tk.TclError) as exc:
            self._append_log(f"\n[ERRO] Falha na revisão manual de imagem local: {exc}\n")
            if self.proc and self.proc.poll() is None:
                self.proc.terminate()

    def _show_local_media_review(self, request: dict) -> list | str:
        from PIL import Image, ImageTk

        suggested_path = request.get("image_path", "")
        folder_path = Path(suggested_path).parent if suggested_path else Path(self.local_media_folder.get())

        all_image_files = []
        if folder_path.is_dir():
            all_image_files = sorted([
                str(p.resolve()) for p in folder_path.glob("*.*")
                if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}
            ])

        if not all_image_files and suggested_path:
            all_image_files = [suggested_path]

        if suggested_path in all_image_files:
            all_image_files.remove(suggested_path)
            all_image_files.insert(0, suggested_path)

        candidates_list = [
            {"image_path": img_path, "title": Path(img_path).name}
            for img_path in all_image_files
        ]

        current_index = {"idx": 0}
        selected_paths = []

        dialog = tk.Toplevel(self)
        dialog.title(f"Revisar/Selecionar Imagens — Cena {request['scene_id']}")
        dialog.transient(self)
        dialog.geometry("950x880")
        dialog.minsize(700, 600)
        dialog.grab_set()

        header_label = ttk.Label(dialog, font=("Segoe UI Semibold", 11), foreground="#67d7bd")
        header_label.pack(fill="x", padx=14, pady=(14, 8))

        image_label = ttk.Label(dialog, anchor="center")
        image_label.pack(fill="both", expand=True, padx=14, pady=6)

        nav_frame = ttk.Frame(dialog)
        nav_frame.pack(fill="x", padx=14, pady=5)

        def update_view():
            if not candidates_list:
                return
            idx = current_index["idx"]
            cand = candidates_list[idx]
            image_path = Path(cand["image_path"])
            
            status_sel = " [✔ SELECIONADA PARA ESTA CENA]" if str(image_path) in selected_paths else ""
            header_label.config(
                text=f"Cena {request['scene_id']} · Foto {idx + 1} de {len(candidates_list)} · "
                     f"Arquivo: {image_path.name}{status_sel}"
            )

            if image_path.is_file():
                with Image.open(image_path) as source:
                    source.thumbnail((850, 400), Image.Resampling.LANCZOS)
                    preview = source.convert("RGB")
                    photo = ImageTk.PhotoImage(preview, master=dialog)
                    image_label.configure(image=photo)
                    image_label.image = photo
            else:
                image_label.configure(image="")
                image_label.image = None

        def go_prev():
            current_index["idx"] = (current_index["idx"] - 1) % len(candidates_list)
            update_view()

        def go_next():
            current_index["idx"] = (current_index["idx"] + 1) % len(candidates_list)
            update_view()

        ttk.Button(nav_frame, text="⬅ Foto Anterior", command=go_prev).pack(side="left")
        ttk.Button(nav_frame, text="Próxima Foto ➔", command=go_next).pack(side="left", padx=10)

        # Roteiro
        ttk.Label(dialog, text="Trecho do roteiro desta cena:", font=("Segoe UI Semibold", 10)).pack(anchor="w", padx=14, pady=(8, 3))
        text_frame = ttk.Frame(dialog)
        text_frame.pack(fill="both", expand=False, padx=14, pady=(0, 8))
        scene_text = tk.Text(text_frame, height=4, wrap="word", background=self.palette["field"], foreground=self.palette["text"])
        text_scroll = ttk.Scrollbar(text_frame, orient="vertical", command=scene_text.yview)
        scene_text.configure(yscrollcommand=text_scroll.set)
        scene_text.pack(side="left", fill="both", expand=True)
        text_scroll.pack(side="right", fill="y")
        scene_text.insert("1.0", str(request.get("scene_text", "")))
        scene_text.configure(state="disabled")

        def add_current_photo():
            path_str = candidates_list[current_index["idx"]]["image_path"]
            if path_str not in selected_paths:
                selected_paths.append(path_str)
            update_view()

        def remove_current_photo():
            path_str = candidates_list[current_index["idx"]]["image_path"]
            if path_str in selected_paths:
                selected_paths.remove(path_str)
            update_view()

        add_frame = ttk.Frame(dialog)
        add_frame.pack(fill="x", padx=14, pady=5)
        ttk.Button(add_frame, text="➕ Adicionar esta foto à cena (Múltiplas)", command=add_current_photo).pack(side="left")
        ttk.Button(add_frame, text="❌ Remover esta foto da cena", command=remove_current_photo).pack(side="left", padx=10)

        actions = ttk.Frame(dialog)
        actions.pack(fill="x", padx=14, pady=(5, 14))

        def finish_selection():
            if not selected_paths and candidates_list:
                selected_paths.append(candidates_list[current_index["idx"]]["image_path"])
            dialog.destroy()

        ttk.Button(actions, text="Concluir e Usar Selecionadas ➔", command=finish_selection).pack(side="right")

        update_view()
        dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
        self.wait_window(dialog)
        return selected_paths
    
    def _append_log(self, value: str) -> None:
        self.log_text.configure(state="normal")
        for line in value.splitlines(keepends=True):
            normalized = line.upper()
            if any(marker in normalized for marker in ("[ERRO]", "FALHOU", "ERROR", "TRACEBACK", "CANCELAMENTO")):
                tag = "error"
            elif any(marker in normalized for marker in ("[OK]", "CONCLUÍDO", "CONCLUIDO", "APROVADO", "SUCESSO")):
                tag = "success"
            elif any(marker in normalized for marker in ("AVISO", "WARNING", "REPROVADO", "SEM VÍDEO", "SEM VIDEO")):
                tag = "warning"
            elif re.search(r"\[\d+/\d+\]|\[L[1-6](?:-[^]]+)?\]", normalized):
                tag = "stage"
            else:
                tag = "info"
            self.log_text.insert("end", line, tag)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _save_log(self) -> None:
        """Salva o conteúdo visível do log em arquivo UTF-8 sem limpá-lo."""
        try:
            project = Path(self.project_dir.get()).expanduser()
            logs_dir = project / "logs"
            logs_dir.mkdir(parents=True, exist_ok=True)
            base = "makete_ho.log"
            target = logs_dir / base
            index = 2
            while target.exists():
                target = logs_dir / f"makete_ho{index}.log"
                index += 1
            content = self.log_text.get("1.0", "end-1c")
            target.write_text(content, encoding="utf-8", errors="replace")
            messagebox.showinfo("Log salvo", f"Log salvo em:\n{target}")
        except Exception as exc:
            messagebox.showerror("Falha ao salvar log", f"Não foi possível salvar o log:\n{exc}")

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
