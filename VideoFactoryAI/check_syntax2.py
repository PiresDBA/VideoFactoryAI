import py_compile
import os
import sys

path = os.path.join("C:\\Fabrica-de-videos\\VideoFactoryAI", "script_writer_agent.py")
try:
    py_compile.compile(path, doraise=True)
    print("script_writer_agent.py: OK")
except py_compile.PyCompileError as e:
    print(f"script_writer_agent.py: ERROR - {e}")
    sys.exit(1)
print("Done")