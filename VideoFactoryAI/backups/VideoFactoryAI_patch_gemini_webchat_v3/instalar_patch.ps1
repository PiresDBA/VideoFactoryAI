# VideoFactoryAI — patch de recuperação Gemini e repetição adaptativa L4
# Executar a partir da pasta VideoFactoryAI_patch_gemini_webchat_v3 extraída.
$ErrorActionPreference = "Stop"

$patchDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectDir = Split-Path -Parent $patchDir
$targetModule = Join-Path $projectDir "gemini_webchat_image.py"
$targetAgent = Join-Path $projectDir "media_research_agent.py"
$replacementModule = Join-Path $patchDir "gemini_webchat_image.py"

if (!(Test-Path $targetAgent)) {
    throw "Não encontrei media_research_agent.py em: $projectDir. Extraia a pasta v3 diretamente dentro da pasta VideoFactoryAI."
}
if (!(Test-Path $replacementModule)) { throw "Arquivo de substituição ausente: $replacementModule" }

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backupDir = Join-Path $projectDir ("_backup_gemini_patch_" + $stamp)
New-Item -ItemType Directory -Path $backupDir | Out-Null
foreach ($f in @("gemini_webchat_image.py", "media_research_agent.py")) {
    $p = Join-Path $projectDir $f
    if (Test-Path $p) { Copy-Item $p (Join-Path $backupDir $f) }
}
Write-Host "Backup criado em: $backupDir" -ForegroundColor Green

# Substitui somente o módulo de integração com Gemini.
Copy-Item $replacementModule $targetModule -Force

# Usa UTF-8 explicitamente e aplica alterações localizadas no agente.
$enc = New-Object System.Text.UTF8Encoding($false)
$content = [System.IO.File]::ReadAllText($targetAgent)

# Captura a justificativa visual para alimentar a próxima tentativa L4.
$oldReject = 'if not approved:\s*\r?\n\s*try:\s*\r?\n\s*Path\(media_path\)\.unlink\(missing_ok=True\)\s*\r?\n\s*except Exception:\s*\r?\n\s*pass'
$newReject = @'
if not approved:
                    try:
                        self._last_visual_feedback = reason
                    except Exception:
                        pass
                    try:
                        Path(media_path).unlink(missing_ok=True)
                    except Exception:
                        pass
'@.TrimEnd()
if ($content -match [regex]::Escape('self._last_visual_feedback = reason')) {
    Write-Host "Feedback visual já parece estar instrumentado; mantendo." -ForegroundColor Yellow
} elseif ([regex]::IsMatch($content, $oldReject)) {
    $content = [regex]::Replace($content, $oldReject, [System.Text.RegularExpressions.MatchEvaluator]{ param($m) $newReject }, 1)
} else {
    Write-Warning "Não consegui localizar com segurança o bloco de rejeição visual. A recuperação do Gemini será instalada, mas o feedback adaptativo poderá não ser aplicado."
}

# Troca apenas o bloco L4, mantendo L1-L3 e auditoria final intactos.
$startPattern = '(?s)        prompt = ai_prompt or img_query or scene\.get\("descricao", f"Cena \{sid\}"\).*?(?=    # ── Batch com Auditoria Final Anti-Duplicata)'
if (-not [regex]::IsMatch($content, $startPattern)) {
    # Fallback tolerante a comentários/codificação legada, sem depender do texto do comentário.
    $startPattern = '(?s)        prompt = ai_prompt or img_query or scene\.get\("descricao", f"Cena \{sid\}"\).*?(?=    def _enforce_final_uniqueness\()'
}
if (-not [regex]::IsMatch($content, $startPattern)) {
    throw "Não consegui localizar o bloco L4 com segurança. O arquivo original foi preservado no backup: $backupDir"
}

$newL4 = @'
        # NÍVEL 4 — Gemini Web com até 3 tentativas e feedback da avaliação.
        # L1-L3 continuam sendo tentados antes de chegar aqui; não cria placeholders.
        base_prompt = ai_prompt or img_query or scene.get("descricao", f"Cena {sid}")
        feedback = ""
        generated = None
        max_gemini_attempts = max(1, min(3, int(os.environ.get("VF_GEMINI_RETRIES", "3"))))
        try:
            from gemini_webchat_image import generate_image
        except Exception as exc:
            print(f"    [L4-Gemini] Integração indisponível: {exc}")
            generate_image = None

        for attempt in range(1, max_gemini_attempts + 1):
            if generate_image is None:
                break
            if attempt == 1:
                prompt = base_prompt
            else:
                suggestions = scene.get("_visual_search_suggestions", [])
                suggestion_text = ", ".join(str(x) for x in suggestions[:5]) if isinstance(suggestions, list) else ""
                prompt = (
                    f"{base_prompt}\n\nCORREÇÃO OBRIGATÓRIA após rejeição visual anterior: {feedback}\n"
                    "Não repita a composição/objeto que foi rejeitado. Gere uma imagem que mostre "
                    "diretamente os elementos exigidos na cena. Priorize os detalhes específicos "
                    "do roteiro e evite assunto apenas genericamente relacionado."
                )
                if suggestion_text:
                    prompt += f"\nTermos positivos sugeridos pelo avaliador: {suggestion_text}."
            print(f"    [L4-Gemini] Tentativa {attempt}/{max_gemini_attempts} para cena {sid:02d}...")
            try:
                generated = generate_image(
                    prompt=prompt,
                    dest_path=dest_path,
                    scene_id=sid,
                    topic=getattr(self, "_current_topic", "documentario"),
                )
            except Exception as exc:
                print(f"    [L4-Gemini] Falha na geração: {exc}")
                generated = None
            if not generated or not os.path.isfile(dest_path):
                print(f"    [L4-Gemini] Não foi possível recuperar arquivo na tentativa {attempt}.")
                continue

            generated_hash = _file_hash(dest_path)
            if generated_hash and generated_hash in self.used_hashes:
                print(f"    [L4-Gemini] Imagem duplicada; tentando outra geração.")
                try: os.remove(dest_path)
                except OSError: pass
                feedback = "A imagem anterior era duplicada de outra cena; gere uma composição diferente."
                continue

            # Limpa feedback anterior para que a validação desta tentativa preencha o novo.
            try:
                self._last_visual_feedback = ""
            except Exception:
                pass
            if not self._validate_asset(scene, dest_path, "gemini_webchat"):
                feedback = str(getattr(self, "_last_visual_feedback", "") or
                               "A imagem não foi aprovada na avaliação visual. Gere outra imagem específica.")
                print(f"    [L4-Gemini] Reprovada; motivo para nova tentativa: {feedback[:350]}")
                try: os.remove(dest_path)
                except OSError: pass
                generated = None
                continue

            url, lic = generated
            if generated_hash:
                self.used_hashes[generated_hash] = sid
            self.used_paths[dest_path] = sid
            self._record_hit("gemini_webchat")
            self._add_report(sid, 4, "gemini_webchat", url, lic, dest_path, "ai_generated")
            return dest_path

        print(f"    [L4-Gemini] Nenhuma imagem aprovada após {max_gemini_attempts} tentativa(s). Cena {sid:02d} pendente; sem imagem falsa.")
        try:
            if os.path.exists(dest_path): os.remove(dest_path)
        except OSError:
            pass
        return None

'@
$content = [regex]::Replace($content, $startPattern, [System.Text.RegularExpressions.MatchEvaluator]{ param($m) $newL4 }, 1)

[System.IO.File]::WriteAllText($targetAgent, $content, $enc)

# Verificação sintática com o interpretador do projeto, se disponível.
$python = "C:\Docling\venv\Scripts\python.exe"
if (Test-Path $python) {
    & $python -m py_compile $targetModule $targetAgent
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "A verificação sintática falhou. Restaurando os dois arquivos do backup."
        Copy-Item (Join-Path $backupDir "media_research_agent.py") $targetAgent -Force
        if (Test-Path (Join-Path $backupDir "gemini_webchat_image.py")) {
            Copy-Item (Join-Path $backupDir "gemini_webchat_image.py") $targetModule -Force
        } else {
            Remove-Item $targetModule -Force -ErrorAction SilentlyContinue
        }
        throw "Patch revertido automaticamente por falha de sintaxe."
    }
    Write-Host "Verificação sintática Python: OK" -ForegroundColor Green
} else {
    Write-Warning "Python em C:\Docling\venv não encontrado; rode py_compile manualmente."
}
Write-Host ""
Write-Host "Patch instalado. L1-L3 não foram reescritos; L4 agora tenta até 3 gerações adaptativas." -ForegroundColor Green
Write-Host "Backup para reversão: $backupDir"
