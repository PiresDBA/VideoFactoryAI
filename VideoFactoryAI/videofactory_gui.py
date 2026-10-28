#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Estúdio de Produção — interface gráfica do VideoFactoryAI.

A GUI é uma camada de controle: monta a linha de comando e executa agent.py
como subprocesso. A lógica do pipeline permanece exclusivamente em agent.py.
Execute a partir da pasta do projeto (a pasta que contém agent.py).
"""
from __future__ import annotations

import json
import os
import queue
import re
import shutil
import signal
import subprocess
import sys
import threading
import tkinter as tk
import unicodedata
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

APP_TITLE = "VideoFactoryAI — Estúdio de Produção"
FONT = "Segoe UI"
FONT_SEMI = "Segoe UI Semibold"
FONT_MONO = "Cascadia Mono"

PALETTE = {
    "bg": "#0f171c",
    "surface": "#1a2730",
    "card": "#15212a",
    "field": "#0a1116",
    "border": "#2b3d48",
    "text": "#e9f1f4",
    "muted": "#8ea4ae",
    "accent": "#1fbf9f",
    "accent_hover": "#2fd6b4",
    "accent_dark": "#15967e",
    "warn": "#f2c15c",
    "error": "#ff7b72",
    "ok": "#6fdc9c",
}

# (cor de fundo, cor do texto, rótulo) para o indicador de estado no cabeçalho.
STATE_STYLES = {
    "idle": ("#24363f", "#a9bec7", "PRONTO"),
    "running": ("#0f5d52", "#c8f7ea", "EXECUTANDO"),
    "cancelling": ("#6b4e12", "#ffe6a8", "CANCELANDO"),
    "ok": ("#1e5c3c", "#caf8dc", "CONCLUÍDO"),
    "error": ("#6a2426", "#ffd6d3", "ERRO"),
}

MEDIA_SOURCE_MODES = (
    ("local_only", "Somente biblioteca local"),
    ("local_then_online", "Biblioteca local → internet / WebChat"),
    ("webchat_only", "Somente WebChat (geração por navegador)"),
    ("internet_images", "Somente imagens da internet (bancos/Openverse)"),
)
PROVIDER_OPTIONS = (
    ("gemini", "Gemini"),
    ("dreamina", "CapCut Dreamina"),
    ("copilot", "Copilot"),
    ("chatgpt", "ChatGPT"),
    ("grok", "Grok"),
    ("qwen", "Qwen"),
    ("google_ai_studio", "Google AI Studio"),
)
STAGE_OPTIONS = (
    ("full", "Produção completa"),
    ("script", "Apenas roteiro  ·  --script-only"),
    ("images", "Apenas mídias  ·  --images-only"),
    ("render", "Apenas render  ·  --render-only"),
)
SUBTITLE_OPTIONS = (
    ("burn", "Gerar SRT e incluir no vídeo"),
    ("srt_only", "Gerar somente SRT da narração existente"),
    ("none", "Não gerar legendas"),
    ("audio_only", "Gerar somente narração MP3 (sem legenda nem vídeo)"),
)
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


class VideoFactoryGUI(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1360x860")
        self.minsize(1100, 680)
        self.configure(background=PALETTE["bg"])
        self._scrollables: list[tk.Canvas] = []
        self.bind_all("<MouseWheel>", self._on_global_wheel)
        self.bind_all("<Button-4>", self._on_global_wheel)
        self.bind_all("<Button-5>", self._on_global_wheel)
        self.bind("<Control-Return>", lambda _e: self._start())
        self._apply_theme()
        self._init_variables()
        self._build_ui()
        self._load_media_source_settings()
        self.after(100, self._drain_log_queue)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------
    # Estado (nomes de variáveis preservados: _build_command depende deles)
    # ------------------------------------------------------------------
    def _init_variables(self) -> None:
        self.project_dir = tk.StringVar(value=str(Path(__file__).resolve().parent))
        self.project_choice = tk.StringVar(value="")
        self.script_path = tk.StringVar()
        self.mode = tk.StringVar(value="script")
        self.topic = tk.StringVar()
        self.duration = tk.StringVar(value="5")
        self.channel = tk.StringVar(value="documentario")
        self.voice = tk.StringVar(value="pt-BR-AntonioNeural")
        self.tts_engine = tk.StringVar(value="edge-tts")
        self.xtts_reference = tk.StringVar(value="")
        self.whisper_model = tk.StringVar(value="base")
        self.art_director = tk.StringVar(value="standard")
        self.youtube_mode = tk.StringVar(value="cc")
        self.image_provider = tk.StringVar(value="gemini")
        self.authorized_video = tk.StringVar()
        self.source_url = tk.StringVar()
        self.rights_confirmed = tk.BooleanVar(value=False)
        self.subtitle_mode = tk.StringVar(value="burn")
        self.stage = tk.StringVar(value="full")
        self.script_only = tk.BooleanVar(value=False)
        self.images_only = tk.BooleanVar(value=False)
        self.render_only = tk.BooleanVar(value=False)
        self.prepend_text = tk.StringVar(value="")
        self.append_text = tk.StringVar(value="")
        self.skip_ollama_manual = tk.BooleanVar(value=False)
        self.resume = tk.BooleanVar(value=True)
        self.checkpoint = tk.BooleanVar(value=True)
        self.reuse_audio = tk.BooleanVar(value=True)
        self.reuse_approved_images = tk.BooleanVar(value=True)
        self.revalidate_images = tk.BooleanVar(value=False)
        self.force_regeneration = tk.BooleanVar(value=False)
        self.gemini_only = tk.BooleanVar(value=False)
        self.web_research_before_generation = tk.BooleanVar(value=False)
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

    # ------------------------------------------------------------------
    # Tema
    # ------------------------------------------------------------------
    def _apply_theme(self) -> None:
        p = PALETTE
        self.palette = p
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure(".", background=p["bg"], foreground=p["text"], font=(FONT, 9),
                        bordercolor=p["border"], focuscolor=p["accent"])
        style.configure("TFrame", background=p["bg"])
        style.configure("TLabel", background=p["bg"], foreground=p["text"], font=(FONT, 9))
        style.configure("Muted.TLabel", background=p["bg"], foreground=p["muted"], font=(FONT, 9))
        style.configure("Hint.TLabel", background=p["bg"], foreground=p["muted"], font=(FONT, 8))
        style.configure("Warn.TLabel", background=p["bg"], foreground=p["warn"], font=(FONT, 8))
        style.configure("Title.TLabel", background=p["bg"], foreground=p["accent"], font=(FONT_SEMI, 20))
        style.configure("Subtitle.TLabel", background=p["bg"], foreground=p["muted"], font=(FONT, 10))
        style.configure("Section.TLabel", background=p["bg"], foreground=p["text"], font=(FONT_SEMI, 13))
        style.configure("Count.TLabel", background=p["bg"], foreground=p["accent"], font=(FONT_SEMI, 11))

        style.configure("TLabelframe", background=p["bg"], bordercolor=p["border"], relief="solid", borderwidth=1)
        style.configure("TLabelframe.Label", background=p["bg"], foreground=p["accent"], font=(FONT_SEMI, 10))

        style.configure("TButton", background=p["surface"], foreground=p["text"], bordercolor=p["border"],
                        padding=(12, 7), font=(FONT_SEMI, 9), focusthickness=0)
        style.map("TButton",
                  background=[("disabled", p["surface"]), ("pressed", p["accent_dark"]), ("active", "#24404c")],
                  foreground=[("disabled", "#5b7079")])
        style.configure("Accent.TButton", background=p["accent"], foreground="#04221c",
                        bordercolor=p["accent"], padding=(16, 9), font=(FONT_SEMI, 10))
        style.map("Accent.TButton",
                  background=[("disabled", "#23434a"), ("pressed", p["accent_dark"]), ("active", p["accent_hover"])],
                  foreground=[("disabled", "#5b7079")])
        style.configure("Danger.TButton", foreground="#ffb1ad")

        style.configure("TEntry", fieldbackground=p["field"], foreground=p["text"],
                        insertcolor=p["text"], bordercolor=p["border"], padding=6)
        style.map("TEntry", bordercolor=[("focus", p["accent"])],
                  fieldbackground=[("disabled", "#0c1419")], foreground=[("disabled", "#5b7079")])
        style.configure("TCombobox", fieldbackground=p["field"], foreground=p["text"],
                        arrowcolor=p["text"], bordercolor=p["border"], padding=5)
        style.map("TCombobox",
                  fieldbackground=[("readonly", p["field"]), ("disabled", "#0c1419")],
                  foreground=[("readonly", p["text"]), ("disabled", "#5b7079")],
                  selectbackground=[("readonly", p["field"])],
                  selectforeground=[("readonly", p["text"])],
                  bordercolor=[("focus", p["accent"])])
        self.option_add("*TCombobox*Listbox.background", p["field"])
        self.option_add("*TCombobox*Listbox.foreground", p["text"])
        self.option_add("*TCombobox*Listbox.selectBackground", p["accent_dark"])
        self.option_add("*TCombobox*Listbox.selectForeground", "white")

        for name in ("TCheckbutton", "TRadiobutton"):
            style.configure(name, background=p["bg"], foreground=p["text"], focuscolor=p["bg"],
                            indicatorbackground=p["field"], indicatorforeground=p["accent"])
            style.map(name, background=[("active", p["bg"])],
                      indicatorbackground=[("selected", p["accent"])])

        style.configure("TNotebook", background=p["bg"], borderwidth=0)
        style.configure("TNotebook.Tab", background=p["surface"], foreground=p["muted"],
                        padding=(18, 9), font=(FONT_SEMI, 9), borderwidth=0)
        style.map("TNotebook.Tab",
                  background=[("selected", p["bg"]), ("active", "#22343e")],
                  foreground=[("selected", p["accent"])])

        style.configure("TPanedwindow", background=p["bg"])
        style.configure("Vertical.TScrollbar", background=p["border"], troughcolor=p["bg"],
                        bordercolor=p["bg"], arrowcolor=p["muted"])
        style.configure("Horizontal.TProgressbar", background=p["accent"], troughcolor=p["field"],
                        bordercolor=p["field"], lightcolor=p["accent"], darkcolor=p["accent"])

    # ------------------------------------------------------------------
    # Construção da interface
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        self._build_header()

        body = ttk.Panedwindow(self, orient="horizontal")
        body.grid(row=1, column=0, sticky="nsew", pady=(14, 10))
        left = ttk.Frame(body)
        right = ttk.Frame(body)
        body.add(left, weight=5)
        body.add(right, weight=6)
        self._build_settings(left)
        self._build_monitor(right)

        self._build_footer()
        self._update_mode()
        self._load_xtts_reference_from_config()
        self._update_tts_controls()
        self._apply_stage()
        self._refresh_projects()

    def _build_header(self) -> None:
        header = ttk.Frame(self)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        titles = ttk.Frame(header)
        titles.grid(row=0, column=0, sticky="w")
        ttk.Label(titles, text="VideoFactoryAI", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            titles,
            text="Estúdio de produção  ·  configure nas abas e acompanhe a execução à direita",
            style="Subtitle.TLabel",
        ).pack(anchor="w")
        self.pill = tk.Label(header, text="", font=(FONT_SEMI, 9), padx=14, pady=6, bd=0)
        self.pill.grid(row=0, column=1, sticky="e")
        self._set_state("idle")

    def _build_footer(self) -> None:
        footer = ttk.Frame(self)
        footer.grid(row=2, column=0, sticky="ew")
        ttk.Label(footer, textvariable=self.status, style="Muted.TLabel").pack(side="left")
        ttk.Label(footer, text="Atalho: Ctrl+Enter inicia a produção", style="Muted.TLabel").pack(side="right")

    def _build_settings(self, parent: ttk.Frame) -> None:
        self.notebook = ttk.Notebook(parent)
        self.notebook.pack(fill="both", expand=True)
        pages = (
            ("Roteiro", self._tab_script),
            ("Narração", self._tab_voice),
            ("Imagens", self._tab_images),
            ("Projetos", self._tab_projects),
            ("Avançado", self._tab_advanced),
        )
        for title, builder in pages:
            outer, inner = self._scrollable_page(self.notebook)
            builder(inner)
            self.notebook.add(outer, text=f"  {title}  ")

    def _scrollable_page(self, parent: ttk.Notebook) -> tuple[ttk.Frame, ttk.Frame]:
        outer = ttk.Frame(parent)
        canvas = tk.Canvas(outer, background=PALETTE["bg"], highlightthickness=0, borderwidth=0)
        bar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=bar.set)
        bar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        inner = ttk.Frame(canvas, padding=(16, 14))
        window_id = canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(window_id, width=e.width))
        self._scrollables.append(canvas)
        canvas.bind("<Destroy>", lambda _e: self._forget_scrollable(canvas))
        return outer, inner

    def _card(self, parent: tk.Misc, title: str) -> ttk.LabelFrame:
        card = ttk.LabelFrame(parent, text=title, padding=(14, 10))
        card.pack(fill="x", pady=(0, 12))
        card.columnconfigure(1, weight=1)
        return card

    def _note(self, parent: tk.Misc, text: str, row: int, columnspan: int = 3, warn: bool = False) -> None:
        ttk.Label(
            parent,
            text=text,
            style="Warn.TLabel" if warn else "Hint.TLabel",
            wraplength=520,
            justify="left",
        ).grid(row=row, column=0, columnspan=columnspan, sticky="w", pady=(8, 2))

    def _label(self, parent: tk.Misc, text: str, row: int) -> None:
        ttk.Label(parent, text=text).grid(row=row, column=0, sticky="w", padx=(0, 14), pady=5)

    # ---- Aba: Roteiro -------------------------------------------------
    def _tab_script(self, page: ttk.Frame) -> None:
        card = self._card(page, "Projeto")
        self._label(card, "Pasta do projeto", 0)
        ttk.Entry(card, textvariable=self.project_dir).grid(row=0, column=1, sticky="ew", pady=5)
        actions = ttk.Frame(card)
        actions.grid(row=0, column=2, padx=(8, 0))
        ttk.Button(actions, text="Escolher…", command=self._browse_project).pack(side="left")
        ttk.Button(actions, text="Abrir saída", command=self._open_output).pack(side="left", padx=(6, 0))

        card = self._card(page, "Entrada do documentário")
        ttk.Radiobutton(card, text="Usar roteiro .txt existente", variable=self.mode, value="script",
                        command=self._update_mode).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 4))
        ttk.Entry(card, textvariable=self.script_path).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        ttk.Button(card, text="Selecionar…", command=self._browse_script).grid(row=1, column=2, padx=(8, 0), pady=(0, 10))
        self.topic_radio = ttk.Radiobutton(card, text="Gerar roteiro automaticamente a partir de um tema",
                                           variable=self.mode, value="topic", command=self._update_mode)
        self.topic_radio.grid(row=2, column=0, columnspan=3, sticky="w")
        self._label(card, "Tema", 3)
        self.topic_entry = ttk.Entry(card, textvariable=self.topic)
        self.topic_entry.grid(row=3, column=1, columnspan=2, sticky="ew", pady=5)
        self._label(card, "Duração (min)", 4)
        options = ttk.Frame(card)
        options.grid(row=4, column=1, columnspan=2, sticky="w", pady=5)
        self.duration_entry = ttk.Entry(options, textvariable=self.duration, width=8)
        self.duration_entry.pack(side="left")
        ttk.Label(options, text="Canal").pack(side="left", padx=(20, 8))
        ttk.Combobox(options, textvariable=self.channel,
                     values=["documentario", "historia", "geopolitica", "tecnologia"], width=18).pack(side="left")

        card = self._card(page, "Etapa do pipeline")
        for index, (key, label) in enumerate(STAGE_OPTIONS):
            ttk.Radiobutton(card, text=label, variable=self.stage, value=key,
                            command=self._apply_stage).grid(row=index, column=0, columnspan=3, sticky="w", pady=1)
        self._note(card, "Etapas parciais exigem arquivos da execução anterior: --images-only precisa de "
                         "narração pronta; --render-only precisa de clips já processados.",
                   row=len(STAGE_OPTIONS))

        card = self._card(page, "Injeção de texto no roteiro")
        self._label(card, "Abertura (início)", 0)
        ttk.Entry(card, textvariable=self.prepend_text).grid(row=0, column=1, sticky="ew", pady=5)
        self._label(card, "Chamada final (fim)", 1)
        ttk.Entry(card, textvariable=self.append_text).grid(row=1, column=1, sticky="ew", pady=5)
        self._note(card, "O texto é inserido no roteiro antes da narração. Útil para slogans fixos e CTAs.", row=2)

    # ---- Aba: Narração ------------------------------------------------
    def _tab_voice(self, page: ttk.Frame) -> None:
        card = self._card(page, "Voz e transcrição")
        self._label(card, "Motor TTS", 0)
        self.tts_combo = ttk.Combobox(card, textvariable=self.tts_engine,
                                      values=["edge-tts", "xtts", "f5-tts", "openai"], state="readonly", width=18)
        self.tts_combo.grid(row=0, column=1, sticky="w", pady=5)
        self.tts_combo.bind("<<ComboboxSelected>>", self._update_tts_controls)
        self._label(card, "Voz (Edge/OpenAI)", 1)
        self.voice_combo = ttk.Combobox(card, textvariable=self.voice,
                                        values=["pt-BR-AntonioNeural", "pt-BR-FranciscaNeural", "pt-BR-ThalitaNeural"],
                                        width=26)
        self.voice_combo.grid(row=1, column=1, sticky="w", pady=5)
        self._label(card, "Áudio-base XTTS", 2)
        reference = ttk.Frame(card)
        reference.grid(row=2, column=1, sticky="ew", pady=5)
        self.xtts_reference_entry = ttk.Entry(reference, textvariable=self.xtts_reference)
        self.xtts_reference_entry.pack(side="left", fill="x", expand=True)
        self.xtts_reference_button = ttk.Button(reference, text="Escolher WAV…", command=self._browse_xtts_reference)
        self.xtts_reference_button.pack(side="left", padx=(6, 0))
        self._note(card, "O XTTS clona a voz a partir deste áudio (recomendado: WAV limpo de 10 a 30 s, sem música).",
                   row=3, columnspan=2)
        self._label(card, "Whisper (legendas)", 4)
        ttk.Combobox(card, textvariable=self.whisper_model, values=["tiny", "base", "small", "medium", "large"],
                     state="readonly", width=18).grid(row=4, column=1, sticky="w", pady=5)

        card = self._card(page, "Saída da produção")
        for index, (key, label) in enumerate(SUBTITLE_OPTIONS):
            ttk.Radiobutton(card, text=label, variable=self.subtitle_mode, value=key).grid(
                row=index, column=0, columnspan=3, sticky="w", pady=1)
        self._note(card, "Os modos de SRT separado e de narração não usam a voz selecionada acima. "
                         "O arquivo separado sai em português (PT-BR).",
                   row=len(SUBTITLE_OPTIONS), warn=True)

    # ---- Aba: Imagens -------------------------------------------------
    def _tab_images(self, page: ttk.Frame) -> None:
        self.media_source_labels = {key: label for key, label in MEDIA_SOURCE_MODES}
        self.media_source_by_label = {label: key for key, label in MEDIA_SOURCE_MODES}

        card = self._card(page, "Origem das imagens")
        self._label(card, "Estratégia de busca", 0)
        self.media_source_combo = ttk.Combobox(
            card, textvariable=self.media_source_display,
            values=[label for _, label in MEDIA_SOURCE_MODES], state="readonly",
        )
        self.media_source_combo.set(self.media_source_labels[self.media_source_mode.get()])
        self.media_source_combo.grid(row=0, column=1, sticky="ew", pady=5)
        self.media_source_combo.bind("<<ComboboxSelected>>", self._select_media_source_mode)
        self._label(card, "Pasta da biblioteca local", 1)
        folder = ttk.Frame(card)
        folder.grid(row=1, column=1, sticky="ew", pady=5)
        ttk.Entry(folder, textvariable=self.local_media_folder).pack(side="left", fill="x", expand=True)
        ttk.Button(folder, text="Escolher pasta…", command=self._browse_local_media_folder).pack(side="left", padx=(6, 0))
        self._label(card, "Mínimo de imagens únicas", 2)
        ttk.Entry(card, textvariable=self.min_local_images, width=10).grid(row=2, column=1, sticky="w", pady=5)
        checks = ttk.Frame(card)
        checks.grid(row=3, column=0, columnspan=3, sticky="w", pady=(8, 0))
        ttk.Checkbutton(checks, text="Pular Ollama (seleção manual direta de fotos)",
                        variable=self.skip_ollama_manual).pack(anchor="w")
        ttk.Checkbutton(checks, text="Revisar imagens locais abaixo do limiar",
                        variable=self.review_local_media).pack(anchor="w", pady=(2, 0))
        self._note(card, "O mínimo distribui imagens entre os cortes das cenas. No modo somente local, "
                         "a produção falha se a quantidade não for atingida.", row=4)

        card = self._card(page, "Provedor de imagem com IA")
        self._label(card, "Provedor", 0)
        self.provider_labels = {key: label for key, label in PROVIDER_OPTIONS}
        self.provider_by_label = {label: key for key, label in PROVIDER_OPTIONS}
        self.provider_combo = ttk.Combobox(card, state="readonly",
                                           values=[label for _, label in PROVIDER_OPTIONS])
        self.provider_combo.set(self.provider_labels[self.image_provider.get()])
        self.provider_combo.grid(row=0, column=1, sticky="ew", pady=5)
        self.provider_combo.bind("<<ComboboxSelected>>", self._select_image_provider)
        actions = ttk.Frame(card)
        actions.grid(row=1, column=0, columnspan=3, sticky="w", pady=(6, 0))
        ttk.Button(actions, text="1. Abrir login", command=self._open_image_provider_login).pack(side="left")
        ttk.Button(actions, text="2. Calibrar", command=self._calibrate_selected_image_provider).pack(side="left", padx=(6, 0))
        self._note(card, "Abra o login, entre na conta e feche somente a janela do navegador. Depois calibre; "
                         "o resultado aparece no monitor.", row=2)

        card = self._card(page, "Qualidade e fontes de vídeo")
        self._label(card, "Diretor de arte", 0)
        ttk.Combobox(card, textvariable=self.art_director, values=["standard", "strict", "off"],
                     state="readonly", width=18).grid(row=0, column=1, sticky="w", pady=5)
        self._label(card, "Fonte YouTube", 1)
        ttk.Combobox(card, textvariable=self.youtube_mode, values=["off", "cc", "authorized", "both"],
                     state="readonly", width=18).grid(row=1, column=1, sticky="w", pady=5)
        self._label(card, "Vídeo local autorizado", 2)
        video = ttk.Frame(card)
        video.grid(row=2, column=1, sticky="ew", pady=5)
        ttk.Entry(video, textvariable=self.authorized_video).pack(side="left", fill="x", expand=True)
        ttk.Button(video, text="Escolher vídeo…", command=self._browse_authorized_video).pack(side="left", padx=(6, 0))
        self._label(card, "URL de origem (opcional)", 3)
        ttk.Entry(card, textvariable=self.source_url).grid(row=3, column=1, sticky="ew", pady=5)
        ttk.Checkbutton(card, text="Confirmo que tenho autorização/licença para reutilizar esse arquivo",
                        variable=self.rights_confirmed).grid(row=4, column=0, columnspan=3, sticky="w", pady=(8, 0))
        self._note(card, "CC só baixa vídeo com licença reutilizável explícita. Os modos 'authorized' e 'both' "
                         "usam o arquivo local autorizado acima.", row=5)

    # ---- Aba: Projetos ------------------------------------------------
    def _tab_projects(self, page: ttk.Frame) -> None:
        card = self._card(page, "Projetos existentes e produções interrompidas")
        self._label(card, "Projeto", 0)
        self.project_combo = ttk.Combobox(card, textvariable=self.project_choice, state="readonly", width=40)
        self.project_combo.grid(row=0, column=1, sticky="ew", pady=5)
        ttk.Button(card, text="Atualizar lista",
                   command=lambda: self._refresh_projects(verbose=True)).grid(row=0, column=2, padx=(8, 0))
        actions = ttk.Frame(card)
        actions.grid(row=1, column=0, columnspan=3, sticky="w", pady=(12, 0))
        self.resume_btn = ttk.Button(actions, text="↻  Retomar projeto", command=self._resume_selected)
        self.resume_btn.pack(side="left")
        self.delete_btn = ttk.Button(actions, text="Excluir projeto…", style="Danger.TButton",
                                     command=self._delete_selected_project)
        self.delete_btn.pack(side="left", padx=(8, 0))
        self._note(card, "Retomar usa o checkpoint salvo e o roteiro original em roteiros/. Excluir remove a pasta "
                         "de trabalho do projeto e os exportados com o mesmo nome; o roteiro nunca é apagado.",
                   row=2)

    # ---- Aba: Avançado ------------------------------------------------
    def _tab_advanced(self, page: ttk.Frame) -> None:
        card = self._card(page, "Checkpoints e retomada")
        for index, (label, variable) in enumerate((
            ("Usar checkpoint ao iniciar (retomada)", self.resume),
            ("Salvar checkpoints (recomendado)", self.checkpoint),
            ("Reutilizar narração se o roteiro não mudou", self.reuse_audio),
        )):
            ttk.Checkbutton(card, text=label, variable=variable).grid(row=index, column=0, columnspan=2,
                                                                       sticky="w", pady=2)

        card = self._card(page, "Reuso e regeneração de mídia")
        media_options = (
            ("Reutilizar imagens aprovadas", self.reuse_approved_images),
            ("Revalidar imagens existentes", self.revalidate_images),
            ("Forçar nova busca/geração de mídia", self.force_regeneration),
            ("Ignorar cache de mídia", self.ignore_cache),
            ("Pesquisar na web antes de gerar imagens IA", self.web_research_before_generation),
            ("Web primeiro (mídia real antes de IA)", self.prefer_real_media),
            ("Fallback para Gemini", self.gemini_fallback),
            ("Somente Gemini para geração", self.gemini_only),
        )
        for index, (label, variable) in enumerate(media_options):
            ttk.Checkbutton(card, text=label, variable=variable,
                            command=self._sync_image_reuse_options).grid(
                row=index // 2, column=index % 2, sticky="w", padx=(0, 22), pady=3)

        card = self._card(page, "Diagnóstico")
        ttk.Checkbutton(card, text="Debug detalhado (--debug)", variable=self.debug_verbose).grid(
            row=0, column=0, sticky="w")

    # ---- Monitor ------------------------------------------------------
    def _build_monitor(self, parent: ttk.Frame) -> None:
        card = ttk.LabelFrame(parent, text="Monitor da produção  ·  logs em tempo real", padding=(14, 10))
        card.pack(fill="both", expand=True, padx=(10, 0), pady=(0, 0))
        card.columnconfigure(0, weight=1)
        card.rowconfigure(2, weight=1)

        toolbar = ttk.Frame(card)
        toolbar.grid(row=0, column=0, sticky="ew")
        self.start_btn = ttk.Button(toolbar, text="▶  Iniciar produção", style="Accent.TButton", command=self._start)
        self.start_btn.pack(side="left")
        self.stop_btn = ttk.Button(toolbar, text="■  Cancelar", command=self._stop, state="disabled")
        self.stop_btn.pack(side="left", padx=(8, 0))
        ttk.Button(toolbar, text="Ver comando", command=self._show_command).pack(side="left", padx=(8, 0))
        ttk.Button(toolbar, text="Limpar log", command=self._clear_log).pack(side="right")
        ttk.Button(toolbar, text="Salvar log", command=self._save_log).pack(side="right", padx=(0, 8))

        self.progress = ttk.Progressbar(card, mode="indeterminate", style="Horizontal.TProgressbar")
        self.progress.grid(row=1, column=0, sticky="ew", pady=(12, 10))

        log_host = ttk.Frame(card)
        log_host.grid(row=2, column=0, sticky="nsew")
        log_host.columnconfigure(0, weight=1)
        log_host.rowconfigure(0, weight=1)
        self.log_text = tk.Text(
            log_host, wrap="word", state="disabled", font=(FONT_MONO, 10),
            background=PALETTE["field"], foreground="#d7e6eb", insertbackground="white",
            relief="flat", borderwidth=0, highlightthickness=1,
            highlightbackground=PALETTE["border"], highlightcolor=PALETTE["accent"],
            padx=12, pady=10, spacing1=2, spacing3=2, selectbackground="#1d6b5d",
        )
        self.log_text.tag_configure("info", foreground="#b8c8ce")
        self.log_text.tag_configure("success", foreground=PALETTE["ok"])
        self.log_text.tag_configure("warning", foreground=PALETTE["warn"])
        self.log_text.tag_configure("error", foreground=PALETTE["error"])
        self.log_text.tag_configure("stage", foreground=PALETTE["accent"], font=(FONT_MONO, 10, "bold"))
        scroll = ttk.Scrollbar(log_host, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scroll.set)
        self.log_text.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")

    # ------------------------------------------------------------------
    # Estado visual, rolagem e comportamento da interface
    # ------------------------------------------------------------------
    def _set_state(self, kind: str, text: str | None = None) -> None:
        background, foreground, label = STATE_STYLES[kind]
        self.pill.configure(text=f"  {label}  ", background=background, foreground=foreground)
        if text is not None:
            self.status.set(text)

    def _apply_stage(self, _event=None) -> None:
        """Aplica a etapa escolhida (radio único) aos modos exclusivos do pipeline."""
        stage = self.stage.get()
        script_only = stage == "script"
        self.script_only.set(script_only)
        self.images_only.set(stage == "images")
        self.render_only.set(stage == "render")

        if script_only:
            for widget in (self.tts_combo, self.voice_combo, self.xtts_reference_entry, self.xtts_reference_button):
                widget.configure(state="disabled")
        else:
            self.tts_combo.configure(state="readonly")
            self._update_tts_controls()

        needs_script = stage in ("images", "render")
        if needs_script:
            self.mode.set("script")
        self.topic_radio.configure(state="disabled" if needs_script else "normal")
        self._update_mode()

    def _on_global_wheel(self, event) -> None:
        """Roteia a roda do mouse para o painel rolável sob o ponteiro."""
        if event.num == 4:
            units = -1
        elif event.num == 5:
            units = 1
        else:
            units = -1 if event.delta > 0 else 1
        try:
            widget = self.winfo_containing(event.x_root, event.y_root)
        except (tk.TclError, KeyError):
            return
        while widget is not None:
            if widget in self._scrollables:
                widget.yview_scroll(units, "units")
                return
            widget = widget.master

    def _forget_scrollable(self, canvas: tk.Canvas) -> None:
        if canvas in self._scrollables:
            self._scrollables.remove(canvas)

    def _show_command(self) -> None:
        try:
            cmd, _cwd = self._build_command()
        except Exception as exc:
            messagebox.showerror("Confira as configurações", str(exc))
            return
        text = " ".join(self._quote(item) for item in cmd)
        win = tk.Toplevel(self)
        win.title("Comando que será executado")
        win.configure(background=PALETTE["bg"])
        win.transient(self)
        box = tk.Text(win, wrap="word", height=10, width=110, font=(FONT_MONO, 9),
                      background=PALETTE["field"], foreground=PALETTE["text"], relief="flat",
                      padx=12, pady=10)
        box.insert("1.0", text)
        box.configure(state="disabled")
        box.pack(fill="both", expand=True, padx=16, pady=(16, 8))
        buttons = ttk.Frame(win, padding=(16, 0, 16, 14))
        buttons.pack(fill="x")

        def copy() -> None:
            self.clipboard_clear()
            self.clipboard_append(text)

        ttk.Button(buttons, text="Copiar", command=copy).pack(side="left")
        ttk.Button(buttons, text="Fechar", command=win.destroy).pack(side="right")

    def _update_mode(self) -> None:
        script_mode = self.mode.get() == "script"
        state = "disabled" if script_mode else "normal"
        self.topic_entry.configure(state=state)
        self.duration_entry.configure(state=state)

    def _select_image_provider(self, _event=None) -> None:
        self.image_provider.set(self.provider_by_label.get(self.provider_combo.get(), "gemini"))

    def _sync_image_reuse_options(self) -> None:
        if self.revalidate_images.get():
            self.reuse_approved_images.set(False)
        elif self.reuse_approved_images.get():
            self.revalidate_images.set(False)

    def _refresh_projects(self, verbose: bool = False) -> None:
        try:
            projects_dir = self._root_dir() / "projetos"
            projects_dir.mkdir(parents=True, exist_ok=True)
            # Lista todos os workspaces, inclusive projetos que falharam antes do primeiro checkpoint.
            names = sorted(p.name for p in projects_dir.iterdir() if p.is_dir())
            self.project_combo["values"] = names
            if self.project_choice.get() not in names:
                self.project_choice.set(names[0] if names else "")
            if verbose:
                self._append_log(f"[GUI] Pastas de projeto encontradas: {len(names)}\n")
        except Exception as exc:
            self._append_log(f"[GUI] Não foi possível listar projetos: {exc}\n")

    # ------------------------------------------------------------------
    # Execução
    # ------------------------------------------------------------------
    def _local_library_problem(self) -> str | None:
        """Impede iniciar quando o modo exige biblioteca local e ela não tem imagens.

        Espelha a regra do media_research_agent (local_only = 'required'): com índice
        vazio a produção aborta no meio do passo 4. Aqui o erro aparece antes.
        """
        if self.subtitle_mode.get() in ("audio_only", "srt_only") or self.script_only.get():
            return None
        if self.media_source_mode.get() != "local_only":
            return None
        folder = Path(self.local_media_folder.get().strip()).expanduser()
        if not folder.is_dir():
            return f"A pasta da biblioteca local não existe:\n{folder}"
        images = [p for p in folder.glob("*.*") if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS]
        if not images:
            return (
                "O modo 'Somente biblioteca local' exige imagens na pasta, mas ela está vazia:\n"
                f"{folder}\n\n"
                "Escolha a pasta de uma biblioteca com fotos, ou troque a estratégia para "
                "'Biblioteca local → internet / WebChat'."
            )
        return None

    def _start(self) -> None:
        if self.proc and self.proc.poll() is None:
            return
        try:
            cmd, cwd = self._build_command()
        except Exception as exc:
            messagebox.showerror("Confira as configurações", str(exc))
            return
        problem = self._local_library_problem()
        if problem:
            messagebox.showerror("Biblioteca local", problem)
            return
        summary = " ".join(self._quote(x) for x in cmd)
        self._append_log(f"\n{'=' * 72}\nIniciando em: {cwd}\nComando: {summary}\n{'=' * 72}\n")
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.progress.start(12)
        self._set_state("running", "Executando pipeline…")

        child_env = os.environ.copy()
        if self.review_local_media.get():
            child_env["VF_LOCAL_MEDIA_REVIEW_GUI"] = "1"
        if self.tts_engine.get().strip().lower() in ("xtts", "xtts-v2", "xtts_v2", "clone"):
            # O caminho absoluto selecionado na GUI tem prioridade sobre config.yaml.
            child_env["VF_XTTS_SPEAKER"] = str(Path(self.xtts_reference.get()).expanduser().resolve())
            # Evita que uma falha do XTTS seja silenciosamente mascarada por Edge-TTS.
            child_env["VF_XTTS_SEM_FALLBACK"] = "1"
            self._append_log("[GUI] XTTS selecionado: a narração usará o áudio-base indicado. Se o XTTS falhar, "
                             "a execução exibirá erro em vez de trocar de voz silenciosamente.\n")
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


    def _finish(self, kind: str, text: str) -> None:
        self.start_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        self.progress.stop()
        self._set_state(kind, text)
        self._refresh_projects()

    def _drain_log_queue(self) -> None:
        try:
            while True:
                item = self.log_queue.get_nowait()
                if item == "__DONE_OK__":
                    self._finish("ok", "Concluído. Confira os arquivos e relatórios na pasta de saída.")
                elif item == "__DONE_ERROR__":
                    self._finish("error", "Terminou com erro ou interrupção. Leia o log.")
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
            selected_paths = self._show_local_media_review(request)
            if not self.proc or not self.proc.stdin:
                raise RuntimeError("O processo não está aguardando uma decisão de revisão.")
            
            # Send the list of selected paths as JSON array
            if isinstance(selected_paths, list) and selected_paths:
                # Convert to JSON array and send to agent
                response = json.dumps(selected_paths)
                self.proc.stdin.write(response + "\n")
                print(f"[DEBUG] Enviando {len(selected_paths)} fotos para o agente", flush=True)
            elif isinstance(selected_paths, bool):
                # Backward compatibility - simple approve/reject
                self.proc.stdin.write("aprovar\n" if selected_paths else "rejeitar\n")
            else:
                # Default to reject if nothing selected
                self.proc.stdin.write("rejeitar\n")
            
            self.proc.stdin.flush()
        except (OSError, ValueError, RuntimeError, KeyError, tk.TclError) as exc:
            self._append_log(f"\n[ERRO] Falha na revisão manual de imagem local: {exc}\n")
            if self.proc and self.proc.poll() is None:
                self.proc.terminate()


    def _show_local_media_review(self, request: dict) -> list:
        """Seleção de imagens locais para uma cena: busca, miniaturas e contador ao vivo."""
        from PIL import Image, ImageTk

        suggested_path = str(request.get("image_path", "") or "")
        folder_path = Path(suggested_path).parent if suggested_path else Path(self.local_media_folder.get())
        all_files: list[str] = []
        if folder_path.is_dir():
            all_files = sorted(str(p.resolve()) for p in folder_path.glob("*.*")
                               if p.suffix.lower() in IMAGE_EXTENSIONS)
        if not all_files and suggested_path:
            all_files = [suggested_path]
        if suggested_path in all_files:
            all_files.remove(suggested_path)
            all_files.insert(0, suggested_path)

        scene_id = request.get("scene_id", "?")
        selected: set[str] = set()
        visible: list[str] = list(all_files)
        cards: dict[str, tuple[tk.Frame, tk.Label]] = {}
        thumbs: dict[str, object] = {}
        thumb_size = (176, 132)
        columns = 5

        dialog = tk.Toplevel(self)
        dialog.title(f"Selecionar imagens — Cena {scene_id}")
        dialog.configure(background=PALETTE["bg"])
        dialog.geometry("1220x880")
        dialog.minsize(1000, 680)
        dialog.transient(self)
        dialog.columnconfigure(0, weight=1)
        dialog.rowconfigure(2, weight=1)

        def normalize(text: str) -> str:
            text = unicodedata.normalize("NFKD", text)
            return "".join(ch for ch in text if not unicodedata.combining(ch)).lower()

        def thumbnail(path: str):
            if path not in thumbs:
                try:
                    with Image.open(path) as img:
                        img.thumbnail(thumb_size, Image.Resampling.LANCZOS)
                        thumbs[path] = ImageTk.PhotoImage(img.convert("RGB"), master=dialog)
                except Exception:
                    thumbs[path] = None
            return thumbs[path]

        def style_card(path: str) -> None:
            entry = cards.get(path)
            if not entry:
                return
            frame, name_label = entry
            is_selected = path in selected
            frame.configure(highlightbackground=PALETTE["accent"] if is_selected else PALETTE["border"])
            name_label.configure(
                text=("✔ " if is_selected else "") + Path(path).name[:30],
                foreground=PALETTE["accent"] if is_selected else PALETTE["muted"],
            )

        def update_counter() -> None:
            counter.configure(text=f"Selecionadas: {len(selected)} / {len(all_files)}")
            finish_btn.configure(text=f"Usar selecionadas ({len(selected)})")

        def toggle(path: str) -> None:
            if path in selected:
                selected.discard(path)
            else:
                selected.add(path)
            style_card(path)
            update_counter()

        def rebuild() -> None:
            for child in inner.winfo_children():
                child.destroy()
            cards.clear()
            if not visible:
                tk.Label(inner, text="Nenhuma imagem encontrada para a busca.", font=(FONT, 11),
                         background=PALETTE["bg"], foreground=PALETTE["muted"]).grid(row=0, column=0, padx=40, pady=60)
                return
            for pos, path in enumerate(visible):
                row, col = divmod(pos, columns)
                frame = tk.Frame(inner, background=PALETTE["card"], highlightthickness=3,
                                 highlightbackground=PALETTE["border"], bd=0, cursor="hand2")
                frame.grid(row=row, column=col, padx=6, pady=6, sticky="n")
                image = thumbnail(path)
                if image is not None:
                    picture = tk.Label(frame, image=image, background=PALETTE["card"], cursor="hand2")
                    picture.image = image  # mantém referência viva
                else:
                    picture = tk.Label(frame, text="[erro ao carregar]", width=24, height=8,
                                       background=PALETTE["card"], foreground=PALETTE["muted"])
                picture.pack(padx=6, pady=(8, 4))
                name_label = tk.Label(frame, text="", background=PALETTE["card"], font=(FONT, 8),
                                      width=30, anchor="w")
                name_label.pack(padx=6, pady=(0, 8), fill="x")
                for widget in (frame, picture, name_label):
                    widget.bind("<Button-1>", lambda _e, p=path: toggle(p))
                cards[path] = (frame, name_label)
                style_card(path)
            for col in range(columns):
                inner.columnconfigure(col, weight=1)
            canvas.yview_moveto(0)

        def select_visible(flag: bool) -> None:
            for path in visible:
                if flag:
                    selected.add(path)
                else:
                    selected.discard(path)
                style_card(path)
            update_counter()

        def on_filter(*_args) -> None:
            query = normalize(search_var.get().strip())
            visible[:] = [p for p in all_files if not query or query in normalize(Path(p).stem)]
            rebuild()
            update_counter()

        def finish_selection() -> None:
            dialog.destroy()

        def cancel_selection() -> None:
            selected.clear()
            dialog.destroy()

        # Cabeçalho
        head = ttk.Frame(dialog, padding=(18, 16, 18, 6))
        head.grid(row=0, column=0, sticky="ew")
        head.columnconfigure(0, weight=1)
        ttk.Label(head, text=f"Cena {scene_id}", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(head, text="Escolha uma ou mais fotos da biblioteca local para esta cena. Clique na miniatura para marcar.",
                  style="Muted.TLabel").grid(row=1, column=0, sticky="w")
        counter = ttk.Label(head, text="", style="Count.TLabel")
        counter.grid(row=0, column=1, rowspan=2, sticky="e")

        # Barra de ferramentas
        bar = ttk.Frame(dialog, padding=(18, 4))
        bar.grid(row=1, column=0, sticky="ew")
        ttk.Label(bar, text="Buscar pelo nome").pack(side="left")
        search_var = tk.StringVar()
        search_entry = ttk.Entry(bar, textvariable=search_var, width=34)
        search_entry.pack(side="left", padx=(8, 16))
        ttk.Button(bar, text="Selecionar visíveis", command=lambda: select_visible(True)).pack(side="left")
        ttk.Button(bar, text="Limpar seleção", command=lambda: select_visible(False)).pack(side="left", padx=(6, 0))
        ttk.Label(bar, text=f"{len(all_files)} fotos na pasta", style="Muted.TLabel").pack(side="right")

        # Grade rolável
        grid_host = ttk.Frame(dialog, padding=(18, 6))
        grid_host.grid(row=2, column=0, sticky="nsew")
        grid_host.columnconfigure(0, weight=1)
        grid_host.rowconfigure(0, weight=1)
        canvas = tk.Canvas(grid_host, background=PALETTE["bg"], highlightthickness=0, borderwidth=0)
        bar_y = ttk.Scrollbar(grid_host, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=bar_y.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        bar_y.grid(row=0, column=1, sticky="ns")
        inner = tk.Frame(canvas, background=PALETTE["bg"])
        window_id = canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(window_id, width=e.width))
        self._scrollables.append(canvas)
        canvas.bind("<Destroy>", lambda _e: self._forget_scrollable(canvas))

        # Trecho do roteiro (somente leitura)
        scene_text = str(request.get("scene_text", "") or "")
        if scene_text:
            snippet_box = ttk.LabelFrame(dialog, text="Trecho do roteiro", padding=(10, 6))
            snippet_box.grid(row=3, column=0, sticky="ew", padx=18, pady=(8, 0))
            snippet = tk.Text(snippet_box, height=3, wrap="word", background=PALETTE["field"],
                              foreground=PALETTE["text"], relief="flat", padx=8, pady=6, font=(FONT, 9))
            snippet.pack(fill="x")
            snippet.insert("1.0", scene_text[:320] + ("…" if len(scene_text) > 320 else ""))
            snippet.configure(state="disabled")

        # Ações
        actions = ttk.Frame(dialog, padding=(18, 10, 18, 16))
        actions.grid(row=4, column=0, sticky="ew")
        ttk.Button(actions, text="Cancelar", command=cancel_selection).pack(side="left")
        finish_btn = ttk.Button(actions, text="Usar selecionadas (0)", style="Accent.TButton",
                                command=finish_selection)
        finish_btn.pack(side="right")

        search_var.trace_add("write", on_filter)
        dialog.bind("<Escape>", lambda _e: cancel_selection())
        dialog.protocol("WM_DELETE_WINDOW", cancel_selection)
        rebuild()
        update_counter()
        search_entry.focus_set()
        try:
            dialog.grab_set()
        except tk.TclError:
            pass  # janela ainda não visível em algumas plataformas; o diálogo segue funcionando

        self.wait_window(dialog)
        return list(selected)

    def _stop(self) -> None:
        proc = self.proc
        if not proc or proc.poll() is not None:
            return
        if not messagebox.askyesno(
            "Cancelar produção",
            "Deseja cancelar a produção em andamento?\n\n"
            "O checkpoint mais recente será preservado quando já tiver sido salvo, "
            "permitindo tentar retomar depois. Processos filhos como FFmpeg também serão encerrados.",
        ):
            return
        self._set_state("cancelling", "Cancelando produção…")
        self._append_log("\n[GUI] Cancelamento solicitado; tentando encerrar o pipeline e processos filhos…\n")
        try:
            if os.name == "nt":
                # Processo iniciado em grupo próprio: tenta sinal cooperativo e, se não encerrar, mata a árvore.
                try:
                    proc.send_signal(signal.CTRL_BREAK_EVENT)
                except Exception:
                    proc.terminate()
                threading.Thread(target=self._force_stop_process_tree, args=(proc,), daemon=True).start()
            else:
                proc.terminate()
        except Exception as exc:
            messagebox.showerror("Falha ao cancelar", str(exc))

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
        """Salva o log visível em <projeto>.log, com o nome do projeto atual."""
        try:
            project = Path(self.project_dir.get()).expanduser()
            logs_dir = project / "logs"
            logs_dir.mkdir(parents=True, exist_ok=True)
            slug = self._project_slug_from_current_input() or self.project_choice.get().strip() or "projeto"
            slug = self._slugify(slug)
            target = logs_dir / f"{slug}.log"
            index = 2
            while target.exists():
                target = logs_dir / f"{slug}_{index}.log"
                index += 1
            content = self.log_text.get("1.0", "end-1c")
            target.write_text(content, encoding="utf-8", errors="replace")
            messagebox.showinfo("Log salvo", f"Log salvo em:\n{target}")
        except Exception as exc:
            messagebox.showerror("Falha ao salvar log", f"Não foi possível salvar o log:\n{exc}")

    def _clear_log(self) -> None:
        self.log_text.configure(state="normal"); self.log_text.delete("1.0", "end"); self.log_text.configure(state="disabled")

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


    # ------------------------------------------------------------------
    # Ações e utilitários verbatim (contrato com agent.py e com o disco)
    # ------------------------------------------------------------------
    def _update_tts_controls(self, _event=None) -> None:
        is_xtts = self.tts_engine.get().strip().lower() in ("xtts", "xtts-v2", "xtts_v2", "clone")
        state = "normal" if is_xtts else "disabled"
        self.xtts_reference_entry.configure(state=state)
        self.xtts_reference_button.configure(state=state)
        self.voice_combo.configure(state="disabled" if is_xtts else "normal")

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

    def _browse_project(self) -> None:
        p = filedialog.askdirectory(title="Selecione a pasta que contém agent.py", initialdir=self.project_dir.get() or str(Path.home()))
        if p:
            self.project_dir.set(p)
            self._load_xtts_reference_from_config()
            if not self._local_media_folder_manual:
                self._load_media_source_settings()

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
        
        # Validação de modos de pipeline exclusivos
        pipeline_modes = [
            self.script_only.get(),
            self.images_only.get(),
            self.render_only.get(),
        ]
        if sum(pipeline_modes) > 1:
            raise ValueError(
                "Apenas um modo de pipeline pode ser selecionado: "
                "--script-only, --images-only ou --render-only."
            )
        # --images-only e --render-only exigem roteiro existente
        if (self.images_only.get() or self.render_only.get()) and self.mode.get() != "script":
            raise ValueError(
                "Os modos --images-only e --render-only exigem "
                "um arquivo de roteiro .txt (modo 'Usar roteiro .txt existente')."
            )
        # --render-only não é compatível com audio_only/srt_only
        if self.render_only.get() and audio_only:
            raise ValueError("--render-only não é compatível com --audio-only.")
        if self.render_only.get() and subtitle_mode == "srt_only":
            raise ValueError("--render-only não é compatível com --subtitles-only.")
        
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
        
        # Pipeline control flags
        if self.script_only.get():
            cmd.append("--script-only")
        if self.images_only.get():
            cmd.append("--images-only")
        if self.render_only.get():
            cmd.append("--render-only")
        
        # Text injection flags
        prepend_text = self.prepend_text.get().strip()
        if prepend_text:
            cmd.extend(["--prepend-text", prepend_text])
        append_text = self.append_text.get().strip()
        if append_text:
            cmd.extend(["--append-text", append_text])

        if self.youtube_mode.get() in ("authorized", "both"):
            video = self.authorized_video.get().strip()
            if not video: raise ValueError("Escolha um arquivo de vídeo local autorizado para este modo do YouTube.")
            if not Path(video).expanduser().is_file(): raise ValueError("O arquivo de vídeo selecionado não existe.")
            if not self.rights_confirmed.get(): raise ValueError("Confirme que você tem autorização/licença para reutilizar o arquivo.")
            cmd.extend(["--youtube-authorized-file", str(Path(video).expanduser().resolve()), "--youtube-rights-confirmed"])
            if self.source_url.get().strip(): cmd.extend(["--youtube-source-url", self.source_url.get().strip()])
        return cmd, project

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

    def _calibrate_selected_image_provider(self) -> None:
        provider = self.image_provider.get()
        self._calibrate_image_provider(provider)



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
