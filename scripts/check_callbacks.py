#!/usr/bin/env python3
"""
Скрипт для автоматической проверки всех callback обработчиков в bot.py
Проверяет:
1. Наличие await callback.answer()
2. Обработку ошибок (try-except)
3. Правильность работы с состояниями
"""

import re
import ast
from pathlib import Path

def check_callback_handlers(file_path: str):
    """Проверяет все callback обработчики в файле"""
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Находим все @dp.callback_query декораторы
    callback_pattern = r'@dp\.callback_query\([^)]+\)\s*async\s+def\s+(\w+)\([^)]*\):'
    callbacks = re.finditer(callback_pattern, content)
    
    issues = []
    callback_count = 0
    
    for match in callbacks:
        callback_count += 1
        func_name = match.group(1)
        start_pos = match.start()
        
        # Находим конец функции (следующий @dp или @dp. или конец файла)
        next_decorator = re.search(r'\n@dp\.', content[start_pos + 100:])
        if next_decorator:
            func_end = start_pos + 100 + next_decorator.start()
        else:
            func_end = len(content)
        
        func_code = content[start_pos:func_end]
        
        # Проверка 1: Есть ли await callback.answer()
        if 'await callback.answer()' not in func_code and 'await callback.answer(' not in func_code:
            issues.append({
                'type': 'missing_answer',
                'function': func_name,
                'line': content[:start_pos].count('\n') + 1,
                'severity': 'HIGH',
                'message': f'❌ {func_name}: Отсутствует await callback.answer()'
            })
        
        # Проверка 2: Есть ли try-except
        if 'try:' not in func_code:
            issues.append({
                'type': 'no_error_handling',
                'function': func_name,
                'line': content[:start_pos].count('\n') + 1,
                'severity': 'MEDIUM',
                'message': f'⚠️  {func_name}: Отсутствует обработка ошибок (try-except)'
            })
        elif 'except Exception' in func_code:
            # Проверяем что в except есть логирование
            except_block = func_code[func_code.index('except Exception'):]
            if 'logger.error' not in except_block and 'logger.warning' not in except_block:
                issues.append({
                    'type': 'no_logging_in_except',
                    'function': func_name,
                    'line': content[:start_pos].count('\n') + 1,
                    'severity': 'LOW',
                    'message': f'ℹ️  {func_name}: В except нет логирования'
                })
        
        # Проверка 3: Если есть state, проверяем что есть await state.clear() или set_state
        if 'state: FSMContext' in func_code:
            if 'await state.clear()' not in func_code and 'await state.set_state(' not in func_code and 'await state.update_data(' not in func_code:
                issues.append({
                    'type': 'unused_state',
                    'function': func_name,
                    'line': content[:start_pos].count('\n') + 1,
                    'severity': 'LOW',
                    'message': f'ℹ️  {func_name}: state передан но не используется'
                })
    
    return issues, callback_count

def print_report(issues, callback_count):
    """Выводит отчет о проблемах"""
    print(f"\n{'='*80}")
    print(f"📊 ОТЧЁТ О ПРОВЕРКЕ CALLBACK ОБРАБОТЧИКОВ")
    print(f"{'='*80}\n")
    
    print(f"✅ Всего callback обработчиков: {callback_count}\n")
    
    if not issues:
        print("🎉 Все проверки пройдены! Проблем не найдено.\n")
        return
    
    # Группируем по типам
    by_type = {}
    for issue in issues:
        issue_type = issue['type']
        if issue_type not in by_type:
            by_type[issue_type] = []
        by_type[issue_type].append(issue)
    
    # Выводим статистику
    high_count = sum(1 for i in issues if i['severity'] == 'HIGH')
    medium_count = sum(1 for i in issues if i['severity'] == 'MEDIUM')
    low_count = sum(1 for i in issues if i['severity'] == 'LOW')
    
    print(f"🔴 КРИТИЧНЫХ: {high_count}")
    print(f"🟡 СРЕДНИХ: {medium_count}")
    print(f"🔵 НИЗКИХ: {low_count}\n")
    
    print(f"{'='*80}\n")
    
    # Выводим детали
    for issue_type, issue_list in sorted(by_type.items(), key=lambda x: len(x[1]), reverse=True):
        print(f"\n📋 {issue_type.upper().replace('_', ' ')} ({len(issue_list)} проблем):")
        print("-" * 80)
        for issue in sorted(issue_list, key=lambda x: x['line']):
            print(f"  {issue['message']}")
            print(f"     Строка: {issue['line']}")
        print()

def generate_fix_script(issues, output_file='fix_callbacks.txt'):
    """Генерирует список функций для исправления"""
    high_priority = [i for i in issues if i['severity'] == 'HIGH']
    
    if not high_priority:
        return
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("КРИТИЧНЫЕ ФУНКЦИИ ДЛЯ ИСПРАВЛЕНИЯ:\n")
        f.write("="*80 + "\n\n")
        
        for issue in sorted(high_priority, key=lambda x: x['line']):
            f.write(f"Функция: {issue['function']}\n")
            f.write(f"Строка: {issue['line']}\n")
            f.write(f"Проблема: {issue['message']}\n")
            f.write(f"Исправление: Добавить 'await callback.answer()' в конце функции или перед return\n")
            f.write("-"*80 + "\n")
    
    print(f"\n💾 Список критичных исправлений сохранён в: {output_file}")

if __name__ == "__main__":
    bot_file = Path(__file__).parent / "bot.py"
    
    print("🔍 Анализирую bot.py...")
    issues, callback_count = check_callback_handlers(str(bot_file))
    
    print_report(issues, callback_count)
    
    if issues:
        generate_fix_script(issues)
        print(f"\n{'='*80}")
        print("💡 РЕКОМЕНДАЦИИ:")
        print("1. Сначала исправьте все КРИТИЧНЫЕ проблемы (missing_answer)")
        print("2. Затем добавьте обработку ошибок (try-except)")
        print("3. Добавьте логирование в except блоки")
        print(f"{'='*80}\n")
