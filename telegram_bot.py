"""Отправка уведомлений в Telegram + запись в БД."""
import os
import requests
from dotenv import load_dotenv

from database import log_notification

load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
API = f"https://api.telegram.org/bot{TOKEN}"

TIMEOUT = 15


def _has_creds():
    return bool(TOKEN) and bool(CHAT_ID)


def test_connection():
    if not _has_creds():
        return False, "Не задан TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID в .env"
    try:
        r = requests.get(f"{API}/getMe", timeout=TIMEOUT)
        data = r.json()
        if r.ok and data.get("ok"):
            name = data["result"].get("username", "bot")
            return True, f"Бот @{name} подключён"
        return False, f"Telegram ответил: {data}"
    except Exception as e:
        return False, f"Сетевая ошибка: {e}"


def send_message(text: str, subject: str | None = None,
                 parse_mode: str = "HTML"):
    """Отправляет текст в Telegram и пишет результат в БД."""
    if not _has_creds():
        err = "Не задан токен/chat_id"
        log_notification("telegram", text, status="error",
                         recipient=CHAT_ID or None,
                         subject=subject, error=err)
        return False, err

    try:
        r = requests.post(
            f"{API}/sendMessage",
            data={
                "chat_id": CHAT_ID,
                "text": text,
                "parse_mode": parse_mode,
                "disable_web_page_preview": True,
            },
            timeout=TIMEOUT,
        )
        data = r.json()
        if r.ok and data.get("ok"):
            log_notification("telegram", text, status="ok",
                             recipient=CHAT_ID, subject=subject)
            return True, "OK"
        err = data.get("description", f"HTTP {r.status_code}")
        log_notification("telegram", text, status="error",
                         recipient=CHAT_ID, subject=subject, error=err)
        return False, err
    except Exception as e:
        log_notification("telegram", text, status="error",
                         recipient=CHAT_ID, subject=subject, error=str(e))
        return False, str(e)


def send_document(file_bytes: bytes, filename: str,
                  caption: str = "", subject: str | None = None):
    """Отправляет файл (PDF) в Telegram и пишет результат в БД."""
    msg_for_log = caption or f"[file] {filename}"

    if not _has_creds():
        err = "Не задан токен/chat_id"
        log_notification("telegram", msg_for_log, status="error",
                         recipient=CHAT_ID or None,
                         subject=subject, error=err)
        return False, err

    try:
        r = requests.post(
            f"{API}/sendDocument",
            data={"chat_id": CHAT_ID, "caption": caption},
            files={"document": (filename, file_bytes, "application/pdf")},
            timeout=TIMEOUT,
        )
        data = r.json()
        if r.ok and data.get("ok"):
            log_notification("telegram", msg_for_log, status="ok",
                             recipient=CHAT_ID, subject=subject)
            return True, "OK"
        err = data.get("description", f"HTTP {r.status_code}")
        log_notification("telegram", msg_for_log, status="error",
                         recipient=CHAT_ID, subject=subject, error=err)
        return False, err
    except Exception as e:
        log_notification("telegram", msg_for_log, status="error",
                         recipient=CHAT_ID, subject=subject, error=str(e))
        return False, str(e)


def notify_urgent_containers(forecast_df, subject: str = "urgent_list"):
    """Формирует сводку по срочным контейнерам и отправляет диспетчеру."""
    urgent = forecast_df[forecast_df["priority"] == "Срочно"]

    if urgent.empty:
        text = "✅ Срочных контейнеров нет."
    else:
        lines = ["<b>🔴 Срочные контейнеры:</b>", ""]
        for _, row in urgent.iterrows():
            lines.append(
                f"• <b>{row['name']}</b> — {row['address']}\n"
                f"  Заполнение: {row['current_fill']}% · "
                f"до переполнения: {row['hours_to_full']} ч"
            )
        lines.append("")
        lines.append(f"Всего: {len(urgent)} шт.")
        text = "\n".join(lines)

    return send_message(text, subject=subject)
