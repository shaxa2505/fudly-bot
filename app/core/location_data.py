"""Location data helpers for region/district selection."""
from __future__ import annotations

from app.core.utils import normalize_city

# Minimal region -> districts mapping (extend as needed).
_REGION_DISTRICTS: dict[str, list[dict[str, str]]] = {
    "Самарканд": [
        {"ru": "Самарканд", "uz": "Samarqand"},
        {"ru": "Каттакурган", "uz": "Kattaqo'rg'on"},
        {"ru": "Акдарья", "uz": "Oqdaryo"},
        {"ru": "Булунгур", "uz": "Bulung'ur"},
        {"ru": "Джамбай", "uz": "Jomboy"},
        {"ru": "Иштыхон", "uz": "Ishtixon"},
        {"ru": "Кошрабад", "uz": "Qo'shrabot"},
        {"ru": "Нарпай", "uz": "Narpay"},
        {"ru": "Нурабад", "uz": "Nurobod"},
        {"ru": "Пайарык", "uz": "Payariq"},
        {"ru": "Пастдаргом", "uz": "Pastdarg'om"},
        {"ru": "Пахтачи", "uz": "Paxtachi"},
        {"ru": "Тайлак", "uz": "Toyloq"},
        {"ru": "Ургут", "uz": "Urgut"},
    ],
}


def get_districts_for_region(region: str | None, lang: str = "ru") -> list[tuple[str, str]]:
    """Return [(label, canonical_ru)] for district selection."""
    if not region:
        return []
    region_key = normalize_city(region)
    districts = _REGION_DISTRICTS.get(region_key, [])
    if not districts:
        return []
    label_key = "ru" if lang == "ru" else "uz"
    result: list[tuple[str, str]] = []
    for item in districts:
        label = item.get(label_key) or item.get("ru")
        canonical = item.get("ru")
        if label and canonical:
            result.append((label, canonical))
    return result


def get_district_label(
    region: str | None, district: str | None, lang: str = "ru"
) -> str | None:
    """Return district label in requested language, fallback to stored value."""
    if not district:
        return None
    region_key = normalize_city(region) if region else None
    if not region_key or region_key not in _REGION_DISTRICTS:
        return district
    label_key = "ru" if lang == "ru" else "uz"
    for item in _REGION_DISTRICTS[region_key]:
        if item.get("ru", "").lower() == district.lower():
            return item.get(label_key) or district
    return district
