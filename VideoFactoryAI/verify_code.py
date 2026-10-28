# Quick check on the key code sections
with open(r'C:\Fabrica-de-videos\VideoFactoryAI\agent.py', 'r', encoding='utf-8', errors='ignore') as f:
    content = f.read()

# 1. Check _request_local_media_review function exists and returns list
if 'def _request_local_media_review(scene: dict, candidate: dict) -> list:' in content:
    print('OK: _request_local_media_review returns list')
else:
    print('FAIL: _request_local_media_review signature missing')

# 2. Check it has the new implementation (choices loop)
if 'choices = []' in content and 'while True:' in content:
    print('OK: Multi-selection loop present')
else:
    print('FAIL: Multi-selection loop missing')

# 3. Check it uses candidate['title'] not image_title
if "candidate['image_title']" in content:
    print('FAIL: Still uses image_title (WRONG)')
elif "candidate['title']" in content:
    print('OK: Uses title (CORRECT)')
else:
    print('? Title pattern unclear')

# 4. Check media_research_agent.py chosen_paths check
with open(r'C:\Fabrica-de-videos\VideoFactoryAI\media_research_agent.py', 'r', encoding='utf-8', errors='ignore') as f:
    content2 = f.read()

old = 'if not chosen_paths or isinstance(chosen_paths, bool):'
new = 'if chosen_paths is None or isinstance(chosen_paths, bool):'

if old in content2:
    print('FAIL: media_research_agent.py: old check still present')
elif new in content2:
    print('OK: media_research_agent.py: new check (is None) present')
else:
    print('? media_research_agent.py: check pattern unclear')

print()
print('=== Code verification complete ===')