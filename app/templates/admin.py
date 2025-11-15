"""Text rendering helpers for admin dashboards."""
from __future__ import annotations

from app.services.admin_service import BookingStats, OfferStats, StoreStats, UserStats


def render_user_stats(stats: UserStats) -> str:
	text = "👥 <b>Пользователи</b>\n\n"
	text += f"📊 Всего: {stats.total}\n"
	text += f"├ 🏪 Партнёры: {stats.sellers}\n"
	text += f"└ 🛍 Покупатели: {stats.customers}\n\n"
	text += f"📅 За неделю: +{stats.week_users}\n"
	text += f"📅 Сегодня: +{stats.today_users}"
	return text


def render_store_stats(stats: StoreStats) -> str:
	text = "🏪 <b>Магазины</b>\n\n"
	text += f"✅ Активные: {stats.active}\n"
	text += f"⏳ На модерации: {stats.pending}\n"
	text += f"❌ Отклонённые: {stats.rejected}"
	return text


def render_offer_stats(stats: OfferStats) -> str:
	text = "📦 <b>Товары</b>\n\n"
	text += f"✅ Активные: {stats.active}\n"
	text += f"❌ Неактивные: {stats.inactive}\n"
	text += f"🗑 Удалённые: {stats.deleted}\n\n"
	if stats.top_categories:
		text += "<b>Топ категорий:</b>\n"
		for category, count in stats.top_categories:
			text += f"├ {category}: {count}\n"
	return text.strip()


def render_booking_stats(stats: BookingStats) -> str:
	text = "🎫 <b>Бронирования</b>\n\n"
	text += f"📊 Всего: {stats.total}\n"
	text += f"├ ⏳ Активные: {stats.pending}\n"
	text += f"├ ✅ Завершённые: {stats.completed}\n"
	text += f"└ ❌ Отменённые: {stats.cancelled}\n\n"
	text += f"📅 Сегодня: {stats.today_bookings}\n"
	text += f"💰 Выручка: {int(stats.today_revenue):,} сум"
	return text
