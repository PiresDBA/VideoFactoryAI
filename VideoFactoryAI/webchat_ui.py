#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
webchat_ui.py — Painel visual de validação para webchat_bridge
================================================================
Interface gráfica simples (Tkinter) que monitora a pasta de fila
e permite aprovar, editar ou rejeitar envios/respostas dos chats.

Como usar:
1. Execute este script em um terminal separado:
   python webchat_ui.py

2. Configure no ambiente:
   set WEBCHAT_UI=1
   set VF_WEBCHAT_VALIDAR=resposta  (ou 'envio', 'ambos')

3. O painel fica ativo esperando itens na fila.
   Quando o bridge envia algo para validação, aparece aqui com:
   - Tipo: 'envio' | 'resposta' | 'assistido'
   - Site: gemini, chatgpt, copilot, deepseek, etc.
   - Texto completo

4. Botões:
   [Aprovar]   → Aceita o texto como está
   [Editar]    → Abre editor para modificar antes de aprovar
   [Reprovar]  → Rejeita (o bridge tenta próximo site ou aborta)

Arquivos de fila em: VideoFactoryAI/fila/
  pendente_<id>.json  → Item aguardando validação
  resposta_<id>.json  → Sua decisão (criado pelo painel)
"""

import os
import sys
import json
import time
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
from pathlib import Path
from datetime import datetime

# Diretório base do projeto
BASE = Path(__file__).resolve().parent
FILA = BASE / "fila"
FILA.mkdir(exist_ok=True)

REFRESH_MS = 800  # intervalo de verificação da fila


class WebChatUI:
    def __init__(self, root):
        self.root = root
        self.root.title("VideoFactoryAI — Validador WebChat")
        self.root.geometry("900x700")
        self.root.minsize(800, 600)

        self.pending_items = {}  # vid -> item data
        self.current_vid = None
        self.editor_window = None

        self._build_ui()
        self._start_watcher()

    def _build_ui(self):
        # Toolbar
        toolbar = ttk.Frame(self.root, padding=10)
        toolbar.pack(fill=tk.X)

        ttk.Label(toolbar, text="🔍 Monitorando: ", font=("Segoe UI", 10, "bold")).pack(side=tk.LEFT)
        self.status_label = ttk.Label(toolbar, text="Aguardando itens...", foreground="gray")
        self.status_label.pack(side=tk.LEFT, padx=5)

        ttk.Button(toolbar, text="🔄 Atualizar Agora", command=self._scan_queue).pack(side=tk.RIGHT, padx=5)
        ttk.Button(toolbar, text="📁 Abrir Pasta Fila", command=self._open_queue_folder).pack(side=tk.RIGHT, padx=5)
        ttk.Button(toolbar, text="❌ Limpar Órfãos", command=self._clean_orphans).pack(side=tk.RIGHT, padx=5)

        # Paned window: lista à esquerda, detalhes à direita
        paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        # ── Painel Esquerdo: Lista de itens pendentes ────────────────────────
        left_frame = ttk.LabelFrame(paned, text="Itens Pendentes", padding=5)
        paned.add(left_frame, weight=1)

        columns = ("id", "tipo", "site", "horario", "preview")
        self.tree = ttk.Treeview(left_frame, columns=columns, show="headings", selectmode="browse")
        self.tree.heading("id", text="ID")
        self.tree.heading("tipo", text="Tipo")
        self.tree.heading("site", text="Site")
        self.tree.heading("horario", text="Hora")
        self.tree.heading("preview", text="Prévia")
        self.tree.column("id", width=180, anchor=tk.W)
        self.tree.column("tipo", width=80, anchor=tk.CENTER)
        self.tree.column("site", width=100, anchor=tk.CENTER)
        self.tree.column("horario", width=100, anchor=tk.CENTER)
        self.tree.column("preview", width=300, anchor=tk.W)
        self.tree.pack(fill=tk.BOTH, expand=True)
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        # Scrollbar
        vsb = ttk.Scrollbar(left_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

        # ── Painel Direito: Detalhes do item selecionado ─────────────────────
        right_frame = ttk.LabelFrame(paned, text="Detalhes do Item", padding=5)
        paned.add(right_frame, weight=2)

        # Info header
        info_frame = ttk.Frame(right_frame)
        info_frame.pack(fill=tk.X, pady=(0, 5))
        self.lbl_tipo = ttk.Label(info_frame, text="Tipo: —", font=("Segoe UI", 10, "bold"))
        self.lbl_tipo.pack(side=tk.LEFT, padx=5)
        self.lbl_site = ttk.Label(info_frame, text="Site: —", foreground="blue")
        self.lbl_site.pack(side=tk.LEFT, padx=15)
        self.lbl_time = ttk.Label(info_frame, text="Hora: —", foreground="gray")
        self.lbl_time.pack(side=tk.LEFT, padx=15)

        # Texto do item
        self.txt_content = scrolledtext.ScrolledText(right_frame, wrap=tk.WORD, font=("Consolas", 10))
        self.txt_content.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        self.txt_content.config(state=tk.DISABLED)

        # Botões de ação
        btn_frame = ttk.Frame(right_frame)
        btn_frame.pack(fill=tk.X)

        self.btn_aprovar = ttk.Button(btn_frame, text="✅ Aprovar", command=lambda: self._decide("aprovar"),
                                      style="Accent.TButton", state=tk.DISABLED)
        self.btn_aprovar.pack(side=tk.LEFT, padx=5, ipadx=15, ipady=5)

        self.btn_editar = ttk.Button(btn_frame, text="✏️ Editar e Aprovar", command=lambda: self._decide("editar"),
                                     state=tk.DISABLED)
        self.btn_editar.pack(side=tk.LEFT, padx=5, ipadx=15, ipady=5)

        self.btn_reprovar = ttk.Button(btn_frame, text="❌ Reprovar", command=lambda: self._decide("rejeitar"),
                                       state=tk.DISABLED)
        self.btn_reprovar.pack(side=tk.LEFT, padx=5, ipadx=15, ipady=5)

        # Estilo para botão de aprovar
        style = ttk.Style()
        style.configure("Accent.TButton", foreground="white", background="#28a745")
        style.map("Accent.TButton", background=[("active", "#218838")])

        # Log inferior
        log_frame = ttk.LabelFrame(self.root, text="Log", padding=5)
        log_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
        self.txt_log = scrolledtext.ScrolledText(log_frame, height=6, font=("Consolas", 9), state=tk.DISABLED)
        self.txt_content.pack(fill=tk.BOTH, expand=True)
        self.txt_log.pack(fill=tk.BOTH, expand=True)

    def _log(self, msg):
        """Adiciona mensagem ao log com timestamp."""
        ts = datetime.now().strftime("%H:%M:%S")
        self.txt_log.config(state=tk.NORMAL)
        self.txt_log.insert(tk.END, f"[{ts}] {msg}\n")
        self.txt_log.see(tk.END)
        self.txt_log.config(state=tk.DISABLED)

    def _start_watcher(self):
        """Inicia thread que monitora a pasta de fila."""
        self._scan_queue()
        self.root.after(REFRESH_MS, self._start_watcher)

    def _scan_queue(self):
        """Escaneia arquivos pendentes na fila."""
        try:
            found = {}
            for f in FILA.glob("pendente_*.json"):
                try:
                    data = json.loads(f.read_text(encoding="utf-8"))
                    vid = data.get("id")
                    if vid:
                        found[vid] = (f, data)
                except Exception:
                    pass

            # Adiciona novos
            for vid, (fpath, data) in found.items():
                if vid not in self.pending_items:
                    self.pending_items[vid] = {"path": fpath, "data": data, "resp_path": FILA / f"resposta_{vid}.json"}
                    self._add_to_tree(vid, data)

            # Remove processados
            for vid in list(self.pending_items.keys()):
                if vid not in found:
                    del self.pending_items[vid]
                    self._remove_from_tree(vid)

            # Atualiza status
            count = len(self.pending_items)
            self.status_label.config(text=f"{count} item(ns) aguardando validação" if count else "Aguardando itens...",
                                     foreground="green" if count else "gray")

        except Exception as e:
            self._log(f"Erro ao escanear fila: {e}")

    def _add_to_tree(self, vid, data):
        tipo = data.get("tipo", "?")
        site = data.get("site", "?")
        horario = datetime.now().strftime("%H:%M:%S")
        preview = data.get("texto", "")[:80].replace("\n", " ")
        self.tree.insert("", tk.END, iid=vid, values=(vid, tipo, site, horario, preview))
        self._log(f"Novo item na fila: {tipo} de {site} ({vid})")

    def _remove_from_tree(self, vid):
        try:
            self.tree.delete(vid)
        except Exception:
            pass

    def _on_select(self, event):
        selection = self.tree.selection()
        if not selection:
            self._clear_detail()
            return
        vid = selection[0]
        self.current_vid = vid
        item = self.pending_items.get(vid)
        if not item:
            return
        data = item["data"]
        self.lbl_tipo.config(text=f"Tipo: {data.get('tipo', '?')}")
        self.lbl_site.config(text=f"Site: {data.get('site', '?')}")
        self.lbl_time.config(text=f"Hora: {datetime.now().strftime('%H:%M:%S')}")
        self.txt_content.config(state=tk.NORMAL)
        self.txt_content.delete("1.0", tk.END)
        self.txt_content.insert(tk.END, data.get("texto", ""))
        self.txt_content.config(state=tk.DISABLED)
        self.btn_aprovar.config(state=tk.NORMAL)
        self.btn_editar.config(state=tk.NORMAL)
        self.btn_reprovar.config(state=tk.NORMAL)

    def _clear_detail(self):
        self.current_vid = None
        self.lbl_tipo.config(text="Tipo: —")
        self.lbl_site.config(text="Site: —")
        self.lbl_time.config(text="Hora: —")
        self.txt_content.config(state=tk.NORMAL)
        self.txt_content.delete("1.0", tk.END)
        self.txt_content.config(state=tk.DISABLED)
        self.btn_aprovar.config(state=tk.DISABLED)
        self.btn_editar.config(state=tk.DISABLED)
        self.btn_reprovar.config(state=tk.DISABLED)

    def _decide(self, acao):
        if not self.current_vid:
            return
        item = self.pending_items.get(self.current_vid)
        if not item:
            return
        data = item["data"]
        texto = data.get("texto", "")

        if acao == "editar":
            self._open_editor(texto)
            return

        # Escreve resposta
        resp_data = {"acao": acao, "texto": texto}
        try:
            item["resp_path"].write_text(json.dumps(resp_data, ensure_ascii=False), encoding="utf-8")
            self._log(f"Decisão '{acao}' enviada para {self.current_vid}")
        except Exception as e:
            self._log(f"Erro ao escrever resposta: {e}")

    def _open_editor(self, texto_original):
        """Abre janela de edição de texto."""
        if self.editor_window and self.editor_window.winfo_exists():
            self.editor_window.lift()
            return

        self.editor_window = tk.Toplevel(self.root)
        self.editor_window.title("Editar Texto")
        self.editor_window.geometry("700x500")
        self.editor_window.transient(self.root)
        self.editor_window.grab_set()

        ttk.Label(self.editor_window, text="Edite o texto e clique em 'Aprovar Editado':").pack(pady=5, padx=10, anchor=tk.W)

        txt = scrolledtext.ScrolledText(self.editor_window, wrap=tk.WORD, font=("Consolas", 10))
        txt.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        txt.insert("1.0", texto_original)

        btn_frame = ttk.Frame(self.editor_window)
        btn_frame.pack(fill=tk.X, padx=10, pady=10)

        def salvar_editado():
            novo = txt.get("1.0", "end-1c")
            resp_data = {"acao": "aprovar", "texto": novo}
            item = self.pending_items.get(self.current_vid)
            if item:
                try:
                    item["resp_path"].write_text(json.dumps(resp_data, ensure_ascii=False), encoding="utf-8")
                    self._log(f"Texto editado e aprovado para {self.current_vid}")
                except Exception as e:
                    self._log(f"Erro ao salvar editado: {e}")
            self.editor_window.destroy()

        ttk.Button(btn_frame, text="✅ Aprovar Editado", command=salvar_editado).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text="❌ Cancelar", command=self.editor_window.destroy).pack(side=tk.RIGHT, padx=5)

    def _open_queue_folder(self):
        import subprocess
        try:
            if sys.platform == "win32":
                subprocess.Popen(["explorer", str(FILA)])
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(FILA)])
            else:
                subprocess.Popen(["xdg-open", str(FILA)])
        except Exception as e:
            self._log(f"Erro ao abrir pasta: {e}")

    def _clean_orphans(self):
        """Remove arquivos de resposta sem pendente correspondente."""
        count = 0
        for f in FILA.glob("resposta_*.json"):
            try:
                f.unlink()
                count += 1
            except Exception:
                pass
        for f in FILA.glob("pendente_*.tmp"):
            try:
                f.unlink()
                count += 1
            except Exception:
                pass
        self._log(f"Limpeza: {count} arquivo(s) órfão(s) removido(s)")


def main():
    root = tk.Tk()
    # Tenta usar tema moderno
    try:
        root.tk.call("source", "azure.tcl")
        root.tk.call("set_theme", "light")
    except Exception:
        pass
    app = WebChatUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()