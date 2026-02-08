"""
Легаси админские обработчики (система модерации, статистика)

Содержит:
- Статистика с экспортом CSV (admin_analytics)
- Модерация магазинов (pending/approve/reject)
- Просмотр магазинов и товаров
"""

import csv
import logging

from aiogram import F, Router, types
from aiogram.types import FSInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder

logger = logging.getLogger(__name__)
import os
from datetime import datetime, timedelta

from handlers.common.utils import html_escape

router = Router(name="admin_legacy")

# Dependencies будут внедрены через setup
_bot = None
_db = None
_get_text = None
_moderation_keyboard = None
_get_uzb_time = None
_ADMIN_ID = None
_DATABASE_URL = None


def setup(bot, db, get_text, moderation_keyboard, get_uzb_time, admin_id, database_url):
    """Инициализация зависимостей"""
    global _bot, _db, _get_text, _moderation_keyboard, _get_uzb_time, _ADMIN_ID, _DATABASE_URL
    _bot = bot
    _db = db
    _get_text = get_text
    _moderation_keyboard = moderation_keyboard
    _get_uzb_time = get_uzb_time
    _ADMIN_ID = admin_id
    _DATABASE_URL = database_url


# ============== СТАТИСТИКА С CSV ==============



@router.message(F.text == "?? ?????????")
async def admin_analytics(message: types.Message):
    """
    ??????????? ?????????? ? ????????? ? CSV

    ?????: ??????? ????????????? ?????? ????? ??????????
    """
    if message.from_user.id != _ADMIN_ID:
        await message.answer("? ?????? ????????")
        return

    try:
        def _safe_int(row) -> int:
            if not row:
                return 0
            value = row[0]
            return int(value) if value is not None else 0

        def _safe_number(row) -> float:
            if not row:
                return 0.0
            value = row[0]
            return float(value) if value is not None else 0.0

        lang = "ru"
        try:
            lang = _db.get_user_language(message.from_user.id)
        except Exception:
            pass

        period_end = _get_uzb_time() if _get_uzb_time else datetime.utcnow()
        period_start = period_end - timedelta(days=30)
        period_label = _get_text(lang, "admin_orders_period_30d")

        placeholder = "%s" if _DATABASE_URL and "postgres" in _DATABASE_URL else "?"
        date_filter = f"o.created_at >= {placeholder} AND o.created_at < {placeholder}"
        date_params = (period_start, period_end)

        with _db.get_connection() as conn:
            cursor = conn.cursor()

            # 1. ????? ?????????? ?????????????
            cursor.execute("SELECT COUNT(*) FROM users")
            total_users = _safe_int(cursor.fetchone())

            cursor.execute("SELECT COUNT(*) FROM users WHERE role = 'seller'")
            total_sellers = _safe_int(cursor.fetchone())

            cursor.execute("SELECT COUNT(*) FROM users WHERE role = 'customer'")
            total_customers = _safe_int(cursor.fetchone())

            cursor.execute("SELECT COUNT(*) FROM users WHERE language = 'ru'")
            ru_users = _safe_int(cursor.fetchone())

            cursor.execute("SELECT COUNT(*) FROM users WHERE language = 'uz'")
            uz_users = _safe_int(cursor.fetchone())

            # 2. ?????????? ?????????
            cursor.execute("SELECT COUNT(*) FROM stores WHERE status = 'active'")
            active_stores = _safe_int(cursor.fetchone())

            cursor.execute("SELECT COUNT(*) FROM stores WHERE status = 'pending'")
            pending_stores = _safe_int(cursor.fetchone())

            cursor.execute("SELECT COUNT(*) FROM stores WHERE status = 'rejected'")
            rejected_stores = _safe_int(cursor.fetchone())

            # 3. ?????????? ???????
            cursor.execute("SELECT COUNT(*) FROM offers WHERE status = 'active'")
            active_offers = _safe_int(cursor.fetchone())

            cursor.execute("SELECT COUNT(*) FROM offers WHERE status = 'expired'")
            expired_offers = _safe_int(cursor.fetchone())

            cursor.execute("SELECT COUNT(*) FROM offers WHERE status = 'sold_out'")
            sold_out_offers = _safe_int(cursor.fetchone())

            # 4. ?????? (???????????????)
            cursor.execute(f"SELECT COUNT(*) FROM orders o WHERE {date_filter}", date_params)
            total_orders = _safe_int(cursor.fetchone())

            cursor.execute(
                f"""
                SELECT o.order_status, COUNT(*)
                FROM orders o
                WHERE {date_filter}
                GROUP BY o.order_status
                """,
                date_params,
            )
            status_rows = cursor.fetchall() or []
            status_counts = {
                str(row[0] or "unknown"): int(row[1] or 0) for row in status_rows if row
            }

            active_statuses = ("pending", "preparing", "ready", "delivering")
            active_orders = sum(status_counts.get(s, 0) for s in active_statuses)
            completed_orders = status_counts.get("completed", 0)
            cancelled_orders = status_counts.get("cancelled", 0)
            rejected_orders = status_counts.get("rejected", 0)

            cursor.execute(
                f"""
                SELECT COALESCE(SUM(COALESCE(o.total_price, off.discount_price * o.quantity, 0)), 0)
                FROM orders o
                LEFT JOIN offers off ON o.offer_id = off.offer_id
                WHERE {date_filter} AND o.order_status = 'completed'
                """,
                date_params,
            )
            revenue_completed = _safe_number(cursor.fetchone())
            avg_ticket = revenue_completed / completed_orders if completed_orders else 0

            cursor.execute(
                f"""
                SELECT COALESCE(NULLIF(o.payment_method, ''), 'unknown') AS method, COUNT(*)
                FROM orders o
                WHERE {date_filter}
                GROUP BY 1
                ORDER BY COUNT(*) DESC
                """,
                date_params,
            )
            payment_methods = cursor.fetchall() or []

            cursor.execute(
                f"""
                SELECT COALESCE(NULLIF(o.payment_status, ''), 'unknown') AS status, COUNT(*)
                FROM orders o
                WHERE {date_filter}
                GROUP BY 1
                ORDER BY COUNT(*) DESC
                """,
                date_params,
            )
            payment_statuses = cursor.fetchall() or []

            cursor.execute(
                f"""
                SELECT
                    CASE
                        WHEN o.order_type IS NULL OR o.order_type = '' THEN
                            CASE WHEN o.delivery_address IS NULL THEN 'pickup' ELSE 'delivery' END
                        ELSE o.order_type
                    END AS order_type,
                    COUNT(*)
                FROM orders o
                WHERE {date_filter}
                GROUP BY 1
                ORDER BY COUNT(*) DESC
                """,
                date_params,
            )
            order_types = cursor.fetchall() or []

            cursor.execute(
                f"""
                SELECT COALESCE(s.name, '-') AS store_name,
                       COUNT(*) AS orders_count,
                       COALESCE(SUM(COALESCE(o.total_price, off.discount_price * o.quantity, 0)), 0) AS revenue
                FROM orders o
                LEFT JOIN stores s ON o.store_id = s.store_id
                LEFT JOIN offers off ON o.offer_id = off.offer_id
                WHERE {date_filter} AND o.order_status = 'completed'
                GROUP BY s.name
                ORDER BY revenue DESC
                LIMIT 5
                """,
                date_params,
            )
            top_stores = cursor.fetchall() or []

            cursor.execute(
                f"""
                SELECT o.order_id,
                       o.created_at,
                       o.order_status,
                       o.payment_status,
                       o.payment_method,
                       COALESCE(o.total_price, off.discount_price * o.quantity, 0) AS total_price,
                       COALESCE(s.name, '') AS store_name,
                       COALESCE(u.first_name, u.username, '') AS customer_name
                FROM orders o
                LEFT JOIN stores s ON o.store_id = s.store_id
                LEFT JOIN users u ON o.user_id = u.user_id
                LEFT JOIN offers off ON o.offer_id = off.offer_id
                WHERE {date_filter}
                ORDER BY o.created_at DESC
                LIMIT 10
                """,
                date_params,
            )
            recent_orders = cursor.fetchall() or []

            cursor.execute(
                f"""
                SELECT o.order_id,
                       o.created_at,
                       o.order_status,
                       o.payment_status,
                       o.payment_method,
                       CASE
                           WHEN o.order_type IS NULL OR o.order_type = '' THEN
                               CASE WHEN o.delivery_address IS NULL THEN 'pickup' ELSE 'delivery' END
                           ELSE o.order_type
                       END AS order_type,
                       COALESCE(o.total_price, off.discount_price * o.quantity, 0) AS total_price,
                       COALESCE(s.name, '') AS store_name,
                       COALESCE(u.first_name, u.username, '') AS customer_name,
                       COALESCE(u.phone, '') AS phone
                FROM orders o
                LEFT JOIN stores s ON o.store_id = s.store_id
                LEFT JOIN users u ON o.user_id = u.user_id
                LEFT JOIN offers off ON o.offer_id = off.offer_id
                WHERE {date_filter}
                ORDER BY o.created_at DESC
                LIMIT 500
                """,
                date_params,
            )
            order_rows = cursor.fetchall() or []

            # 5. ???-5 ????????? ?? ???????? ???????
            cursor.execute(
                """
                SELECT u.first_name, COUNT(o.offer_id) as offers_count
                FROM users u
                INNER JOIN stores s ON u.user_id = s.owner_id
                INNER JOIN offers o ON s.store_id = o.store_id
                WHERE o.status = 'active'
                GROUP BY u.user_id
                ORDER BY offers_count DESC
                LIMIT 5
                """
            )
            top_sellers = cursor.fetchall()

            # 6. ????? ?????????? ?????????
            cursor.execute(
                """
                SELECT category, COUNT(*) as count
                FROM offers
                WHERE status = 'active'
                GROUP BY category
                ORDER BY count DESC
                LIMIT 5
                """
            )
            top_categories = cursor.fetchall()

            # 7. ??????? discount
            cursor.execute(
                """
                SELECT AVG(((original_price - discount_price) * 100.0 / original_price)) as avg_discount
                FROM offers
                WHERE status = 'active' AND original_price > 0
                """
            )
            avg_discount_result = cursor.fetchone()
            avg_discount = (
                round(avg_discount_result[0], 1)
                if avg_discount_result and avg_discount_result[0]
                else 0
            )



        # ????????? ????????? ?????
        report_lines = [
            "?? <b>??????????? ?????????</b>",
            "",
            "?? <b>????????????</b>",
            f"? ?????: {total_users}",
            f"? ????????: {total_sellers}",
            f"? ??????????: {total_customers}",
            f"? ??????? ????: {ru_users}",
            f"? ????????? ????: {uz_users}",
            "",
            "?? <b>????????</b>",
            f"? ????????: {active_stores}",
            f"? ?? ?????????: {pending_stores}",
            f"? ???????????: {rejected_stores}",
            "",
            "?? <b>??????</b>",
            f"? ????????: {active_offers}",
            f"? ????????: {expired_offers}",
            f"? ????????????: {sold_out_offers}",
            "",
            f"?? <b>??????? ??????:</b> {avg_discount}%",
            "",
            "?? <b>???-5 ?????????:</b>",
        ]

        for i, (name, count) in enumerate(top_sellers, 1):
            report_lines.append(f"{i}. {name} ? {count} ???????")

        report_lines.append("")
        report_lines.append("?? <b>?????????? ?????????:</b>")

        category_names = {
            "bakery": "?? ????",
            "dairy": "?? ???????",
            "meat": "?? ????",
            "fruits": "?? ??????",
            "vegetables": "?? ?????",
            "ready_food": "?? ??????? ???",
        }

        for i, (cat, count) in enumerate(top_categories, 1):
            cat_name = category_names.get(cat, cat)
            report_lines.append(f"{i}. {cat_name} ? {count} ???????")

        report_lines.append("")
        report_lines.append(_get_text(lang, "admin_orders_analytics_title"))
        report_lines.append(_get_text(lang, "admin_orders_period").format(period=period_label))

        if total_orders == 0:
            report_lines.append("")
            report_lines.append(_get_text(lang, "admin_orders_empty"))
        else:
            report_lines.append("")
            report_lines.append(_get_text(lang, "admin_orders_summary"))
            report_lines.append(_get_text(lang, "admin_orders_total").format(count=total_orders))
            report_lines.append(_get_text(lang, "admin_orders_active").format(count=active_orders))
            report_lines.append(_get_text(lang, "admin_orders_completed").format(count=completed_orders))
            report_lines.append(_get_text(lang, "admin_orders_cancelled").format(count=cancelled_orders))
            report_lines.append(_get_text(lang, "admin_orders_rejected").format(count=rejected_orders))
            report_lines.append(
                _get_text(lang, "admin_orders_revenue").format(amount=f"{int(revenue_completed):,}")
            )
            report_lines.append(
                _get_text(lang, "admin_orders_avg_ticket").format(
                    amount=f"{int(avg_ticket):,}" if avg_ticket else "0"
                )
            )

            report_lines.append("")
            report_lines.append(_get_text(lang, "admin_orders_status_breakdown"))
            for status, count in sorted(status_counts.items(), key=lambda x: x[1], reverse=True):
                report_lines.append(f"? {status}: {count}")

            report_lines.append("")
            report_lines.append(_get_text(lang, "admin_orders_payment_methods"))
            for method, count in payment_methods:
                report_lines.append(f"? {method}: {count}")

            report_lines.append("")
            report_lines.append(_get_text(lang, "admin_orders_payment_statuses"))
            for status, count in payment_statuses:
                report_lines.append(f"? {status}: {count}")

            report_lines.append("")
            report_lines.append(_get_text(lang, "admin_orders_types"))
            for order_type, count in order_types:
                report_lines.append(f"? {order_type}: {count}")

            report_lines.append("")
            report_lines.append(_get_text(lang, "admin_orders_top_stores"))
            for idx, row in enumerate(top_stores, 1):
                store_name = html_escape(row[0]) if row and row[0] else "-"
                orders_count = int(row[1]) if row and row[1] is not None else 0
                revenue = int(row[2]) if row and row[2] is not None else 0
                report_lines.append(f"{idx}. {store_name} ? {orders_count} / {revenue:,} ???")

            report_lines.append("")
            report_lines.append(_get_text(lang, "admin_orders_recent"))
            for row in recent_orders:
                order_id, _, status, _, pay_method, total_price, store_name, customer_name = row
                store_name = html_escape(store_name) if store_name else "-"
                customer_name = html_escape(customer_name) if customer_name else "-"
                total_val = int(total_price) if total_price is not None else 0
                report_lines.append(f"? #{order_id} | {status or '-'} | {total_val:,} ???")
                report_lines.append(
                    f"  {store_name} | {customer_name} | {pay_method or '-'}"
                )

        report = "\n".join(report_lines)
        await message.answer(report, parse_mode="HTML")



        # ??????? ? CSV (????? ?????????)
        csv_filename = f"analytics_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

        with open(csv_filename, "w", newline="", encoding="utf-8-sig") as csvfile:
            writer = csv.writer(csvfile)

            # ????????? ? ??????
            writer.writerow(["??????", "??????????", "????????"])
            writer.writerow(["????????????", "?????", total_users])
            writer.writerow(["????????????", "????????", total_sellers])
            writer.writerow(["????????????", "??????????", total_customers])
            writer.writerow(["????????????", "??????? ????", ru_users])
            writer.writerow(["????????????", "????????? ????", uz_users])
            writer.writerow(["????????", "????????", active_stores])
            writer.writerow(["????????", "?? ?????????", pending_stores])
            writer.writerow(["????????", "???????????", rejected_stores])
            writer.writerow([])
            writer.writerow(["??????", "????????", active_offers])
            writer.writerow(["??????", "????????", expired_offers])
            writer.writerow(["??????", "????????????", sold_out_offers])
            writer.writerow([])
            writer.writerow(["??????? ??????", "", f"{avg_discount}%"])
            writer.writerow([])
            writer.writerow(["???-5 ?????????", "", ""])
            for i, (name, count) in enumerate(top_sellers, 1):
                writer.writerow([i, name, count])

        # ?????????? CSV ????
        csv_file = FSInputFile(csv_filename)
        await message.answer_document(csv_file, caption="?? ?????? ????????? ? CSV ???????")

        # ??????? ????????? ????
        if os.path.exists(csv_filename):
            os.remove(csv_filename)

        # ??????? ??????? ? CSV
        orders_csv_filename = f"orders_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

        with open(orders_csv_filename, "w", newline="", encoding="utf-8-sig") as csvfile:
            writer = csv.writer(csvfile)
            headers = [
                _get_text(lang, "admin_orders_csv_order_id"),
                _get_text(lang, "admin_orders_csv_created_at"),
                _get_text(lang, "admin_orders_csv_status"),
                _get_text(lang, "admin_orders_csv_payment_status"),
                _get_text(lang, "admin_orders_csv_payment_method"),
                _get_text(lang, "admin_orders_csv_order_type"),
                _get_text(lang, "admin_orders_csv_total_price"),
                _get_text(lang, "admin_orders_csv_store"),
                _get_text(lang, "admin_orders_csv_customer"),
                _get_text(lang, "admin_orders_csv_phone"),
            ]
            writer.writerow(headers)

            for row in order_rows:
                (
                    order_id,
                    created_at,
                    status,
                    payment_status,
                    payment_method,
                    order_type,
                    total_price,
                    store_name,
                    customer_name,
                    phone,
                ) = row
                writer.writerow(
                    [
                        order_id,
                        created_at,
                        status,
                        payment_status,
                        payment_method,
                        order_type,
                        int(total_price) if total_price is not None else 0,
                        store_name,
                        customer_name,
                        phone,
                    ]
                )

        await message.answer_document(
            FSInputFile(orders_csv_filename),
            caption=_get_text(lang, "admin_orders_csv_caption"),
        )

        if os.path.exists(orders_csv_filename):
            os.remove(orders_csv_filename)

    except Exception as e:
        await message.answer(f"? ?????? ??? ???????????? ?????????: {e}")

# ============== МОДЕРАЦИЯ МАГАЗИНОВ ==============


@router.message(F.text == "🏪 Заявки на партнерство")
async def admin_pending_stores(message: types.Message):
    """Показать заявки на модерацию магазинов"""
    if message.from_user.id != _ADMIN_ID:
        await message.answer("❌ Доступ запрещён")
        return

    try:
        stores = _db.get_stores_by_status("pending")

        if not stores:
            await message.answer("✅ Новых заявок нет")
            return

        for store in stores:
            store_text = f"""
🏪 <b>{store['name']}</b>

📍 Город: {store['city']}
🏢 Адрес: {store['address']}
📋 Описание: {store['description']}
📂 Категория: {store['category']}
📞 Телефон: {store['phone']}
👤 Владелец ID: {store['owner_id']}
🏢 Тип: {store['business_type']}
"""

            await message.answer(
                store_text, reply_markup=_moderation_keyboard(store["store_id"]), parse_mode="HTML"
            )

    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")


@router.callback_query(F.data.startswith("approve_"))
async def approve_store(callback: types.CallbackQuery):
    """Одобрить магазин"""
    if callback.from_user.id != _ADMIN_ID:
        await callback.answer("❌ Доступ запрещён", show_alert=True)
        return

    try:
        # callback.data format: "approve_store_6" -> split by "_" -> take last element
        store_id = int(callback.data.split("_")[-1])
    except (ValueError, IndexError) as e:
        logger.error(f"Invalid store_id in callback data: {callback.data}, error: {e}")
        await callback.answer("❌ Неверный запрос", show_alert=True)
        return

    try:
        # Обновляем статус магазина
        _db.update_store_status(store_id, "active")

        # Получаем данные о магазине
        store = _db.get_store(store_id)

        # Обновляем роль владельца на seller
        _db.update_user_role(store["owner_id"], "seller")

        # Устанавливаем режим просмотра продавца
        try:
            _db.set_user_view_mode(store["owner_id"], "seller")
        except Exception:
            pass

        # Отправляем уведомление владельцу с меню продавца
        lang = _db.get_user_language(store["owner_id"])
        notification = _get_text(lang, "store_approved")

        try:
            from app.keyboards.seller import main_menu_seller

            await _bot.send_message(
                store["owner_id"],
                notification,
                parse_mode="HTML",
                reply_markup=main_menu_seller(lang),
            )
        except Exception:
            # Fallback without keyboard
            try:
                await _bot.send_message(store["owner_id"], notification, parse_mode="HTML")
            except Exception:
                pass

        await callback.message.edit_text(
            f"✅ Магазин '{store['name']}' одобрен!\n\n{callback.message.text}"
        )
        await callback.answer("✅ Магазин одобрен")

    except Exception as e:
        await callback.answer(f"❌ Ошибка: {e}", show_alert=True)


@router.callback_query(F.data.startswith("reject_"))
async def reject_store(callback: types.CallbackQuery):
    """Отклонить заявку на магазин"""
    if callback.from_user.id != _ADMIN_ID:
        await callback.answer("❌ Доступ запрещён", show_alert=True)
        return

    try:
        # callback.data format: "reject_store_6" -> split by "_" -> take last element
        store_id = int(callback.data.split("_")[-1])
    except (ValueError, IndexError) as e:
        logger.error(f"Invalid store_id in callback data: {callback.data}, error: {e}")
        await callback.answer("❌ Неверный запрос", show_alert=True)
        return

    try:
        # Обновляем статус
        _db.update_store_status(store_id, "rejected")

        # Получаем данные о магазине
        store = _db.get_store(store_id)

        # Уведомляем владельца
        lang = _db.get_user_language(store["owner_id"])
        notification = _get_text(lang, "store_rejected")

        try:
            await _bot.send_message(store["owner_id"], notification)
        except Exception:
            pass

        await callback.message.edit_text(
            f"❌ Магазин '{store['name']}' отклонён\n\n{callback.message.text}"
        )
        await callback.answer("✅ Заявка отклонена")

    except Exception as e:
        await callback.answer(f"❌ Ошибка: {e}", show_alert=True)


# ============== ПРОСМОТР МАГАЗИНОВ И ТОВАРОВ ==============


@router.message(F.text == "📋 Все предложения")
async def admin_all_offers(message: types.Message):
    """Показать все активные предложения"""
    if message.from_user.id != _ADMIN_ID:
        await message.answer("❌ Доступ запрещён")
        return

    try:
        offers = _db.get_all_offers()

        if not offers:
            await message.answer("📋 Нет активных предложений")
            return

        # Показываем первые 10
        for offer in offers[:10]:
            offer_text = f"""
🔥 <b>{offer.get('title', 'Без названия')}</b>

📦 ID: {offer.get('offer_id')}
🏪 Магазин ID: {offer.get('store_id')}
💵 Цена: <s>{offer.get('original_price', 0):,}</s> → <b>{offer.get('discount_price', 0):,} сум</b>
📦 Остаток: {offer.get('quantity', 0)} {offer.get('unit', 'шт')}
📅 Истекает: {offer.get('expiry_date', 'неизвестно')}
📊 Статус: {offer.get('status', 'unknown')}
"""
            await message.answer(offer_text, parse_mode="HTML")

        if len(offers) > 10:
            await message.answer(f"... и ещё {len(offers) - 10} предложений")

    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")


@router.message(F.text == "🏪 Все магазины")
async def admin_all_stores(message: types.Message):
    """Показать все магазины с возможностью удаления"""
    if message.from_user.id != _ADMIN_ID:
        await message.answer("❌ Доступ запрещён")
        return

    try:
        stores = _db.get_all_stores()

        if not stores:
            await message.answer("🏪 Магазинов нет")
            return

        for store in stores:
            builder = InlineKeyboardBuilder()
            builder.button(
                text=f"🗑 Удалить {store['name'][:20]}",
                callback_data=f"delete_store_{store['store_id']}",
            )

            store_text = f"""
🏪 <b>{store['name']}</b>

📍 {store['city']}
📊 Статус: {store['status']}
👤 Владелец ID: {store['owner_id']}
📞 {store['phone']}
"""
            await message.answer(store_text, reply_markup=builder.as_markup(), parse_mode="HTML")

    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")


@router.callback_query(F.data.startswith("delete_store_"))
async def delete_store_callback(callback: types.CallbackQuery):
    """Удалить магазин"""
    if callback.from_user.id != _ADMIN_ID:
        await callback.answer("❌ Доступ запрещён", show_alert=True)
        return

    try:
        store_id = int(callback.data.split("_")[2])
    except (ValueError, IndexError) as e:
        logger.error(f"Invalid store_id in callback data: {callback.data}, error: {e}")
        await callback.answer("❌ Неверный запрос", show_alert=True)
        return

    try:
        store = _db.get_store(store_id)

        # Удаляем магазин
        _db.delete_store(store_id)

        await callback.message.edit_text(f"🗑 Магазин '{store['name']}' удалён")
        await callback.answer("✅ Магазин удалён")

    except Exception as e:
        await callback.answer(f"❌ Ошибка: {e}", show_alert=True)


# ============== ПЛЕЙСХОЛДЕРЫ ==============


@router.message(F.text == "📢 Рассылка")
async def admin_broadcast(message: types.Message):
    """Рассылка (в разработке)"""
    if message.from_user.id != _ADMIN_ID:
        await message.answer("❌ Доступ запрещён")
        return

    await message.answer("📢 Функция рассылки в разработке")


@router.message(F.text == "⚙️ Настройки")
async def admin_settings(message: types.Message):
    """Настройки админ-панели"""
    if message.from_user.id != _ADMIN_ID:
        await message.answer("❌ Доступ запрещён")
        return

    from aiogram.utils.keyboard import InlineKeyboardBuilder

    kb = InlineKeyboardBuilder()
    kb.button(text="💳 Платёжные реквизиты", callback_data="admin_payment_settings")
    kb.button(text="🔔 Уведомления", callback_data="admin_notifications_settings")
    kb.button(text="📊 Лимиты", callback_data="admin_limits_settings")
    kb.adjust(1)

    text = "⚙️ <b>Настройки платформы</b>\n\n"
    text += "Выберите раздел для настройки:"

    await message.answer(text, parse_mode="HTML", reply_markup=kb.as_markup())
