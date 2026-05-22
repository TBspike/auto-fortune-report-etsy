"""
PDF 渲染器 — 将 AI 生成的报告渲染为专业排版英文 PDF
使用 Playwright (Headless Chromium) 渲染 HTML → PDF
"""
import os
import asyncio
from datetime import datetime
from pathlib import Path
from jinja2 import Environment, FileSystemLoader

REPORTS_DIR = Path(__file__).parent.parent / "reports"
TEMPLATES_DIR = Path(__file__).parent.parent / "templates"


def render_report_html(report_data: dict) -> str:
    """Render report data into HTML using the Jinja2 template"""
    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))
    template = env.get_template("report_template.html")

    html = template.render(
        name=report_data["client_name"],
        date=datetime.now().strftime("%B %d, %Y"),
        year_pillar=report_data["bazi_chart"]["year"],
        month_pillar=report_data["bazi_chart"]["month"],
        day_pillar=report_data["bazi_chart"]["day"],
        hour_pillar=report_data["bazi_chart"]["hour"],
        day_master=report_data["day_master"],
        elements=report_data["elements"],
        luck_start_age=report_data["luck_start_age"],
        great_luck=report_data["great_luck"],
        report_body=report_data["report_text"].replace("\n", "<br>\n"),
        order_id=report_data.get("order_id", "N/A"),
    )
    return html


async def html_to_pdf(html: str, output_path: str) -> str:
    """Convert HTML to PDF using Playwright"""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("⚠️ Playwright not installed. Install with: pip3 install playwright && python3 -m playwright install chromium")
        return ""

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.set_content(html, wait_until="networkidle")
        await page.pdf(
            path=output_path,
            format="A4",
            margin={"top": "0.8in", "bottom": "0.8in", "left": "0.8in", "right": "0.8in"},
            print_background=True,
        )
        await browser.close()

    return output_path


def save_report(report_data: dict, order_id: str = "") -> str:
    """完整流程：渲染 HTML → 生成 PDF → 保存到 reports/ 目录"""
    report_data["order_id"] = order_id or f"ORD-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    # Generate HTML
    html = render_report_html(report_data)

    # Save HTML for debugging
    html_path = REPORTS_DIR / f"report-{report_data['order_id']}.html"
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(html_path, "w") as f:
        f.write(html)

    # Generate PDF
    pdf_path = str(REPORTS_DIR / f"report-{report_data['order_id']}.pdf")
    try:
        pdf_result = asyncio.run(html_to_pdf(html, pdf_path))
        if pdf_result:
            return pdf_result
    except Exception as e:
        print(f"⚠️ PDF generation failed: {e}")
        # Return HTML path as fallback
        return str(html_path)

    return str(html_path)


if __name__ == "__main__":
    # Test with sample data
    test_data = {
        "client_name": "Test User",
        "bazi_chart": {
            "year": "庚午",
            "month": "辛巳",
            "day": "甲申",
            "hour": "乙亥",
        },
        "day_master": "甲 (Big Tree)",
        "elements": {"金": 2, "木": 1, "水": 1, "火": 3, "土": 1},
        "luck_start_age": 4,
        "great_luck": ["壬午", "癸未", "甲申", "乙酉", "丙戌", "丁亥"],
        "report_text": """
        <h2>1. Your Day Master: The Core of Your Being</h2>
        <p>Your Day Master is <strong>甲 (Big Tree)</strong> — representing leadership, ambition, and growth. Like a mighty tree, you naturally strive upward, seeking to expand your influence and reach your full potential.</p>
        <p>The combination of your Four Pillars — <strong>庚午 辛巳 甲申 乙亥</strong> — creates a unique energetic blueprint that shapes your life journey.</p>
        <h2>2. Five Elements: Your Internal Energy Blueprint</h2>
        <p>Your Five Element distribution: <strong>金: 2, 木: 1, 水: 1, 火: 3, 土: 1</strong></p>
        <p>The dominant element in your chart is <strong>Fire</strong>, which brings warmth, passion, and creative energy. The element to nurture is <strong>Water/Wood</strong>, suggesting areas for growth and balance.</p>
        <h2>3. Career & Wealth: Your Professional Path</h2>
        <p>Your chart reveals natural leadership abilities. With 甲 Wood as your Day Master and strong Fire energy, careers in creative direction, entrepreneurship, or roles that allow you to guide others would be fulfilling.</p>
        <h2>4. Relationships: Understanding Your Patterns</h2>
        <p>The Earthly Branches in your chart suggest you approach relationships with depth and loyalty. Your 申 branch indicates a thoughtful, analytical approach to partnerships.</p>
        <h2>5. Timing & Life Cycles: When Things Happen</h2>
        <p>Your first Luck Cycle begins at age 4. Your Great Luck Cycles: 壬午 → 癸未 → 甲申 → 乙酉 → 丙戌 → 丁亥</p>
        <p>Each 10-year cycle activates different aspects of your chart. Your current position in this cycle is significant for career decisions.</p>
        <h2>6. Practical Guidance</h2>
        <p>1. <strong>Career</strong>: Focus on leadership roles that allow growth<br>2. <strong>Relationships</strong>: Balance your analytical nature with emotional openness<br>3. <strong>Timing</strong>: The coming years favor expansion and new initiatives<br>4. <strong>Growth</strong>: Nurture Water/Wood elements through rest and flexibility</p>
        <hr>
        <p><em>This report is for entertainment and self-reflection purposes only. It is not a substitute for professional advice.</em></p>
        """,
    }

    path = save_report(test_data, order_id="TEST-001")
    print(f"✅ Report saved: {path}")
