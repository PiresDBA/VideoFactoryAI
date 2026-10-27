# -*- coding: utf-8 -*-
import sys
sys.stdout.reconfigure(encoding='utf-8')

with open('VideoFactoryAI/agent.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find all broken print statements
for i, line in enumerate(lines):
    if 'print("  [OK]' in line and not line.strip().endswith('")') and not line.strip().endswith('")\n'):
        print(f"Line {i+1}: {repr(line)}")
    if line.strip() == '")' or line.strip() == '")\n':
        print(f"Line {i+1}: {repr(line)} - orphaned closing")

print("Total lines:", len(lines))