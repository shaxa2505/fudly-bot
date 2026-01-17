"""geo_reference_tables

Revision ID: 20260218_005
Revises: 004_store_location_slugs
Create Date: 2026-02-18 00:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union
import re

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "005_geo_reference"
down_revision: Union[str, None] = "004_store_location_slugs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_SUFFIX_RE = re.compile(
    r"\s+(?:shahri|shahar|shahr|tumani|tuman|viloyati|viloyat|region|district|province|oblast|oblasti"
    r"|город|район|область|шахри|шахар|тумани|туман|вилоят)\b",
    re.IGNORECASE,
)


def _normalize_slug(value: str) -> str:
    value_clean = " ".join(value.strip().split())
    value_clean = value_clean.split(",")[0]
    value_clean = re.sub(r"\s*\([^)]*\)", "", value_clean)
    value_clean = _SUFFIX_RE.sub("", value_clean).strip(" ,")
    value_clean = re.sub(r"[^\w\s]", " ", value_clean, flags=re.UNICODE)
    value_clean = " ".join(value_clean.split())
    return value_clean.lower()


_REGIONS: list[dict[str, object]] = [
    {
        "code": "tashkent_city",
        "ru": "Ташкент",
        "uz": "Toshkent",
        "is_city": 1,
        "districts": [
            {"ru": "Бектемир", "uz": "Bektemir"},
            {"ru": "Мирабад", "uz": "Mirobod"},
            {"ru": "Мирзо-Улугбек", "uz": "Mirzo Ulug'bek"},
            {"ru": "Сергелий", "uz": "Sergeli"},
            {"ru": "Шайхантахур", "uz": "Shayxontohur"},
            {"ru": "Учтепа", "uz": "Uchtepa"},
            {"ru": "Яшнабад", "uz": "Yashnobod"},
            {"ru": "Янгихаёт", "uz": "Yangihayot"},
            {"ru": "Юнусабад", "uz": "Yunusobod"},
            {"ru": "Яккасарай", "uz": "Yakkasaroy"},
            {"ru": "Алмазар", "uz": "Olmazor"},
            {"ru": "Чиланзар", "uz": "Chilonzor"},
        ],
    },
    {
        "code": "tashkent_region",
        "ru": "Ташкентская область",
        "uz": "Toshkent viloyati",
        "is_city": 0,
        "slug_uz": "toshkent_viloyati",
        "districts": [],
    },
    {
        "code": "andijan",
        "ru": "Андижан",
        "uz": "Andijon",
        "is_city": 0,
        "districts": [],
    },
    {
        "code": "bukhara",
        "ru": "Бухара",
        "uz": "Buxoro",
        "is_city": 0,
        "districts": [],
    },
    {
        "code": "fergana",
        "ru": "Фергана",
        "uz": "Farg'ona",
        "is_city": 0,
        "districts": [],
    },
    {
        "code": "jizzakh",
        "ru": "Джизак",
        "uz": "Jizzax",
        "is_city": 0,
        "districts": [],
    },
    {
        "code": "namangan",
        "ru": "Наманган",
        "uz": "Namangan",
        "is_city": 0,
        "districts": [],
    },
    {
        "code": "navoiy",
        "ru": "Навоий",
        "uz": "Navoiy",
        "is_city": 0,
        "districts": [],
    },
    {
        "code": "qashqadaryo",
        "ru": "Кашкадарья",
        "uz": "Qashqadaryo",
        "is_city": 0,
        "districts": [],
    },
    {
        "code": "samarkand",
        "ru": "Самарканд",
        "uz": "Samarqand",
        "is_city": 0,
        "districts": [
            {"ru": "Самарканд", "uz": "Samarqand"},
            {"ru": "Каттакурган", "uz": "Kattaqo'rg'on"},
            {"ru": "Акдарья", "uz": "Oqdaryo"},
            {"ru": "Булунгур", "uz": "Bulung'ur"},
            {"ru": "Джамбай", "uz": "Jomboy"},
            {"ru": "Иштыхан", "uz": "Ishtixon"},
            {"ru": "Кошрабад", "uz": "Qo'shrabot"},
            {"ru": "Нарпай", "uz": "Narpay"},
            {"ru": "Нурабад", "uz": "Nurobod"},
            {"ru": "Пайарык", "uz": "Payariq"},
            {"ru": "Пастдаргом", "uz": "Pastdarg'om"},
            {"ru": "Пахтачи", "uz": "Paxtachi"},
            {"ru": "Тайлак", "uz": "Toyloq"},
            {"ru": "Ургут", "uz": "Urgut"},
        ],
    },
    {
        "code": "sirdaryo",
        "ru": "Сырдарья",
        "uz": "Sirdaryo",
        "is_city": 0,
        "districts": [],
    },
    {
        "code": "surxondaryo",
        "ru": "Сурхандарья",
        "uz": "Surxondaryo",
        "is_city": 0,
        "districts": [],
    },
    {
        "code": "khorezm",
        "ru": "Хорезм",
        "uz": "Xorazm",
        "is_city": 0,
        "districts": [],
    },
    {
        "code": "karakalpakstan",
        "ru": "Каракалпакстан",
        "uz": "Qoraqalpog'iston",
        "is_city": 0,
        "districts": [],
    },
]


def upgrade() -> None:
    op.create_table(
        "geo_regions",
        sa.Column("region_id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("name_ru", sa.Text(), nullable=False),
        sa.Column("name_uz", sa.Text(), nullable=False),
        sa.Column("slug_ru", sa.Text(), nullable=False),
        sa.Column("slug_uz", sa.Text(), nullable=False),
        sa.Column("is_city", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("slug_ru", name="uq_geo_regions_slug_ru"),
        sa.UniqueConstraint("slug_uz", name="uq_geo_regions_slug_uz"),
    )

    op.create_table(
        "geo_districts",
        sa.Column("district_id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("region_id", sa.Integer(), nullable=False),
        sa.Column("name_ru", sa.Text(), nullable=False),
        sa.Column("name_uz", sa.Text(), nullable=False),
        sa.Column("slug_ru", sa.Text(), nullable=False),
        sa.Column("slug_uz", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["region_id"],
            ["geo_regions.region_id"],
            name="fk_geo_districts_region_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("region_id", "slug_ru", name="uq_geo_districts_region_slug_ru"),
        sa.UniqueConstraint("region_id", "slug_uz", name="uq_geo_districts_region_slug_uz"),
    )

    op.create_index("idx_geo_districts_region_id", "geo_districts", ["region_id"])

    op.add_column("users", sa.Column("region_id", sa.Integer(), nullable=True))
    op.add_column("users", sa.Column("district_id", sa.Integer(), nullable=True))
    op.add_column("stores", sa.Column("region_id", sa.Integer(), nullable=True))
    op.add_column("stores", sa.Column("district_id", sa.Integer(), nullable=True))

    op.create_foreign_key(
        "fk_users_region_id", "users", "geo_regions", ["region_id"], ["region_id"]
    )
    op.create_foreign_key(
        "fk_users_district_id", "users", "geo_districts", ["district_id"], ["district_id"]
    )
    op.create_foreign_key(
        "fk_stores_region_id", "stores", "geo_regions", ["region_id"], ["region_id"]
    )
    op.create_foreign_key(
        "fk_stores_district_id", "stores", "geo_districts", ["district_id"], ["district_id"]
    )

    op.create_index("idx_users_region_id", "users", ["region_id"])
    op.create_index("idx_users_district_id", "users", ["district_id"])
    op.create_index("idx_stores_region_id", "stores", ["region_id"])
    op.create_index("idx_stores_district_id", "stores", ["district_id"])

    conn = op.get_bind()
    existing_regions = conn.execute(sa.text("SELECT COUNT(*) FROM geo_regions")).scalar()
    if existing_regions:
        return

    for region in _REGIONS:
        region_ru = str(region["ru"])
        region_uz = str(region["uz"])
        slug_uz = region.get("slug_uz") or _normalize_slug(region_uz)
        region_row = conn.execute(
            sa.text(
                """
                INSERT INTO geo_regions (name_ru, name_uz, slug_ru, slug_uz, is_city)
                VALUES (:name_ru, :name_uz, :slug_ru, :slug_uz, :is_city)
                RETURNING region_id
                """
            ),
            {
                "name_ru": region_ru,
                "name_uz": region_uz,
                "slug_ru": _normalize_slug(region_ru),
                "slug_uz": slug_uz,
                "is_city": int(region.get("is_city", 0)),
            },
        ).fetchone()
        if not region_row:
            continue
        region_id = region_row[0]
        districts = region.get("districts", []) or []
        for district in districts:
            district_ru = str(district["ru"])
            district_uz = str(district["uz"])
            conn.execute(
                sa.text(
                    """
                    INSERT INTO geo_districts (
                        region_id, name_ru, name_uz, slug_ru, slug_uz
                    ) VALUES (
                        :region_id, :name_ru, :name_uz, :slug_ru, :slug_uz
                    )
                    """
                ),
                {
                    "region_id": region_id,
                    "name_ru": district_ru,
                    "name_uz": district_uz,
                    "slug_ru": _normalize_slug(district_ru),
                    "slug_uz": _normalize_slug(district_uz),
                },
            )


def downgrade() -> None:
    op.drop_index("idx_stores_district_id", table_name="stores")
    op.drop_index("idx_stores_region_id", table_name="stores")
    op.drop_index("idx_users_district_id", table_name="users")
    op.drop_index("idx_users_region_id", table_name="users")

    op.drop_constraint("fk_stores_district_id", "stores", type_="foreignkey")
    op.drop_constraint("fk_stores_region_id", "stores", type_="foreignkey")
    op.drop_constraint("fk_users_district_id", "users", type_="foreignkey")
    op.drop_constraint("fk_users_region_id", "users", type_="foreignkey")

    op.drop_column("stores", "district_id")
    op.drop_column("stores", "region_id")
    op.drop_column("users", "district_id")
    op.drop_column("users", "region_id")

    op.drop_index("idx_geo_districts_region_id", table_name="geo_districts")
    op.drop_table("geo_districts")
    op.drop_table("geo_regions")
