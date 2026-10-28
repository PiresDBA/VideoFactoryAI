"""Smoke test: test local media with multiple photo selection for makete_ho script."""
import sys, os
sys.path.insert(0, r'C:\Fabrica-de-videos\VideoFactoryAI')

# Read the script
script_path = r'C:\Fabrica-de-videos\roteiros\makete_ho.txt'
with open(script_path, 'r', encoding='utf-8') as f:
    script_text = f.read()

# Config for local-only mode
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

# Initialize MRA
project_dir = r'C:\Fabrica-de-videos'
agent_dir = r'C:\Fabrica-de-videos\VideoFactoryAI'
memory_dir = os.path.join(project_dir, 'memory')
cache_dir = os.path.join(project_dir, 'cache')

mra = MediaResearchAgent(cfg, project_dir, agent_dir / 'memory', cache_dir=cache_dir)

print(f'MRA inicializada')
print(f'  local_media_enabled: {mra.local_media_enabled}')
print(f'  media_source_mode: {mra.media_source_mode}')
print(f'  local_media_mode: {mra.local_media_mode}')
print(f'  Min local images: {mra.min_local_images}')
print(f'  Stock candidates per scene: {mra.stock_candidates_per_scene}')
print(f'  Local images indexed: {len(mra.local_media.index) if mra.local_media else 0}')

# Now test source_scene with first few scenes from plan
# First, let's plan scenes from the script
from agent import plan_scenes

script_text_sample = script_text[:2000]  # Use first part for planning
scenes = plan_scenes(script_text_sample, cfg, topic='maquete escala HO ferromodelismo')

print(f'\nCenas planejadas: {len(scenes)}')
for i, s in enumerate(scenes[:3], 1):
    print(f'  Cena {i}: tipo={s["tipo"]}, duracao={s["duration"]}s, query={s.get("query", "")[:50]}')

# Now test source_all with local media review
print(f'\n--- Testando source_all com revisão local ---')

# Set up the review callback to allow multiple selections
original_review = mra.local_media_review_callback

def multi_selection_callback(scene, candidate):
    """Allow user to select multiple photos per scene."""
    print(f'\n[REVISÃO LOCAL] Cena {scene.get("id", "?")}:')
    print(f'  Candidato: {candidate["title"]}')
    print(f'  Caminho: {candidate["path"]}')
    print(f'  Score: {candidate["score"]:.3f}')
    print(f'  Deseja selecionar esta foto? (aprovar/saltar/selecionar mais): ', end='')
    choice = input().strip().lower()
    
    if choice in {'aprovar', 'a', 's'}:
        return [candidate["path"]]  # Return list with single path
    elif choice in {'selecionar mais', 'm'}:
        # Return the current candidate plus ask for more
        return [candidate["path"]]
    elif choice in {'pular', 'p', 'rejeitar', 'r'}:
        return None
    else:
        print('  Opção inválida, tentando novamente...')
        return multi_selection_callback(scene, candidate)

mra.local_media_review_callback = multi_selection_callback

# Try source_scene for first scene
if scenes:
    first_scene = scenes[0]
    print(f'\nTestando source_scene para cena {first_scene["id"]}')
    print(f'  Query: {first_scene.get("query", "")[:60]}')
    print(f'  Tipo: {first_scene["tipo"]}')
    
    try:
        result = mra.source_scene(first_scene)
        print(f'  Resultado: {result}')
        if result:
            print(f'  Arquivo: {os.path.basename(result)}')
    except Exception as e:
        print(f'  ERRO: {type(e).__name__}: {str(e)[:200]}')
else:
    print('Nenhuma cena gerada!')