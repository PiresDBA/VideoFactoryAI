import re

with open('C:\Fabrica-de-videos\VideoFactoryAI\script_writer_agent.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Nova funcao _generate_with_ai - substituindo a antiga
new_func = '''    def _generate_with_ai(
        self,
        topic: str,
        target_words: int,
        canal_key: str,
        research: Dict[str, str]
    ) -> Optional[str]:
        \"\"\"
        Gera uma narracao factual usando o agente personalizado @roteiroparavideos.

        CORRECAO v3.12: O prompt anterior era extremamente longo (com criterios editoriais,
        regras de evitacao, estrutura, formato de saida, etc.), o que tornava a geracao
        muito restrita e frequentemente gerava roteiros de baixa qualidade.

        Agora o prompt e simples e direto, usando apenas o comando @roteiroparavideos
        que ja e um agente personalizado configurado para criar roteiros completos.
        \"\"\"
        persona = self._get_persona_safely(canal_key)

        # Calcula a duracao em minutos a partir do numero de palavras
        duration_min = max(1.0, target_words / self.WORDS_PER_MINUTE)

        # Prompt simples e direto, usando apenas o comando @roteiroparavideos
        prompt = f"@roteiroparavideos {topic}, porque aconteceu, quem se beneficou disso, roteiro de {duration_min:.0f} minutos."

        for model in ("openai-fast", "mistral"):
            try:
                response = requests.post(
                    "https://text.pollinations.ai/",
                    json={
                        "messages": [
                            {
                                "role": "system",
                                "content": persona,
                            },
                            {"role": "user", "content": prompt},
                        ],
                        "model": model,
                        "seed": 42,
                    },
                    timeout=60,
                )
                if response.status_code != 200:
                    continue

                raw = response.text.strip()
                if len(raw) < 100:
                    continue
                if raw.startswith("{"):
                    try:
                        payload = json.loads(raw)
                        raw = payload.get("content") or payload.get("text") or raw
                    except (ValueError, TypeError):
                        pass

                raw = re.sub(r"```.*?```", "", raw, flags=re.DOTALL)
                clean = self._clean_script(raw)
                count = len(clean.split())

                minimum = min(max(45, int(target_words * 0.60)), target_words)
                if count >= minimum:
                    print(f"    [IA] Roteiro gerado via {model} ({count} palavras).")
                    return clean
            except requests.RequestException:
                continue
            except Exception as exc:
                print(f"    [WARN] Falha no modelo {model}: {exc}")

        return None'''

# Substituir a funcao antiga pela nova - pega o bloco que vai do 'def _generate_with_ai' ate 'return None'
pattern = r'def _generate_with_ai\([^}]+\n.*?return None'
content = re.sub(pattern, new_func, content, flags=re.DOTALL)

with open('C:\Fabrica-de-videos\VideoFactoryAI\script_writer_agent.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Substituicao do _generate_with_ai concluida')