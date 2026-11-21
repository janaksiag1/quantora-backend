"""Automated Telegram Channel Broadcaster for Gainbud (@Gainbud).

Schedules:
- Weekdays (Mon-Fri): Pre-market opening pulse, mid-day IPO GMP radar, power hour momentum, post-market FII/DII wrap.
- Weekends (Sat-Sun): Educational posts, feature highlights (AI Council, Portfolio Doctor), and upcoming IPO calendar.
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List
import httpx
from .config import settings
from .telegram_bot import send_telegram_message

logger = logging.getLogger('gainbud.telegram.broadcaster')

IST = timezone(timedelta(hours=5, minutes=30))

_last_broadcasts: Dict[str, str] = {}
_posted_news_keys: set = set()

def get_channel_target() -> str:
    """Return configured chat ID or default to @Gainbud."""
    return settings.telegram_chat_id or "@Gainbud"

async def broadcast_pre_market() -> Dict[str, Any]:
    """09:00 AM IST Morning Market Preview."""
    target = get_channel_target()
    date_str = datetime.now(IST).strftime("%d %b %Y")
    
    text = (
        f"☀️ <b>GAINBUD MORNING MARKET PULSE · {date_str}</b>\n\n"
        f"📊 <b>Indian Equities Setup:</b>\n"
        f"• Benchmark Nifty 50 and Sensex gear up for today's opening session.\n"
        f"• Domestic Institutions (DIIs) continue steady liquidity support.\n"
        f"• Global cues: US markets and Asian indices trading with mixed sentiment.\n\n"
        f"🎯 <b>Primary Focus for Today:</b>\n"
        f"• Watch active IPO subscription counters and grey market trends.\n"
        f"• Track sector rotation across Banking, IT, and Capital Goods.\n\n"
        f"🎙️ <i>Daily 60-Second Audio Briefing in Hindi & English is live on Gainbud Terminal.</i>"
    )

    buttons = [
        {"text": "⚡ Open Gainbud Terminal", "url": "https://gainbud.in/app"},
        {"text": "🎙️ Listen to Morning Briefing", "url": "https://gainbud.in/app"}
    ]

    res = await send_telegram_message(text=text, chat_id=target, buttons=buttons)
    _last_broadcasts["pre_market"] = datetime.now(IST).isoformat()
    return res

async def broadcast_ipo_gmp() -> Dict[str, Any]:
    """11:30 AM IST Mid-Day Live IPO GMP Radar."""
    target = get_channel_target()
    date_str = datetime.now(IST).strftime("%d %b")

    try:
        from .market_sources import gmp_feed
        ipos = await gmp_feed()
    except Exception:
        ipos = []

    lines = []
    if ipos:
        for item in ipos[:5]:
            name = item.get("name", "")[:28]
            gmp = item.get("gmp", "N/A")
            price = item.get("price", "TBD")
            lines.append(f"• <b>{name}</b>: GMP ₹{gmp} (Price: {price})")

    ipo_text = "\n".join(lines) if lines else "• Check active Mainboard & SME issues on Gainbud live terminal."

    text = (
        f"🚀 <b>GAINBUD LIVE IPO GMP RADAR · {date_str}</b>\n\n"
        f"🔥 <b>Current Grey Market Premiums:</b>\n"
        f"{ipo_text}\n\n"
        f"💡 <i>Unofficial GMP is for sentiment tracking, not a guaranteed listing forecast.</i>\n"
        f"🔍 <i>View 10-Agent AI council valuation & Piotroski F-score on Gainbud.</i>"
    )

    buttons = [
        {"text": "📈 Live IPO GMP Tracker", "url": "https://gainbud.in/app?module=ipo"},
        {"text": "🔍 Check Allotment Status", "url": "https://gainbud.in/app?module=ipo"}
    ]

    res = await send_telegram_message(text=text, chat_id=target, buttons=buttons)
    _last_broadcasts["ipo_gmp"] = datetime.now(IST).isoformat()
    return res

async def broadcast_fii_dii() -> Dict[str, Any]:
    """05:30 PM IST Post-Market Wrap & Institutional Flow."""
    target = get_channel_target()
    date_str = datetime.now(IST).strftime("%d %b %Y")

    text = (
        f"🏛️ <b>GAINBUD POST-MARKET & FII/DII FLOW · {date_str}</b>\n\n"
        f"📈 <b>Market Closing Summary:</b>\n"
        f"• Indian markets completed today's trading session.\n"
        f"• <b>DII Flow:</b> Strong domestic institutional mutual fund buying continues.\n"
        f"• <b>FII Activity:</b> Selective institutional allocation across bluechip index leaders.\n\n"
        f"🩺 <b>Evening Portfolio Check:</b>\n"
        f"Upload your Zerodha or Groww statement to Gainbud's <b>AI Portfolio Doctor</b> to check sector concentration and risk score before tomorrow's open."
    )

    buttons = [
        {"text": "🩺 Run Portfolio X-Ray", "url": "https://gainbud.in/app?module=watchlist"},
        {"text": "📊 Full Market Terminal", "url": "https://gainbud.in/app"}
    ]

    res = await send_telegram_message(text=text, chat_id=target, buttons=buttons)
    _last_broadcasts["fii_dii"] = datetime.now(IST).isoformat()
    return res

async def broadcast_weekend_feature() -> Dict[str, Any]:
    """Saturday/Sunday Education & Marketing Post."""
    target = get_channel_target()
    now_ist = datetime.now(IST)
    is_sunday = now_ist.weekday() == 6

    if is_sunday:
        text = (
            f"📅 <b>GAINBUD WEEK AHEAD & UPCOMING IPO CALENDAR</b>\n\n"
            f"Prepare your market playbook for the upcoming trading week:\n\n"
            f"1️⃣ <b>Upcoming IPO Issues:</b> Check opening dates, lot sizes, and live GMP.\n"
            f"2️⃣ <b>Direct Allotment Checker:</b> Instant 1-click PAN check for Link Intime, KFintech & Bigshare.\n"
            f"3️⃣ <b>PWA Mobile App:</b> Install Gainbud on your home screen for zero-delay alerts without App Store downloads.\n\n"
            f"🚀 <i>Trade with data, research before you invest.</i>"
        )
    else:
        text = (
            f"💡 <b>GAINBUD PRO TRADER MASTERCLASS</b>\n\n"
            f"<b>How to avoid 'Trap IPOs' using Piotroski F-Score?</b>\n\n"
            f"• Never apply solely based on unofficial grey market premium (GMP).\n"
            f"• Check Operating Cash Flows vs Reported Net Profit.\n"
            f"• Watch promoter share pledging and debt-to-equity ratio.\n\n"
            f"🤖 On Gainbud, our <b>10-Agent AI Council</b> (Benjamin Graham, Charlie Munger, Aswath Damodaran, Peter Lynch) cross-examines every offer document with forensic financial checks."
        )

    buttons = [
        {"text": "⚡ Open Gainbud Terminal", "url": "https://gainbud.in/app"},
        {"text": "📲 Install Gainbud App", "url": "https://gainbud.in/app"}
    ]

    res = await send_telegram_message(text=text, chat_id=target, buttons=buttons)
    _last_broadcasts["weekend"] = now_ist.isoformat()
    return res

async def telegram_auto_broadcaster_worker():
    """Background worker that continuously monitors IST schedule and broadcasts timely updates."""
    logger.info("Telegram Auto Broadcaster worker started.")
    await asyncio.sleep(45)  # Initial warmup delay

    while True:
        try:
            now_ist = datetime.now(IST)
            weekday = now_ist.weekday()  # 0: Mon, ..., 4: Fri, 5: Sat, 6: Sun
            hour = now_ist.hour
            minute = now_ist.minute
            today_key = now_ist.strftime("%Y-%m-%d")

            # --- WEEKEND SCHEDULE (Saturday & Sunday) ---
            if weekday in (5, 6):
                # Send once between 11:00 AM and 12:30 PM IST
                if 11 <= hour <= 12 and _last_broadcasts.get("weekend_date") != today_key:
                    logger.info("Broadcasting weekend educational/marketing post.")
                    await broadcast_weekend_feature()
                    _last_broadcasts["weekend_date"] = today_key

            # --- WEEKDAY SCHEDULE (Monday to Friday) ---
            else:
                # 1. Pre-Market (09:00 - 09:20 AM IST)
                if hour == 9 and 0 <= minute <= 20 and _last_broadcasts.get("pre_market_date") != today_key:
                    logger.info("Broadcasting pre-market pulse.")
                    await broadcast_pre_market()
                    _last_broadcasts["pre_market_date"] = today_key

                # 2. Mid-Day IPO GMP (11:30 - 12:15 PM IST)
                elif hour == 11 and 30 <= minute <= 59 and _last_broadcasts.get("ipo_gmp_date") != today_key:
                    logger.info("Broadcasting mid-day IPO GMP radar.")
                    await broadcast_ipo_gmp()
                    _last_broadcasts["ipo_gmp_date"] = today_key

                # 3. Post-Market FII/DII Wrap (05:45 - 06:45 PM IST)
                elif (hour == 17 and minute >= 45) or (hour == 18 and minute <= 45):
                    if _last_broadcasts.get("fii_dii_date") != today_key:
                        logger.info("Broadcasting post-market FII/DII wrap.")
                        await broadcast_fii_dii()
                        _last_broadcasts["fii_dii_date"] = today_key

        except Exception as e:
            logger.error(f"Telegram auto broadcaster error: {e}")

        # Sleep for 10 minutes between schedule checks
        await asyncio.sleep(600)
