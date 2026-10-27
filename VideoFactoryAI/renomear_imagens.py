import os
from pathlib import Path
import re
import unicodedata
import time
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from PIL import Image, ImageTk
import ollama

# --- CONFIGURAÇÕES ---
MODEL_NAME = "llava-phi3"
SUPPORTED_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.webp']
# ---------------------

class AppRenomeador(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Renomeador Inteligente de Imagens (Ollama - Nomes Diretos)")
        self.geometry("850x760")
        self.minsize(750, 680)
        
        self.dir_path = None
        self.image_files = []
        self.is_running = False
        
        self.create_widgets()

    def create_widgets(self):
        # Topo: Seleção de Pasta
        frame_top = ttk.LabelFrame(self, text=" Diretório de Trabalho ", padding=10)
        frame_top.pack(fill="x", padx=10, pady=10)

        self.lbl_path = ttk.Label(frame_top, text="Nenhuma pasta selecionada.", font=("Arial", 10))
        self.lbl_path.pack(side="left", fill="x", expand=True, padx=5)

        btn_browse = ttk.Button(frame_top, text="Selecionar Pasta...", command=self.select_directory)
        btn_browse.pack(side="right", padx=5)

        # Seção de Contexto e Opções Avançadas
        frame_options = ttk.LabelFrame(self, text=" Configurações de Análise e Direcionamento ", padding=10)
        frame_options.pack(fill="x", padx=10, pady=(0, 10))

        lbl_ctx_hint = ttk.Label(frame_options, text="Contexto Opcional (Ex: 'ferromodelismo maquete cortiça', 'bulldog'):", font=("Arial", 9, "italic"))
        lbl_ctx_hint.pack(anchor="w", pady=(0, 3))

        self.entry_context = ttk.Entry(frame_options, font=("Arial", 10))
        self.entry_context.pack(fill="x", expand=True, pady=(0, 8))

        # Checkbox para forçar o reprocessamento de tudo
        self.var_force_reprocess = tk.BooleanVar(value=True) # Deixado True por padrão para corrigir os nomes atuais
        chk_force = ttk.Checkbutton(
            frame_options, 
            text="Forçar reprocessamento de TODAS as imagens (sobrescrever nomes antigos)", 
            variable=self.var_force_reprocess
        )
        chk_force.pack(anchor="w", pady=2)

        # Centro: Preview e Telemetria Lateral
        frame_center = ttk.Frame(self)
        frame_center.pack(fill="both", expand=True, padx=10, pady=5)

        # Esquerda: Imagem Atual
        frame_preview = ttk.LabelFrame(frame_center, text=" Imagem em Análise ", padding=10)
        frame_preview.pack(side="left", fill="both", expand=True, padx=(0, 5))

        self.lbl_image_preview = ttk.Label(frame_preview, text="Sem imagem", anchor="center")
        self.lbl_image_preview.pack(fill="both", expand=True)

        # Direita: Painel de Telemetria e Estatísticas
        frame_telemetry = ttk.LabelFrame(frame_center, text=" Telemetria e Métricas ", padding=10)
        frame_telemetry.pack(side="right", fill="y", padx=(5, 0))

        self.lbl_stat_total = ttk.Label(frame_telemetry, text="Total: 0", font=("Arial", 10, "bold"))
        self.lbl_stat_total.pack(anchor="w", pady=5)

        self.lbl_stat_current = ttk.Label(frame_telemetry, text="Progresso: 0/0", font=("Arial", 10))
        self.lbl_stat_current.pack(anchor="w", pady=5)

        self.lbl_stat_time_item = ttk.Label(frame_telemetry, text="Tempo item atual: 0.0s", font=("Arial", 10))
        self.lbl_stat_time_item.pack(anchor="w", pady=5)

        self.lbl_stat_avg = ttk.Label(frame_telemetry, text="Média por imagem: --", font=("Arial", 10))
        self.lbl_stat_avg.pack(anchor="w", pady=5)

        self.lbl_stat_elapsed = ttk.Label(frame_telemetry, text="Tempo total decorrido: 00:00", font=("Arial", 10))
        self.lbl_stat_elapsed.pack(anchor="w", pady=5)

        # Barra de Progresso
        frame_progress = ttk.Frame(self, padding=10)
        frame_progress.pack(fill="x", padx=10)

        self.progress_bar = ttk.Progressbar(frame_progress, orient="horizontal", mode="determinate")
        self.progress_bar.pack(fill="x", pady=5)

        # Botão de Ação
        self.btn_start = ttk.Button(frame_progress, text="Iniciar Processamento", command=self.start_processing_thread, state="disabled")
        self.btn_start.pack(pady=5)

        # Inferior: Log de Atividades
        frame_log = ttk.LabelFrame(self, text=" Log de Execução ", padding=10)
        frame_log.pack(fill="both", expand=False, padx=10, pady=10, ipady=30)

        self.txt_log = tk.Text(frame_log, height=6, state="disabled", font=("Consolas", 9))
        scrollbar = ttk.Scrollbar(frame_log, orient="vertical", command=self.txt_log.yview)
        self.txt_log.configure(yscrollcommand=scrollbar.set)
        
        self.txt_log.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

    def log(self, message):
        self.txt_log.configure(state="normal")
        self.txt_log.insert("end", message + "\n")
        self.txt_log.see("end")
        self.txt_log.configure(state="disabled")

    def select_directory(self):
        dir_selected = filedialog.askdirectory(title="Selecione a pasta com as imagens")
        if dir_selected:
            self.dir_path = Path(dir_selected)
            self.lbl_path.config(text=str(self.dir_path))
            
            self.image_files = [f for f in self.dir_path.iterdir() if f.suffix.lower() in SUPPORTED_EXTENSIONS]
            total = len(self.image_files)
            
            self.lbl_stat_total.config(text=f"Total de imagens: {total}")
            self.progress_bar.config(value=0, maximum=total if total > 0 else 1)
            
            if total > 0:
                self.btn_start.config(state="normal")
                self.log(f"Pasta carregada: {self.dir_path} ({total} imagens encontradas).")
            else:
                self.btn_start.config(state="disabled")
                messagebox.showwarning("Aviso", "Nenhuma imagem suportada encontrada.")

    def clean_ai_output(self, text):
        """Remove preventivamente artigos, números e pronomes indesejados do início do nome."""
        text = text.lower().strip()
        
        # Remove palavras iniciais incômodas
        palavras_proibidas_inicio = [
            r'^um[_-]', r'^uma[_-]', r'^o[_-]', r'^a[_-]', r'^os[_-]', r'^as[_-]',
            r'^homem[_-]', r'^pessoa[_-]', r'^artesao[_-]', r'^cena[_-]', r'^foto[_-]',
            r'^imagem[_-]', r'^trabalhando[_-]', r'^construcao[_-]', r'^\d+[_-]'
        ]
        
        mudou = True
        while mudou:
            mudou = False
            for padrao in palavras_proibidas_inicio:
                novo_texto = re.sub(padrao, '', text)
                if novo_texto != text:
                    text = novo_texto
                    mudou = True
                    
        return text.strip()

    def sanitize_filename(self, text):
        text = self.clean_ai_output(text)
        
        text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii')
        text = text.lower().strip()
        text = re.sub(r'[^a-z0-9-_]', '_', text)
        text = re.sub(r'_+', '_', text).strip('_')
        
        # Garante que não comece com número ou underline residual
        text = re.sub(r'^[0-9_]+', '', text)
        
        return text[:120]

    def is_name_already_pertinent(self, filename_stem):
        if self.var_force_reprocess.get():
            return False

        if len(filename_stem) >= 80:
            return True
        
        padroes_automaticos = [
            r'^img[_-]?\d+',
            r'^dsc[_-]?\d+',
            r'^screenshot[_-]?\d*',
            r'^\d{8}[_-]\d{6}',
            r'^whatsapp[_-]image',
            r'^copia[_-]de',
        ]
        
        stem_lower = filename_stem.lower()
        for padrao in padroes_automaticos:
            if re.match(padrao, stem_lower):
                return False
                
        return False

    def prepare_image_for_ai(self, img_path):
        temp_path = img_path.with_name(f"_temp_ai_process{img_path.suffix}")
        try:
            with Image.open(img_path) as img:
                img.thumbnail((768, 768))
                if img.mode in ("RGBA", "P"):
                    img = img.convert("RGB")
                img.save(temp_path, quality=90)
            return temp_path
        except Exception:
            return img_path

    def display_preview(self, img_path):
        try:
            img = Image.open(img_path)
            img.thumbnail((220, 220))
            photo = ImageTk.PhotoImage(img)
            self.lbl_image_preview.config(image=photo, text="")
            self.lbl_image_preview.image = photo
        except Exception:
            self.lbl_image_preview.config(image="", text="Erro ao carregar preview")

    def start_processing_thread(self):
        if self.is_running or not self.image_files:
            return
        self.is_running = True
        self.btn_start.config(state="disabled")
        
        threading.Thread(target=self.process_images, daemon=True).start()

    def process_images(self):
        total = len(self.image_files)
        start_time_global = time.time()
        user_context = self.entry_context.get().strip()
        force_mode = self.var_force_reprocess.get()
        
        self.log("--- INICIANDO PROCESSAMENTO (NOMES DIRETOS) ---")
        if force_mode:
            self.log("[!]. Forçando reprocessamento de TODAS as imagens.")
        if user_context:
            self.log(f"Foco Temático Ativo: '{user_context}'")

        for idx, file_path in enumerate(self.image_files, 1):
            item_start_time = time.time()
            self.display_preview(file_path)
            
            if self.is_name_already_pertinent(file_path.stem):
                self.log(f"[{idx}/{total}] Pulado (Nome já é pertinente): {file_path.name}")
                self.progress_bar.config(value=idx)
                continue

            self.lbl_stat_current.config(text=f"Progresso: {idx}/{total} ({file_path.name})")
            self.log(f"[{idx}/{total}] Analisando: {file_path.name}...")

            temp_img_path = self.prepare_image_for_ai(file_path)

            try:
                # PROMPT EXTREMAMENTE DIRETO (SEM FRASES NARRATIVAS)
                base_prompt = (
                    "PROIBIDO iniciar com artigos (um, uma, o, a), pessoas (homem, artesao) ou descrições narrativas. "
                    "Comece OBRIGATÓRIAMENTE direto pelo objeto principal, estrutura ou material técnico em destaque (ex: cortica, trilho, maquete, locomotiva, bancada). "
                )

                if user_context:
                    prompt_text = (
                        f"{base_prompt} "
                        f"Contexto principal: '{user_context}'. "
                        "Liste os elementos técnicos, materiais reais e detalhes específicos separados por termos descritivos, formando uma frase sem verbos de ligação no início (mínimo de 15 palavras). "
                        "Responda EXCLUSIVAMENTE com os termos diretos, sem pontuação final."
                    )
                else:
                    prompt_text = (
                        f"{base_prompt} "
                        "Liste os elementos visuais, texturas e materiais específicos em uma sequência direta de termos técnicos (mínimo de 15 palavras). "
                        "Responda EXCLUSIVAMENTE com os termos diretos, sem pontuação final."
                    )

                response = ollama.chat(
                    model=MODEL_NAME,
                    messages=[{
                        'role': 'user',
                        'content': prompt_text,
                        'images': [str(temp_img_path)]
                    }],
                    options={
                        'num_predict': 70,
                        'temperature': 0.1
                    }
                )
                
                description = response['message']['content']
                new_name_base = self.sanitize_filename(description)
                
                if temp_img_path != file_path and temp_img_path.exists():
                    temp_img_path.unlink()

                if not new_name_base:
                    self.log(f"  -> Falha: IA retornou nome inválido. Ignorando.")
                    continue

                new_filename = f"{new_name_base}{file_path.suffix}"
                new_path = file_path.with_name(new_filename)
                
                counter = 1
                while new_path.exists() and new_path != file_path:
                    new_filename = f"{new_name_base}_{counter}{file_path.suffix}"
                    new_path = file_path.with_name(new_filename)
                    counter += 1

                file_path.rename(new_path)
                
                item_duration = time.time() - item_start_time
                self.log(f"  -> Sucesso: '{new_path.name}' ({len(new_name_base)} chars) [{item_duration:.1f}s]")
                
                self.lbl_stat_time_item.config(text=f"Tempo item atual: {item_duration:.1f}s")
                
                elapsed_global = time.time() - start_time_global
                avg_time = elapsed_global / idx
                self.lbl_stat_avg.config(text=f"Média por imagem: {avg_time:.1f}s")
                
                mins, secs = divmod(int(elapsed_global), 60)
                self.lbl_stat_elapsed.config(text=f"Tempo total decorrido: {mins:02d}:{secs:02d}")

            except Exception as e:
                if temp_img_path != file_path and temp_img_path.exists():
                    temp_img_path.unlink()
                self.log(f"  -> Erro ao processar {file_path.name}: {e}")

            self.progress_bar.config(value=idx)

        self.is_running = False
        self.btn_start.config(state="normal")
        self.log("--- PROCESSAMENTO CONCLUÍDO ---")
        messagebox.showinfo("Sucesso", "Todas as imagens foram renomeadas sem o número 1 ou termos genéricos!")

if __name__ == "__main__":
    app = AppRenomeador()
    app.mainloop()