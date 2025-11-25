"""Script to comment out legacy admin statistics handlers in bot.py."""


def comment_section(content: str, start_marker: str, end_marker: str) -> str:
    """Comment out a section of code between start and end markers."""
    start_idx = content.find(start_marker)
    if start_idx == -1:
        return content

    end_idx = content.find(end_marker, start_idx)
    if end_idx == -1:
        return content

    end_idx += len(end_marker)
    section = content[start_idx:end_idx]

    # Comment each line that isn't already a comment
    lines = section.split("\n")
    commented_lines = []
    for line in lines:
        if line.strip() and not line.lstrip().startswith("#"):
            commented_lines.append("# " + line)
        else:
            commented_lines.append(line)

    commented_section = "\n".join(commented_lines)
    return content[:start_idx] + commented_section + content[end_idx:]


path = "c:/Users/User/Desktop/fudly-bot-main/bot.py"
with open(path, encoding="utf-8") as f:
    content = f.read()

# Comment out admin_users
content = comment_section(
    content,
    '# @dp.message(F.text == "👥 Пользователи")',
    'await message.answer(text, parse_mode="HTML", reply_markup=kb.as_markup())',
)

# Comment out admin_stores
content = comment_section(
    content,
    '@dp.message(F.text == "🏪 Магазины")',
    'await message.answer(text, parse_mode="HTML", reply_markup=kb.as_markup())',
)

# Comment out admin_offers
content = comment_section(
    content,
    '@dp.message(F.text == "📦 Товары")',
    'await message.answer(text, parse_mode="HTML", reply_markup=kb.as_markup())',
)

# Comment out admin_bookings
content = comment_section(
    content,
    '@dp.message(F.text == "📋 Бронирования")',
    'await message.answer(text, parse_mode="HTML", reply_markup=kb.as_markup())',
)

with open(path, "w", encoding="utf-8") as f:
    f.write(content)

print("✅ Successfully commented out 4 legacy admin statistics handlers")
