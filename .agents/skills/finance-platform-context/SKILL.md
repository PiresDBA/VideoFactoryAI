---
name: finance-platform-context
description: Contexto arquitetural completo, modelagem de dados, motor temporal e regras operacionais do Finance AI Copilot. Ative esta skill antes de inspecionar ou alterar o projeto para obter visão completa imediata sem precisar varrer múltiplos arquivos.
metadata:
  version: 1.0.0
  origin: project-local
---

# 🧠 Finance Platform Context — Skill do Finance AI Copilot

Esta skill contém o mapa completo de arquitetura, contratos de dados, regras de negócio e procedimentos operacionais do **Finance AI Copilot**.

---

## 🎯 1. Propósito do Sistema

O **Finance AI Copilot** é um agregador e consolidador financeiro local no estilo *Family Office*, projetado para funcionar 100% offline e com privacidade absoluta:
- **Banco de Dados**: SQLite local em `data/finance_copilot.db` gerenciado por SQLAlchemy.
- **Relatório B3**: Ingestão do Relatório Consolidado Mensal da B3 (`.xlsx`) com abas de Ações, Fundos (FIIs/ETFs), Renda Fixa, Tesouro Direto, Proventos e Negociações.
- **Histórico Temporal Permanente**: Nenhuma planilha sobrescreve a anterior. Cada importação é arquivada com `competencia` (YYYY-MM), `origem` (PF ou PJ), `data_importacao` e `hash_arquivo` (SHA-256).
- **IA Local**: Orquestração via Ollama local com livre escolha de modelos no frontend (`qwen2.5-coder:3b`, `qwen2.5-coder-4k`, `gemma4-turbo`, `ornith`, etc.) e fallback analítico determinístico.

---

## 🗺️ 2. Mapa Rápido de Arquivos e Responsabilidades

| Caminho | Responsabilidade Principal |
| :--- | :--- |
| [`database/models.py`](file:///c:/finance-antigravity/database/models.py) | Modelos ORM: tabelas históricas (`Importacao`, `SnapshotAtivo`, `SnapshotProvento`) e operacionais (`Position`, `Account`, etc.). |
| [`database/crud.py`](file:///c:/finance-antigravity/database/crud.py) | Funções de persistência atômica cumulativa, busca por hash e listagem de importações. |
| [`collectors/normalization_pipeline.py`](file:///c:/finance-antigravity/collectors/normalization_pipeline.py) | Ingestão de arquivos, cálculo de SHA-256, detecção de duplicatas e gravação dupla (histórico + operacional). |
| [`parsers/b3_consolidated_report.py`](file:///c:/finance-antigravity/parsers/b3_consolidated_report.py) | Parser multi-abas do Excel da B3 (Ações, Fundos, Renda Fixa, Tesouro, Proventos, Negociações). |
| [`analytics/engine.py`](file:///c:/finance-antigravity/analytics/engine.py) | Funções analíticas: `get_historical_timeline`, `get_historical_metrics`, `get_historical_growth`, `get_historical_ytd`, patrimônio e alocação. |
| [`agents/ollama_client.py`](file:///c:/finance-antigravity/agents/ollama_client.py) | Cliente HTTP do Ollama (`/api/tags`), listagem de modelos instalados e fallback. |
| [`agents/copilot_agent.py`](file:///c:/finance-antigravity/agents/copilot_agent.py) | Agente Copilot: síntese de consultas temporais ("quanto eu tinha em...", "crescimento entre...", "patrimônio PF/PJ") e integração LLM. |
| [`agents/rag.py`](file:///c:/finance-antigravity/agents/rag.py) | Construtor do contexto RAG com linha do tempo consolidada e benchmarks financeiros. |
| [`frontend/app.py`](file:///c:/finance-antigravity/frontend/app.py) | Interface Streamlit (filtro de titularidade PF/PJ/Consolidado, seletor de modelos Ollama e tabelas permanentes). |
| [`frontend/components/charts.py`](file:///c:/finance-antigravity/frontend/components/charts.py) | Gráficos Plotly: `plot_historical_timeline`, `plot_historical_pf_vs_pj`, exposição e alocação. |
| [`docs/CHANGELOG_AI.md`](file:///c:/finance-antigravity/docs/CHANGELOG_AI.md) | Log contínuo de alterações feitas por agentes com comandos de rollback. |
| [`docs/DECISIONS.md`](file:///c:/finance-antigravity/docs/DECISIONS.md) | Architectural Decision Records (ADRs). |

---

## 🗄️ 3. Estrutura das Tabelas de Histórico Temporal

```python
class Importacao(Base):
    __tablename__ = "importacoes"
    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String(255), nullable=False)
    file_hash = Column(String(64), unique=True, index=True, nullable=False) # SHA-256
    competencia = Column(String(7), nullable=False, index=True)            # YYYY-MM
    origem = Column(String(10), nullable=False, default="PF", index=True)  # "PF" ou "PJ"
    institution_code = Column(String(50), nullable=False, default="b3")
    total_patrimonio = Column(Float, default=0.0)
    total_investimentos = Column(Float, default=0.0)
    data_importacao = Column(DateTime, default=datetime.utcnow)
    
    ativos = relationship("SnapshotAtivo", back_populates="importacao", cascade="all, delete-orphan")
    proventos = relationship("SnapshotProvento", back_populates="importacao", cascade="all, delete-orphan")
```

- Cada importação possui uma coleção de `SnapshotAtivo` e `SnapshotProvento`.
- A unicidade de arquivos é garantida pelo `file_hash` SHA-256.
- A unicidade lógica para relatórios consolidados da B3 é por `(competencia, origem)`.

---

## ⚙️ 4. Fluxo de Ingestão e Deduplicação

1. O arquivo chega em `NormalizationPipeline.process_file(...)`.
2. O SHA-256 é calculado via `NormalizationPipeline.calculate_file_hash(content)`.
3. Se o hash já existir em `db.query(models.Importacao)`, o pipeline lança `ValueError("Arquivo duplicado detectado!...")`.
4. Se for B3 e a combinação `(competencia, origem)` já existir sem a flag `replace_existing=True`, rejeita com aviso para evitar substituição acidental.
5. Em caso de sucesso:
   - Grava atômica e permanentemente na tabela `importacoes` e filhas.
   - Alimenta também as tabelas correntes (`positions`, `accounts`, etc.) para manter total retrocompatibilidade com o restante do app.

---

## 📊 5. Funções Analíticas Principais (`analytics/engine.py`)

- `get_historical_timeline(db, origem="CONSOLIDADO")`: Retorna lista ordenada por competência com valores de PF, PJ, Consolidado e taxas de crescimento nominal e percentual mês a mês.
- `get_historical_metrics(db, competencia, origem="CONSOLIDADO")`: Retorna dicionário com `total_patrimonio`, `total_investimentos`, `por_categoria`, `por_custodiante`, `maiores_ativos` e `proventos_total`.
- `get_historical_growth(db, comp_inicial, comp_final, origem="CONSOLIDADO")`: Variação entre dois meses específicos.
- `get_historical_ytd(db, ano, origem="CONSOLIDADO")`: Crescimento acumulado do ano selecionado.

---

## 🤖 6. Copilot IA e Ollama

- **Endpoint de Tags**: `GET {OLLAMA_BASE_URL}/api/tags` lista os modelos locais.
- **Modelos Locais Típicos do Ambiente**: `qwen2.5-coder:3b`, `qwen2.5-coder-4k`, `gemma4-turbo-perfeito`, `ornith-1.5:9b`.
- **Seleção Dinâmica**: Feita na página 7 do Streamlit via `st.selectbox`, enviada via parâmetro `preferred_model` para `copilot_agent.answer_question(db, question, preferred_model)`.
- **Respostas Temporais**: O método `_synthesize_local_answer` em `copilot_agent.py` interpreta perguntas sobre meses, crescimento e titularidade PF/PJ mesmo se o Ollama estiver offline.

---

## 🧪 7. Comandos de Validação e Testes

Sempre use o Python do ambiente virtual `.venv`:
```powershell
# Executar todos os 44 testes
.venv\Scripts\python -m pytest tests/ -v

# Executar apenas testes do módulo temporal
.venv\Scripts\python -m pytest tests/test_historical_imports.py -v

# Iniciar o Streamlit
.venv\Scripts\python -m streamlit run frontend/app.py
```

---

## ⚠️ 8. Regras Operacionais para Próximos Agentes

1. **Nunca sobrescrever dados de importações anteriores**: O sistema é cumulativo e auditável.
2. **Ao modificar testes**, lembre-se de que testes E2E (`test_real_cycle.py`) realizam limpeza de tabelas de teste antes de importar arquivos de exemplo; sempre incluir `db.query(models.SnapshotProvento).delete()`, `db.query(models.SnapshotAtivo).delete()` e `db.query(models.Importacao).delete()`.
3. **Sempre atualizar `docs/CHANGELOG_AI.md`** ao realizar qualquer alteração estrutural no código.
