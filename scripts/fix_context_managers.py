"""Fix all incorrect context manager usage in bot.py"""
import re

# Read the file
with open('bot.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Pattern to find incorrect usage:
# conn = db.get_connection()
# cursor = conn.cursor()
# ... code ...
# conn.commit()
# conn.close()

# Replace pattern
def fix_context_manager(match):
    indent = match.group(1)
    code_block = match.group(2)
    
    # Remove conn.commit() and conn.close() lines
    code_block = re.sub(r'\n\s*conn\.commit\(\)', '', code_block)
    code_block = re.sub(r'\n\s*conn\.close\(\)', '', code_block)
    
    # Add indentation to the code block
    code_lines = code_block.split('\n')
    indented_code = '\n'.join([(' ' * 4 + line if line.strip() else line) for line in code_lines])
    
    return f"{indent}with db.get_connection() as conn:\n{indent}    cursor = conn.cursor(){indented_code}"

# Pattern: find conn = db.get_connection() followed by cursor = conn.cursor() 
# and capture everything until next empty line or function/handler definition
pattern = r'(\s*)conn = db\.get_connection\(\)\n\s*cursor = conn\.cursor\(\)(.*?)(?=\n\s*(?:async def|def|@|class|\Z))'

content_fixed = re.sub(pattern, fix_context_manager, content, flags=re.DOTALL)

# Write back
with open('bot.py', 'w', encoding='utf-8') as f:
    f.write(content_fixed)

print("✅ Fixed all context manager usage issues!")
