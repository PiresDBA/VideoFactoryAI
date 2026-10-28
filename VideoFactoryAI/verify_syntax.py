import py_compile
import os
import sys

files = [
    "agent.py",
    "media_research_agent.py", 
    "script_writer_agent.py"
]

for f in files:
    path = os.path.join("C:\\Fabrica-de-videos\\VideoFactoryAI", f)
    try:
        py_compile.compile(path, doraise=True)
        print(f"{f}: OK")
    except py_compile.PyCompileError as e:
        print(f"{f}: ERROR - {e}")
        sys.exit(1)

print("All files syntax OK")