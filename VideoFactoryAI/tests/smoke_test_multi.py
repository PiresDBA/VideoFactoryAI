"""Smoke test: verify multi-photo selection works for makete_ho script."""
import sys, os
sys.path.insert(0, r'C:\Fabrica-de-videos\VideoFactoryAI')

from media_research_agent import MediaResearchAgent

# Config for local-only mode with review
cfg = {
    'media': {
        'media_source_mode': 'local_only',
        'local_media_mode': 'required',
        'local_media_enabled': True,
        'local_media_folder': r'C:\Fabrica-de-videos\projetos\makete_ho\imagens',
        'local_ollama_model': 'llava-phi3',
        'local_ollama_url': 'http://127.0.0.1:11434',
        'local_ollama_candidate_count': 4,
        'local_ollama_timeout_s': 180,
        'local_similarity_threshold': 0.80,
        'skip_ollama': False,
        'gemini_only': False,
        'prefer_real_media': True,
    },
    'pipeline': {
        'resume_mode': False,
        'resumed_scene_ids': [],
        'force_regeneration': False,
    },
    'ffmpeg_path': r'C:\Fabrica-de-videos\ffmpeg\bin\ffmpeg.exe',
}

project_dir = r'C:\Fabrica-de-videos'
agent_dir = r'C:\Fabrica-de-videos\VideoFactoryAI'
memory_dir = os.path.join(project_dir, 'memory')
cache_dir = os.path.join(project_dir, 'cache')

print('=== Smoke Test: Multi-Photo Selection ===')
print()

# Initialize MRA
try:
    mra = MediaResearchAgent(cfg, project_dir, agent_dir / 'memory', cache_dir=cache_dir)
    print(f'✅ MRA inicializada')
    print(f'   Local images indexed: {len(mra.local_media.index) if mra.local_media else 0}')
    print(f'   Media source mode: {mra.media_source_mode}')
    print(f'   Local media mode: {mra.local_media_mode}')
except Exception as e:
    print(f'❌ Erro ao inicializar MRA: {e}')
    sys.exit(1)

# Read the script
script_path = r'C:\Fabrica-de-videos\roteiros\makete_ho.txt'
with open(script_path, 'r', encoding='utf-8') as f:
    script_text = f.read()

# Plan scenes
from agent import plan_scenes
scenes = plan_scenes(script_text[:3000], cfg, topic='maquete escala HO ferromodelismo')

print(f'📋 Cenas planejadas: {len(scenes)}')
print()

# Setup review callback (the fixed version)
def review_callback(scene, candidate):
    """Allow user to select multiple photos per scene."""
    print(f'[REVISÃO LOCAL] Cena {scene.get("id", "?")}:')
    print(f'  Candidato: {candidate["title"][:50]}...')
    print(f'  Score: {candidate["score"]:.3f}')
    print(f'  Caminho: {os.path.basename(candidate["path"])}')
    print('  Digite "aprovar" para selecionar, "pular" para ignorar, "fim" para terminar: ', end='')
    choices = []
    while True:
        choice = input().strip().lower()
        if choice in {'fim', 'finish', 'end', 'terminar'}:
            break
        elif choice in {'aprovar', 'a'}:
            choices.append(candidate["path"])
            print(f'  ✓ Selecionado')
        elif choice in {'pular', 'p', 'rejeitar', 'r'}:
            print(f'  ✗ Ignorado')
        else:
            print('  Opção inválida, digite "aprovar", "pular" ou "fim": ', end='')
    
    if not choices:
        return None
    print(f'  {len(choices)} foto(s) selecionada(s)')
    return choices

# Set the callback
mra.local_media_review_callback = review_callback

# Process first 3 scenes with multi-photo selection
print('🎯 Processando cenas com seleção múltipla de fotos...\n')

selected_assets = []
for i, scene in enumerate(scenes[:3], 1):
    print(f'--- Cena {scene["id"]} de 3 ---')
    print(f'Query: {scene.get("query", "")[:60]}')
    
    try:
        result = mra.source_scene(scene)
        if result:
            asset_name = os.path.basename(result)
            print(f'  ✓ Imagem selecionada: {asset_name}')
            selected_assets.append(result)
        else:
            print(f'  ⚠ Nenhuma imagem selecionada para esta cena')
    except Exception as e:
        print(f'  ❌ Erro: {str(e)[:100]}')
    
    print()

print('=' * 50)
print(f'Resultado: {len(selected_assets)} de 3 cenas tiveram imagens selecionadas')
if selected_assets:
    print(f'Assets selecionados: {selected_assets}')
print('=' * 50)
print('✅ Smoke test concluído!')