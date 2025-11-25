# Script to remove duplicate handlers from bot.py
# Handlers have been extracted to modular files and are already integrated


# Read the bot.py file
with open("bot.py", encoding="utf-8") as f:
    content = f.read()
    lines = content.split("\n")

print(f"Original file: {len(lines)} lines")

# Define blocks to remove (line ranges)
# Phase 4: Remove legacy admin handlers (statistics, moderation, system commands)
blocks_to_remove = [
    # Legacy admin handlers (extracted to handlers/admin/legacy.py)
    # admin_analytics (📈 Аналитика) - comprehensive stats with CSV export
    # admin_pending_stores (🏪 Заявки на партнерство) - show pending applications
    # approve_store, reject_store - moderation callbacks
    # admin_all_offers (📋 Все предложения) - list all offers
    # admin_all_stores (🏪 Все магазины) - list stores with delete buttons
    # delete_store_callback - delete store handler
    # admin_broadcast (📢 Рассылка), admin_settings (⚙️ Настройки) - placeholders
    # cmd_migrate_db - DB migration command
    # cmd_enable_delivery - enable delivery command
    (452, 1064),  # ~612 lines of legacy admin handlers
]

# Create backup
with open("bot.py.backup3", "w", encoding="utf-8") as f:
    f.write(content)
print("✅ Created backup: bot.py.backup3")

# Remove blocks in reverse order (to preserve line numbers)
new_lines = lines.copy()
for start, end in reversed(blocks_to_remove):
    print(f"Removing lines {start}-{end} ({end-start+1} lines)")
    # Replace with placeholder comment
    placeholder = (
        f"# Lines {start}-{end}: Handlers extracted to modules (see PHASE3_INTEGRATION_COMPLETE.md)"
    )
    new_lines[start - 1 : end] = [placeholder]

# Write cleaned file
new_content = "\n".join(new_lines)
with open("bot.py", "w", encoding="utf-8") as f:
    f.write(new_content)

final_lines = len(new_lines)
removed = len(lines) - final_lines
print("\n✅ Cleanup complete!")
print(f"   Original: {len(lines)} lines")
print(f"   Final: {final_lines} lines")
print(f"   Removed: {removed} lines")
