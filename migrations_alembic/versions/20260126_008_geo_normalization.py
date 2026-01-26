"""geo_normalization

Revision ID: 008_geo_normalization
Revises: 007_ratings_booking_unique
Create Date: 2026-01-26 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "008_geo_normalization"
down_revision: Union[str, None] = "007_ratings_booking_unique"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Normalize city_slug from geo_regions where possible (cities)
    op.execute(
        """
        UPDATE stores s
        SET city_slug = gr.slug_ru
        FROM geo_regions gr
        WHERE gr.is_city = 1
          AND s.city IS NOT NULL
          AND (lower(s.city) = lower(gr.name_ru) OR lower(s.city) = lower(gr.name_uz))
          AND (s.city_slug IS DISTINCT FROM gr.slug_ru)
        """
    )

    # Fill/normalize region_id + region fields for stores
    op.execute(
        """
        UPDATE stores s
        SET region_id = gr.region_id,
            region = gr.name_ru,
            region_slug = gr.slug_ru
        FROM geo_regions gr
        WHERE (
                s.region IS NOT NULL
                AND (
                    lower(s.region) LIKE '%' || lower(gr.name_ru) || '%'
                    OR lower(s.region) LIKE '%' || lower(gr.name_uz) || '%'
                )
              )
           OR (
                s.region_slug IS NOT NULL
                AND (gr.slug_ru = s.region_slug OR gr.slug_uz = s.region_slug)
              )
           OR (
                s.city_slug IS NOT NULL
                AND (gr.slug_ru = s.city_slug OR gr.slug_uz = s.city_slug)
              )
           OR (
                s.city IS NOT NULL
                AND (lower(s.city) = lower(gr.name_ru) OR lower(s.city) = lower(gr.name_uz))
              )
        """
    )

    # Fill district_id for stores using district names/slugs + region scope if available
    op.execute(
        """
        UPDATE stores s
        SET district_id = gd.district_id
        FROM geo_districts gd
        LEFT JOIN geo_regions gr ON gr.region_id = gd.region_id
        WHERE s.district IS NOT NULL
          AND (
                (s.region_id IS NOT NULL AND gd.region_id = s.region_id)
             OR (s.region_id IS NULL AND s.region IS NOT NULL AND (
                    lower(s.region) LIKE '%' || lower(gr.name_ru) || '%'
                    OR lower(s.region) LIKE '%' || lower(gr.name_uz) || '%'
                ))
             OR (s.region_id IS NULL AND s.region_slug IS NOT NULL AND (
                    gr.slug_ru = s.region_slug OR gr.slug_uz = s.region_slug
                ))
          )
          AND (
                lower(gd.name_ru) = lower(s.district)
             OR lower(gd.name_uz) = lower(s.district)
             OR lower(s.district) LIKE '%' || lower(gd.name_ru) || '%'
             OR lower(s.district) LIKE '%' || lower(gd.name_uz) || '%'
             OR (s.district_slug IS NOT NULL AND (gd.slug_ru = s.district_slug OR gd.slug_uz = s.district_slug))
          )
        """
    )

    # Normalize region/district fields for stores from ids
    op.execute(
        """
        UPDATE stores s
        SET region = gr.name_ru,
            region_slug = gr.slug_ru
        FROM geo_regions gr
        WHERE s.region_id = gr.region_id
          AND (s.region IS DISTINCT FROM gr.name_ru OR s.region_slug IS DISTINCT FROM gr.slug_ru)
        """
    )
    op.execute(
        """
        UPDATE stores s
        SET district = gd.name_ru,
            district_slug = gd.slug_ru
        FROM geo_districts gd
        WHERE s.district_id = gd.district_id
          AND (s.district IS DISTINCT FROM gd.name_ru OR s.district_slug IS DISTINCT FROM gd.slug_ru)
        """
    )

    # Users: fill/normalize region_id from region/city
    op.execute(
        """
        UPDATE users u
        SET region_id = gr.region_id,
            region = gr.name_ru
        FROM geo_regions gr
        WHERE (u.region IS NOT NULL OR u.city IS NOT NULL)
          AND (
                (u.region IS NOT NULL AND (
                    lower(u.region) LIKE '%' || lower(gr.name_ru) || '%'
                    OR lower(u.region) LIKE '%' || lower(gr.name_uz) || '%'
                ))
             OR (u.city IS NOT NULL AND (lower(u.city) = lower(gr.name_ru) OR lower(u.city) = lower(gr.name_uz)))
          )
        """
    )

    # Users: fill/normalize district_id from district + region scope if available
    op.execute(
        """
        UPDATE users u
        SET district_id = gd.district_id,
            district = gd.name_ru
        FROM geo_districts gd
        LEFT JOIN geo_regions gr ON gr.region_id = gd.region_id
        WHERE u.district IS NOT NULL
          AND (
                u.region_id IS NULL OR gd.region_id = u.region_id
             OR (u.region_id IS NULL AND u.region IS NOT NULL AND (
                    lower(u.region) LIKE '%' || lower(gr.name_ru) || '%'
                    OR lower(u.region) LIKE '%' || lower(gr.name_uz) || '%'
                ))
          )
          AND (
                lower(gd.name_ru) = lower(u.district)
             OR lower(gd.name_uz) = lower(u.district)
             OR lower(u.district) LIKE '%' || lower(gd.name_ru) || '%'
             OR lower(u.district) LIKE '%' || lower(gd.name_uz) || '%'
          )
        """
    )

    # Users: normalize region/district names from ids
    op.execute(
        """
        UPDATE users u
        SET region = gr.name_ru
        FROM geo_regions gr
        WHERE u.region_id = gr.region_id
          AND (u.region IS DISTINCT FROM gr.name_ru OR u.region IS NULL)
        """
    )
    op.execute(
        """
        UPDATE users u
        SET district = gd.name_ru
        FROM geo_districts gd
        WHERE u.district_id = gd.district_id
          AND (u.district IS DISTINCT FROM gd.name_ru OR u.district IS NULL)
        """
    )


def downgrade() -> None:
    # Data normalization is not easily reversible; leave as no-op.
    pass
