"""
FastAPI 服务器 — Etsy Webhook 接收 + 自动化报告生成 + PDF 交付
"""
import os
import json
import hmac
import hashlib
import logging
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel, Field

from bazi_engine import calculate_bazi
from report_generator import create_report
from pdf_renderer import save_report

# ── Config ──
ETSY_WEBHOOK_SECRET = os.environ.get("ETSY_WEBHOOK_SECRET", "")
SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "reports@yourdomain.com")
SENDER_PASSWORD = os.environ.get("SENDER_PASSWORD", "")
SMTP_SERVER = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
REPORT_BASE_URL = os.environ.get("REPORT_BASE_URL", "http://localhost:8000")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Auto Fortune Report API", version="1.0.0")


# ── Models ──

class EtsyWebhookPayload(BaseModel):
    """Etsy v3 Order Paid Webhook payload"""
    event: str
    receipt_id: int
    seller_user_id: int
    buyer_user_id: int
    was_paid: bool = True


class OrderData(BaseModel):
    """Parsed order data from Etsy webhook + custom fields"""
    order_id: str
    client_name: str
    birth_year: int
    birth_month: int
    birth_day: int
    birth_hour: int = 12
    birth_minute: int = 0
    gender: str = "male"
    buyer_email: str = ""
    focus: str = "comprehensive"


# ── Etsy Webhook Verification ──

def verify_etsy_webhook(payload: bytes, signature: str) -> bool:
    """Verify Etsy webhook HMAC-SHA256 signature"""
    if not ETSY_WEBHOOK_SECRET:
        logger.warning("ETSY_WEBHOOK_SECRET not set — skipping signature verification")
        return True
    expected = hmac.new(
        ETSY_WEBHOOK_SECRET.encode(),
        payload,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


# ── Email Delivery ──

def send_report_email(to_email: str, download_url: str, order_id: str, client_name: str):
    """Send PDF download link to buyer via email"""
    if not SENDER_PASSWORD:
        logger.info(f"[EMAIL MOCK] To: {to_email}, URL: {download_url}")
        return

    import smtplib
    from email.mime.text import MIMEText

    subject = f"Your Personal BaZi Reading Report — Order #{order_id}"
    body = f"""Hello {client_name},

Thank you for your order! Your personalized BaZi Reading report is ready.

Download your report here:
{download_url}

This link is valid for 7 days.

Note: This report is for entertainment and self-reflection purposes only.

With gratitude,
The BaZi Reading Team
"""

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = SENDER_EMAIL
    msg["To"] = to_email

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.send_message(msg)
        logger.info(f"Email sent to {to_email} for order {order_id}")
    except Exception as e:
        logger.error(f"Failed to send email: {e}")


# ── Parse Personalization ──

def parse_personalization(text: str) -> Optional[dict]:
    """Parse Etsy personalization field into birth data.

    Expected format:
    Name: John Doe
    Birth: 1990-05-15
    Time: 10:30
    Gender: Male
    Focus: Career
    """
    data = {}
    for line in text.strip().split("\n"):
        line = line.strip()
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip().lower()
        value = value.strip()
        if key == "name":
            data["name"] = value
        elif key == "birth":
            parts = value.split("-")
            if len(parts) == 3:
                data["birth_year"] = int(parts[0])
                data["birth_month"] = int(parts[1])
                data["birth_day"] = int(parts[2])
        elif key == "time":
            parts = value.split(":")
            data["birth_hour"] = int(parts[0]) if parts else 12
            data["birth_minute"] = int(parts[1]) if len(parts) > 1 else 0
        elif key == "gender":
            data["gender"] = "male" if value.lower() in ("male", "m") else "female"
        elif key == "focus":
            data["focus"] = value.lower()
    return data if all(k in data for k in ("name", "birth_year", "birth_month", "birth_day")) else None


# ── API Routes ──

@app.get("/health")
def health():
    return {"status": "ok", "timestamp": datetime.now().isoformat()}


@app.post("/webhook/etsy")
async def etsy_webhook(request: Request):
    """Receive Etsy order.paid webhook and trigger report generation"""
    raw_body = await request.body()
    signature = request.headers.get("x-etsy-signature", "")

    if not verify_etsy_webhook(raw_body, signature):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    payload = json.loads(raw_body)
    receipt_id = payload.get("receipt_id")
    logger.info(f"Received Etsy webhook for receipt #{receipt_id}")

    # Return 200 immediately — Etsy expects fast acknowledgment
    # Processing continues in background
    from concurrent.futures import ThreadPoolExecutor
    executor = ThreadPoolExecutor()
    executor.submit(process_etsy_order, receipt_id)

    return {"status": "accepted", "receipt_id": receipt_id}


async def fetch_etsy_receipt(receipt_id: int) -> Optional[OrderData]:
    """Fetch receipt details from Etsy API v3"""
    api_key = os.environ.get("ETSY_API_KEY", "")
    api_token = os.environ.get("ETSY_API_TOKEN", "")

    if not api_key or not api_token:
        logger.warning("Etsy API credentials not configured — using mock data")
        return None

    import httpx
    url = f"https://openapi.etsy.com/v3/application/receipts/{receipt_id}"
    headers = {
        "x-api-key": api_key,
        "Authorization": f"Bearer {api_token}",
    }
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=headers, timeout=15)
            resp.raise_for_status()
            data = resp.json()

        buyer_email = data.get("buyer_email", "")
        buyer_name = data.get("name", "")
        personalization = data.get("personalization", "")

        parsed = parse_personalization(personalization)
        if parsed:
            return OrderData(
                order_id=str(receipt_id),
                client_name=parsed.get("name", buyer_name),
                birth_year=parsed["birth_year"],
                birth_month=parsed["birth_month"],
                birth_day=parsed["birth_day"],
                birth_hour=parsed.get("birth_hour", 12),
                birth_minute=parsed.get("birth_minute", 0),
                gender=parsed.get("gender", "male"),
                buyer_email=buyer_email,
                focus=parsed.get("focus", "comprehensive"),
            )
        return None
    except Exception as e:
        logger.error(f"Failed to fetch receipt {receipt_id}: {e}")
        return None


@app.post("/process")
async def process_order(order: OrderData):
    """API endpoint to manually trigger report generation (for testing)"""
    result = generate_report_pdf(order)
    return {
        "status": "completed",
        "order_id": order.order_id,
        "pdf_path": result,
    }


def process_etsy_order(receipt_id: int):
    """Background processing of an Etsy order"""
    import asyncio

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        order_data = loop.run_until_complete(fetch_etsy_receipt(receipt_id))
        loop.close()
    except Exception as e:
        logger.error(f"Failed to fetch order {receipt_id}: {e}")
        order_data = None

    if not order_data:
        logger.error(f"Cannot process order {receipt_id}: no order data")
        return

    pdf_path = generate_report_pdf(order_data)
    if pdf_path:
        download_url = f"{REPORT_BASE_URL}/download/{order_data.order_id}"
        # Notify buyer — keep retrying email
        for attempt in range(3):
            try:
                send_report_email(
                    to_email=order_data.buyer_email,
                    download_url=download_url,
                    order_id=order_data.order_id,
                    client_name=order_data.client_name,
                )
                break
            except Exception as e:
                logger.warning(f"Email attempt {attempt+1} failed: {e}")


def generate_report_pdf(order: OrderData) -> str:
    """Full pipeline: calculate BaZi → generate report → render PDF"""
    logger.info(f"Generating report for {order.client_name} (order {order.order_id})")

    report_data = create_report(
        name=order.client_name,
        year=order.birth_year,
        month=order.birth_month,
        day=order.birth_day,
        hour=order.birth_hour,
        minute=order.birth_minute,
        gender=order.gender,
        question_focus=order.focus,
    )

    output = save_report(report_data, order_id=order.order_id)
    logger.info(f"Report saved: {output}")
    return output


# ── Serve Generated PDFs ──

from fastapi.responses import FileResponse
from pathlib import Path

REPORTS_DIR = Path(__file__).parent.parent / "reports"


@app.get("/download/{order_id}")
def download_report(order_id: str):
    """Serve generated PDF for download"""
    pdf_path = REPORTS_DIR / f"report-{order_id}.pdf"
    if not pdf_path.exists():
        # Try HTML fallback
        html_path = REPORTS_DIR / f"report-{order_id}.html"
        if html_path.exists():
            return FileResponse(str(html_path), media_type="text/html")
        raise HTTPException(status_code=404, detail="Report not found")
    return FileResponse(str(pdf_path), media_type="application/pdf", filename=f"BaZi-Reading-{order_id}.pdf")


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
