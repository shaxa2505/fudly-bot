"""Fix localization.py unterminated strings."""
import re

with open('localization.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

fixed_lines = []
i = 0
while i < len(lines):
    line = lines[i]
    
    # Check if this is the problematic line
    if '"cart_delivery_min_order":' in line and not line.strip().endswith('",'):
        # This is a multi-line string that needs triple quotes
        # Collect all lines until we find the closing quote
        multiline = [line.rstrip().replace('"cart_delivery_min_order": "', '"cart_delivery_min_order": """')]
        i += 1
        while i < len(lines):
            next_line = lines[i]
            if next_line.strip().endswith('.",'):
                # Found the end
                multiline.append(next_line.rstrip().replace('.",', '.""",'))
                fixed_lines.extend(multiline)
                break
            else:
                multiline.append(next_line.rstrip())
            i += 1
    else:
        fixed_lines.append(line.rstrip())
    i += 1

with open('localization.py', 'w', encoding='utf-8') as f:
    f.write('\n'.join(fixed_lines) + '\n')

print('Fixed localization.py')
