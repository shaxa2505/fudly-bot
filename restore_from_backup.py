import shutil
import os

print("🔄 ВОССТАНОВЛЕНИЕ ИЗ БЭКАПА")
print("=" * 50)

# Ищем последний бэкап
backups = [d for d in os.listdir('d:\\проект') if d.startswith('backup_')]
if not backups:
    print("❌ Бэкапы не найдены!")
    exit(1)

latest_backup = sorted(backups)[-1]
backup_path = f'd:\\проект\\{latest_backup}'

print(f"📁 Найден бэкап: {latest_backup}")
print()

# Список файлов для восстановления
files = ['bot.py', 'database.py', 'keyboards.py', 'localization.py', 'fudly.db', '.env']

response = input("⚠️ ВНИМАНИЕ! Текущие файлы будут заменены. Продолжить? (yes/no): ")
if response.lower() != 'yes':
    print("❌ Отменено")
    exit(0)

print("\n🔄 Восстановление...")
restored = 0
for file in files:
    src = os.path.join(backup_path, file)
    dst = f'd:\\проект\\{file}'
    if os.path.exists(src):
        shutil.copy2(src, dst)
        print(f'✅ {file}')
        restored += 1
    else:
        print(f'⚠️ {file} - не найден в бэкапе')

print(f'\n🎉 ВОССТАНОВЛЕНО!')
print(f'📦 Файлов восстановлено: {restored}')
print(f'📁 Из бэкапа: {latest_backup}')
