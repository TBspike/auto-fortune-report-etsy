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

# ── Config (module-level — loaded once at import, rarely changed) ──
ETSY_WEBHOOK_SECRET = os.environ.get("ETSY_WEBHOOK_SECRET", "")
GUMROAD_WEBHOOK_SECRET = os.environ.get("GUMROAD_WEBHOOK_SECRET", "")
REPORT_BASE_URL = os.environ.get("REPORT_BASE_URL", "http://localhost:8000")


def _email_config():
    """Read Resend API key from env at call time"""
    return {
        "from": os.environ.get("EMAIL_FROM", "onboarding@resend.dev"),
        "api_key": os.environ.get("RESEND_API_KEY", ""),
    }

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
    """Send PDF download link to buyer via Resend API (works on Railway since it uses HTTPS)"""
    cfg = _email_config()
    if not cfg["api_key"]:
        logger.info(f"[EMAIL MOCK] To: {to_email}, URL: {download_url}")
        return

    import resend
    resend.api_key = cfg["api_key"]

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

    try:
        r = resend.Emails.send({
            "from": cfg["from"],
            "to": [to_email],
            "subject": subject,
            "text": body,
        })
        logger.info(f"Email sent to {to_email} for order {order_id} (id={r.get('id', '?')})")
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
    from pathlib import Path
    import os
    cwd = os.getcwd()
    reports_dir = Path(__file__).parent / "reports"
    reports_exist = reports_dir.exists()
    files = [str(f.name) for f in reports_dir.iterdir()] if reports_exist else []
    cfg = _email_config()
    return {
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "email_configured": bool(cfg["api_key"]),
        "email_from": cfg["from"],
        "reports_dir": str(reports_dir),
        "reports_dir_exists": reports_exist,
        "report_files": files,
    }


@app.get("/diagnose/email")
def diagnose_email():
    """Test Resend API connectivity"""
    cfg = _email_config()
    result = {
        "config": {
            "api_key_set": bool(cfg["api_key"]),
            "from": cfg["from"],
        }
    }
    if not cfg["api_key"]:
        result["error"] = "RESEND_API_KEY not set"
        return result

    try:
        import resend
        resend.api_key = cfg["api_key"]
        r = resend.Emails.send({
            "from": cfg["from"],
            "to": [cfg["from"]],
            "subject": "Diagnostic test from Railway",
            "text": "If you see this, Resend is working on Railway.",
        })
        result["send"] = "OK"
        result["email_id"] = r.get("id", "?")
    except Exception as e:
        result["error"] = str(e)

    return result


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


# ── Gumroad Webhook ──

@app.post("/webhook/gumroad")
async def gumroad_webhook(request: Request):
    """Receive Gumroad sale webhook and trigger report generation"""
    raw_body = await request.body()
    payload = json.loads(raw_body)
    sale_id = payload.get("sale_id", "")
    email = payload.get("email", "")

    if not sale_id:
        logger.warning("Gumroad webhook received without sale_id")
        return {"status": "ignored", "reason": "missing sale_id"}

    logger.info(f"Received Gumroad webhook for sale #{sale_id}")

    # Log full payload for debugging (first time only)
    if sale_id == "test_ping":
        logger.info(f"Gumroad test ping payload: {json.dumps(payload, indent=2)[:2000]}")
        return {"status": "ok", "note": "test ping received (no report generated)"}

    # Optional: verify Gumroad webhook signature
    gumroad_signature = request.headers.get("x-gumroad-signature", "")
    if GUMROAD_WEBHOOK_SECRET and gumroad_signature:
        expected = hmac.new(
            GUMROAD_WEBHOOK_SECRET.encode(),
            raw_body,
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected, gumroad_signature):
            logger.warning(f"Invalid Gumroad signature for sale {sale_id}")
            raise HTTPException(status_code=401, detail="Invalid webhook signature")

    # Parse custom_fields
    order_data = parse_gumroad_custom_fields(payload, sale_id, email)
    if order_data is None:
        logger.error(f"Failed to parse Gumroad custom fields for sale {sale_id}")
        return {"status": "error", "reason": "missing or invalid custom_fields"}

    # Process in background thread
    from concurrent.futures import ThreadPoolExecutor
    executor = ThreadPoolExecutor()
    executor.submit(process_gumroad_order, order_data)

    return {"status": "accepted", "sale_id": sale_id}


def parse_gumroad_custom_fields(payload: dict, sale_id: str, email: str) -> Optional[OrderData]:
    """Parse Gumroad custom_fields array into OrderData.

    Gumroad sends custom_fields as:
    [
      {"name": "Full Name", "value": "John", "type": "short-answer"},
      {"name": "Birth Date (YYYY-MM-DD)", "value": "1990-05-15", ...},
      ...
    ]
    The 'name' field is the Gumroad Input block's label (exact text you entered).
    """
    custom_fields = payload.get("custom_fields", [])
    if not custom_fields:
        logger.warning(f"Gumroad payload has no custom_fields (sale {sale_id})")
        return None

    # Build a lookup dict from the custom_fields array
    raw_fields = {}
    for cf in custom_fields:
        name = cf.get("name", "").strip().lower()
        value = cf.get("value", "").strip()
        raw_fields[name] = value

    # Fuzzy match — Gumroad uses the label text verbatim as field name
    client_name = ""
    birth_date_str = ""
    birth_time_str = ""
    gender = ""

    for key, value in raw_fields.items():
        if not value:
            continue
        kl = key.lower()
        if "full name" in kl or kl == "name":
            client_name = value
        elif "birth date" in kl or "birthday" in kl or "birthday" in kl:
            birth_date_str = value
        elif "birth time" in kl or "birthtime" in kl:
            birth_time_str = value
        elif "gender" in kl:
            gender = value

    if not client_name or not birth_date_str:
        logger.warning(f"Gumroad custom_fields missing name or birth date. Raw keys: {list(raw_fields.keys())}")
        return None

    # Parse birth date (YYYY-MM-DD)
    birth_parts = birth_date_str.split("-")
    if len(birth_parts) != 3:
        logger.warning(f"Gumroad birth date format invalid: {birth_date_str}")
        return None

    try:
        birth_year = int(birth_parts[0])
        birth_month = int(birth_parts[1])
        birth_day = int(birth_parts[2])
    except (ValueError, IndexError):
        logger.warning(f"Gumroad birth date values not integers: {birth_date_str}")
        return None

    # Parse birth time (HH:MM, optional)
    birth_hour = 12
    birth_minute = 0
    if birth_time_str:
        time_parts = birth_time_str.split(":")
        try:
            birth_hour = int(time_parts[0]) if time_parts else 12
            birth_minute = int(time_parts[1]) if len(time_parts) > 1 else 0
        except (ValueError, IndexError):
            logger.warning(f"Gumroad birth time format invalid: {birth_time_str}, defaulting to 12:00")

    # Normalize gender
    gender_lower = gender.lower().strip() if gender else ""
    if gender_lower in ("male", "m"):
        gender = "male"
    elif gender_lower in ("female", "f"):
        gender = "female"
    else:
        gender = "male"

    return OrderData(
        order_id=f"gu-{sale_id}",
        client_name=client_name,
        birth_year=birth_year,
        birth_month=birth_month,
        birth_day=birth_day,
        birth_hour=birth_hour,
        birth_minute=birth_minute,
        gender=gender,
        buyer_email=email,
        focus="comprehensive",
    )


def process_gumroad_order(order: OrderData):
    """Background processing of a Gumroad order"""
    pdf_path = generate_report_pdf(order)
    if pdf_path:
        download_url = f"{REPORT_BASE_URL}/download/{order.order_id}"
        logger.info(f"Gumroad report generated for order {order.order_id}: {download_url}")
        for attempt in range(3):
            try:
                send_report_email(
                    to_email=order.buyer_email,
                    download_url=download_url,
                    order_id=order.order_id,
                    client_name=order.client_name,
                )
                break
            except Exception as e:
                logger.warning(f"Email attempt {attempt+1} failed: {e}")
    else:
        logger.error(f"Failed to generate Gumroad report for order {order.order_id}")


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
    """API endpoint to manually trigger report generation (for testing, runs in background)"""
    from concurrent.futures import ThreadPoolExecutor
    executor = ThreadPoolExecutor()
    future = executor.submit(generate_report_pdf, order)

    try:
        result = future.result(timeout=120)
        return {
            "status": "completed",
            "order_id": order.order_id,
            "pdf_path": result,
        }
    except Exception as e:
        logger.error(f"Process order failed: {e}")
        return {
            "status": "processing",
            "order_id": order.order_id,
            "message": "Report is being generated in the background. Check /download/TEST-001 in a minute.",
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

REPORTS_DIR = Path(__file__).parent / "reports"


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
