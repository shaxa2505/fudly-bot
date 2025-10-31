import shutil
import os
from datetime import datetime

# Создаём имя папки с timestamp
timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
backup_dir = f'd:\\проект\\backup_{timestamp}'

# Создаём папку
os.makedirs(backup_dir, exist_ok=True)

# Список файлов для бэкапа
files_to_backup = [
    'bot.py',
    'database.py',
    'keyboards.py',
    'localization.py',
    'fudly.db',
    '.env'
]

# Копируем файлы
copied = 0
for file in files_to_backup:
    src = f'd:\\проект\\{file}'
    if os.path.exists(src):
        shutil.copy2(src, backup_dir)
        print(f'✅ {file}')
        copied += 1
    else:
        print(f'⚠️ {file} - не найден')

print(f'\n🎉 БЭКАП ГОТОВ!')
print(f'📁 Папка: {backup_dir}')
print(f'📦 Скопировано файлов: {copied}')
