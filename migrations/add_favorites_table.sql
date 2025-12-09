-- NOTE:
--   This project уже использует таблицу `favorites` (user_id + store_id),
--   создаваемую в `database_pg_module.schema` и используемую в
--   `database_pg_module.mixins.favorites.FavoritesMixin`.
--   Таблица `user_favorites` с offer_id и ссылкой на users(telegram_id)
--   не соответствует текущей доменной модели и может конфликтовать
--   со схемой. Поэтому миграция ниже помечена как NO-OP, чтобы
--   сохранить файл в репозитории, но не вносить изменений в БД.

-- NO-OP migration: favorites реализованы через таблицу `favorites`.
-- Оставлено только как документирование старой идеи Mini App.

-- If you ever need per-offer favorites for Mini App, создайте
-- отдельную согласованную миграцию под актуальную схему
-- (users.user_id, offers.offer_id) через Alembic, а этот файл
-- не используйте напрямую.
