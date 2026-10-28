# Quick verification that all changes are in place
import re

# Check agent.py
with open(r'C:\Fabrica-de-videos\VideoFactoryAI\agent.py', 'r', encoding='utf-8', errors='ignore') as f:
    agent_content = f.read()

# Check media_research_agent.py
with open(r'C:\Fabrica-de-videos\VideoFactoryAI\media_research_agent.py', 'r', encoding='utf-8', errors='ignore') as f:
    mra_content = f.read()

print('=== VERIFICACAO DAS ALTERACOES ===')
print()

# 1. Check _request_local_media_review returns bool
if 'def _request_local_media_review(scene: dict, candidate: dict):' in agent_content:
    print('OK: _request_local_media_review definida (sem -> list)')
else:
    print('ERRO: assinatura incorreta')

# 2. Check it uses LOCAL_MEDIA_REVIEW_MARKER
if 'LOCAL_MEDIA_REVIEW_MARKER + json.dumps(review)' in agent_content:
    print('OK: Usa LOCAL_MEDIA_REVIEW_MARKER para GUI')
else:
    print('ERRO: Nao usa o marker da GUI')

# 3. Check it returns True/False
if 'return True' in agent_content and 'return False' in agent_content:
    print('OK: Retorna True/False (bool)')
else:
    print('ERRO: Nao retorna bool')

# 4. Check media_research_agent.py handles bool
if 'isinstance(result, bool)' in mra_content:
    print('OK: _try_local_image lida com bool')
else:
    print('ERRO: Nao lida com bool')

# 5. Check it extracts path from match
if 'chosen_paths = [str(match' in mra_content:
    print('OK: Extrai path do match quando bool=True')
else:
    print('ERRO: Nao extrai path do match')

print()
print('=== Verificacao concluida ===')