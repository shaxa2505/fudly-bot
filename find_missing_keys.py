#!/usr/bin/env python
"""Find missing localization keys"""
import re
import os

# Collect all keys from localization.py
with open('localization.py', 'r', encoding='utf-8') as f:
    loc_content = f.read()

# Find all keys in Russian section (simple pattern)
ru_keys = set(re.findall(r'"([a-z][a-z0-9_]+)":\s*["\']', loc_content))

# Collect all get_text usages from code
used_keys = set()
for root, dirs, files in os.walk('.'):
    dirs[:] = [d for d in dirs if d not in ['.git', '.venv', '__pycache__', 'node_modules', 'webapp', 'tests']]
    for f in files:
        if f.endswith('.py') and f != 'localization.py':
            try:
                with open(os.path.join(root, f), 'r', encoding='utf-8') as file:
                    content = file.read()
                    # get_text(lang, "key") patterns
                    matches = re.findall(r'get_text\s*\([^,]+,\s*["\']([a-z][a-z0-9_]+)["\']', content)
                    used_keys.update(matches)
            except:
                pass

missing = used_keys - ru_keys
if missing:
    print(f'Missing keys: {len(missing)}')
    for k in sorted(missing):
        print(f'  - {k}')
else:
    print('All keys are present!')
