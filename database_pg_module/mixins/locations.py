"""
Geo reference helpers for region/district resolution.
"""
from __future__ import annotations

from typing import Any

from psycopg.rows import dict_row

from database_pg_module.mixins.offers import canonicalize_geo_slug


class LocationReferenceMixin:
    """Mixin for resolving region/district IDs from free-form input."""

    _REGION_MARKERS = ("viloyat", "viloyati", "region", "province", "oblast", "oblasti")
    _CITY_MARKERS = ("shahar", "shahri", "city", "gorod")

    def _normalize_geo_text(self, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        return " ".join(text.split())

    def _has_marker(self, value: str, markers: tuple[str, ...]) -> bool:
        lowered = value.lower()
        return any(marker in lowered for marker in markers)

    def _choose_region_row(
        self,
        rows: list[dict[str, Any]],
        prefer_region: bool,
        prefer_city: bool,
    ) -> dict[str, Any] | None:
        if not rows:
            return None
        if len(rows) == 1:
            return rows[0]
        if prefer_region:
            for row in rows:
                if not row.get("is_city"):
                    return row
        if prefer_city:
            for row in rows:
                if row.get("is_city"):
                    return row
        for row in rows:
            if row.get("is_city"):
                return row
        return rows[0]

    def resolve_geo_region(self, value: Any) -> dict[str, Any] | None:
        """Resolve a region row by user input."""
        value_clean = self._normalize_geo_text(value)
        if not value_clean:
            return None

        slug = canonicalize_geo_slug(value_clean)
        prefer_region = self._has_marker(value_clean, self._REGION_MARKERS)
        prefer_city = self._has_marker(value_clean, self._CITY_MARKERS)

        with self.get_connection() as conn:
            cursor = conn.cursor(row_factory=dict_row)
            rows: list[dict[str, Any]] = []
            if slug:
                cursor.execute(
                    """
                    SELECT region_id, name_ru, name_uz, slug_ru, slug_uz, is_city
                    FROM geo_regions
                    WHERE slug_ru = %s OR slug_uz = %s
                    """,
                    (slug, slug),
                )
                rows = [dict(row) for row in cursor.fetchall()]
            row = self._choose_region_row(rows, prefer_region, prefer_city)
            if row:
                return row

            cursor.execute(
                """
                SELECT region_id, name_ru, name_uz, slug_ru, slug_uz, is_city
                FROM geo_regions
                WHERE lower(name_ru) = lower(%s) OR lower(name_uz) = lower(%s)
                ORDER BY is_city DESC, region_id
                LIMIT 1
                """,
                (value_clean, value_clean),
            )
            row = cursor.fetchone()
            if row:
                return dict(row)

            pattern = f"%{value_clean}%"
            cursor.execute(
                """
                SELECT region_id, name_ru, name_uz, slug_ru, slug_uz, is_city
                FROM geo_regions
                WHERE name_ru ILIKE %s OR name_uz ILIKE %s
                ORDER BY is_city DESC, region_id
                LIMIT 1
                """,
                (pattern, pattern),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def resolve_geo_district(
        self,
        value: Any,
        region_id: int | None = None,
    ) -> dict[str, Any] | None:
        """Resolve a district row by user input."""
        value_clean = self._normalize_geo_text(value)
        if not value_clean:
            return None

        slug = canonicalize_geo_slug(value_clean)

        with self.get_connection() as conn:
            cursor = conn.cursor(row_factory=dict_row)
            if region_id is not None:
                cursor.execute(
                    """
                    SELECT district_id, region_id, name_ru, name_uz, slug_ru, slug_uz
                    FROM geo_districts
                    WHERE region_id = %s AND (slug_ru = %s OR slug_uz = %s)
                    """,
                    (region_id, slug, slug),
                )
                row = cursor.fetchone()
                if row:
                    return dict(row)
            else:
                cursor.execute(
                    """
                    SELECT district_id, region_id, name_ru, name_uz, slug_ru, slug_uz
                    FROM geo_districts
                    WHERE slug_ru = %s OR slug_uz = %s
                    """,
                    (slug, slug),
                )
                rows = [dict(row) for row in cursor.fetchall()]
                if len(rows) == 1:
                    return rows[0]
                if len(rows) > 1:
                    return None

            if region_id is not None:
                cursor.execute(
                    """
                    SELECT district_id, region_id, name_ru, name_uz, slug_ru, slug_uz
                    FROM geo_districts
                    WHERE region_id = %s AND (lower(name_ru) = lower(%s) OR lower(name_uz) = lower(%s))
                    LIMIT 1
                    """,
                    (region_id, value_clean, value_clean),
                )
                row = cursor.fetchone()
                if row:
                    return dict(row)

                pattern = f"%{value_clean}%"
                cursor.execute(
                    """
                    SELECT district_id, region_id, name_ru, name_uz, slug_ru, slug_uz
                    FROM geo_districts
                    WHERE region_id = %s AND (name_ru ILIKE %s OR name_uz ILIKE %s)
                    LIMIT 1
                    """,
                    (region_id, pattern, pattern),
                )
                row = cursor.fetchone()
                return dict(row) if row else None

            cursor.execute(
                """
                SELECT district_id, region_id, name_ru, name_uz, slug_ru, slug_uz
                FROM geo_districts
                WHERE lower(name_ru) = lower(%s) OR lower(name_uz) = lower(%s)
                LIMIT 1
                """,
                (value_clean, value_clean),
            )
            row = cursor.fetchone()
            if row:
                return dict(row)

            pattern = f"%{value_clean}%"
            cursor.execute(
                """
                SELECT district_id, region_id, name_ru, name_uz, slug_ru, slug_uz
                FROM geo_districts
                WHERE name_ru ILIKE %s OR name_uz ILIKE %s
                LIMIT 1
                """,
                (pattern, pattern),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def resolve_geo_location(
        self,
        *,
        region: Any | None = None,
        district: Any | None = None,
        city: Any | None = None,
    ) -> dict[str, Any]:
        """Resolve region/district ids and canonical labels."""
        region_value = region if region is not None else city
        region_row = self.resolve_geo_region(region_value) if region_value else None
        region_id = region_row.get("region_id") if region_row else None
        district_row = (
            self.resolve_geo_district(district, region_id) if district else None
        )
        return {
            "region_id": region_id,
            "district_id": district_row.get("district_id") if district_row else None,
            "region_name_ru": region_row.get("name_ru") if region_row else None,
            "district_name_ru": district_row.get("name_ru") if district_row else None,
        }

    def get_geo_regions(
        self,
        *,
        lang: str = "ru",
        include_cities: bool = True,
    ) -> list[dict[str, Any]]:
        """Return geo regions for UI selection."""
        name_col = "name_ru" if lang == "ru" else "name_uz"
        with self.get_connection() as conn:
            cursor = conn.cursor(row_factory=dict_row)
            query = f"SELECT region_id, name_ru, name_uz, is_city FROM geo_regions"
            params: list[Any] = []
            if not include_cities:
                query += " WHERE is_city = %s"
                params.append(0)
            query += f" ORDER BY {name_col}"
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    def get_geo_districts(
        self,
        region_id: int,
        *,
        lang: str = "ru",
    ) -> list[dict[str, Any]]:
        """Return districts for a region."""
        name_col = "name_ru" if lang == "ru" else "name_uz"
        with self.get_connection() as conn:
            cursor = conn.cursor(row_factory=dict_row)
            cursor.execute(
                f"""
                SELECT district_id, region_id, name_ru, name_uz
                FROM geo_districts
                WHERE region_id = %s
                ORDER BY {name_col}
                """,
                (region_id,),
            )
            return [dict(row) for row in cursor.fetchall()]
