import sys
import os
import shutil

# Clear ALL pycache directories
for root, dirs, files in os.walk('.'):
    for d in dirs:
        if d == '__pycache__':
            shutil.rmtree(os.path.join(root, d), ignore_errors=True)
    for f in files:
        if f.endswith('.pyc') or f.endswith('.pyo'):
            os.remove(os.path.join(root, f))

# Clear modules
import sys
for m in list(sys.modules.keys()):
    if 'ytdlp' in m.lower():
        del sys.modules[m]

import importlib
import sys
sys.path.insert(0, 'VideoFactoryAI')

import ytdlp_downloader as yd
print('Module file:', yd.__file__)

import inspect
src = inspect.getsource(yd._check_ytdlp_available)
print('Source:')
print(src[:200])