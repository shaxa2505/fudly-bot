try:
    from localization import TEXTS, get_text
    print(f"✅ SUCCESS!")
    print(f"TEXTS type: {type(TEXTS)}")
    print(f"TEXTS keys: {list(TEXTS.keys())}")
    print(f"RU 'hot_offers': {get_text('ru', 'hot_offers')}")
    print(f"UZ 'hot_offers': {get_text('uz', 'hot_offers')}")
except IndentationError as e:
    print(f"❌ INDENTATION ERROR:")
    print(f"  {e}")
except SyntaxError as e:
    print(f"❌ SYNTAX ERROR:")
    print(f"  {e}")
    print(f"  Line {e.lineno}: {e.text}")
