import httpx
import logging
from typing import Optional, Dict, Any, List
from .config import settings

logger = logging.getLogger('gainbud.telegram')

async def send_telegram_message(
    text: str,
    chat_id: Optional[str] = None,
    parse_mode: str = "HTML",
    buttons: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    """Send an alert message via Telegram Bot API (100% free forever)."""
    token = settings.telegram_bot_token.get_secret_value()
    target = chat_id or settings.telegram_chat_id

    if not token:
        logger.warning("Telegram Bot Token is not set in environment.")
        return {"ok": False, "error": "TELEGRAM_BOT_TOKEN not configured"}

    if not target:
        logger.warning("Telegram Chat ID is not specified.")
        return {"ok": False, "error": "Chat ID not specified"}

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload: Dict[str, Any] = {
        "chat_id": target,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": False,
    }

    if buttons:
        # Format inline keyboard
        keyboard = [[{"text": b["text"], "url": b["url"]} for b in buttons]]
        payload["reply_markup"] = {"inline_keyboard": keyboard}

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            res = await client.post(url, json=payload)
            data = res.json()
            if not res.is_success:
                logger.error(f"Telegram API error: {data}")
                return {"ok": False, "status": res.status_code, "data": data}
            return {"ok": True, "data": data}
    except Exception as e:
        logger.error("Telegram transport failed (%s)", type(e).__name__)
        return {"ok": False, "error": "Telegram transport unavailable"}

async def send_telegram_photo(
    photo_url: str,
    caption: str,
    chat_id: Optional[str] = None,
    parse_mode: str = "HTML",
    buttons: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    """Send a photo with rich caption via Telegram Bot API."""
    token = settings.telegram_bot_token.get_secret_value()
    target = chat_id or settings.telegram_chat_id

    if not token:
        logger.warning("Telegram Bot Token is not set in environment.")
        return {"ok": False, "error": "TELEGRAM_BOT_TOKEN not configured"}

    if not target:
        logger.warning("Telegram Chat ID is not specified.")
        return {"ok": False, "error": "Chat ID not specified"}

    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    payload: Dict[str, Any] = {
        "chat_id": target,
        "photo": photo_url,
        "caption": caption[:1024],
        "parse_mode": parse_mode,
    }

    if buttons:
        keyboard = [[{"text": b["text"], "url": b["url"]} for b in buttons]]
        payload["reply_markup"] = {"inline_keyboard": keyboard}

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            res = await client.post(url, json=payload)
            data = res.json()
            if not res.is_success:
                logger.error(f"Telegram photo API error: {data}")
                return {"ok": False, "status": res.status_code, "data": data}
            return {"ok": True, "data": data}
    except Exception as e:
        logger.error("Telegram photo transport failed (%s)", type(e).__name__)
        return {"ok": False, "error": "Telegram transport unavailable"}

async def format_and_send_ipo_alert(issue: Dict[str, Any], chat_id: Optional[str] = None) -> Dict[str, Any]:
    """Format rich IPO alert card and broadcast to Telegram."""
    name = issue.get("name", "Unknown IPO")
    gmp = issue.get("gmp", "N/A")
    price_band = issue.get("priceBand", issue.get("price", "TBD"))
    open_date = issue.get("openDate", issue.get("dates", "Upcoming"))
    close_date = issue.get("closeDate", "")
    expected_gain = issue.get("expectedGain", "")

    gain_badge = f"\n🔥 <b>Expected Listing Gain:</b> <code>+{expected_gain}%</code>" if expected_gain else ""

    text = (
        f"🚀 <b>GAINBUD LIVE IPO ALERT</b>\n\n"
        f"🏢 <b>Company:</b> <b>{name}</b>\n"
        f"💰 <b>Price Band:</b> {price_band}\n"
        f"📈 <b>Grey Market Premium (GMP):</b> ₹{gmp}{gain_badge}\n"
        f"📅 <b>Subscription Dates:</b> {open_date} {f'to {close_date}' if close_date else ''}\n\n"
        f"🔍 <i>Institutional multi-agent council consensus is ready on Gainbud.</i>"
    )

    buttons = [
        {"text": "📊 View Full Research Report", "url": f"https://gainbud.in/app?module=ipo&issue={name.replace(' ', '+')}"},
        {"text": "⚡ Open Gainbud Terminal", "url": "https://gainbud.in/app"}
    ]

    return await send_telegram_message(text=text, chat_id=chat_id, buttons=buttons)
