"""
AI 报告生成器 — 用 LLM 将八字排盘结果转化为英文报告
"""
import json
import os
from typing import Dict, Optional
from bazi_engine import BaziResult, calculate_bazi

def _llm_config():
    """Read LLM config from env at call time (not module load time)"""
    return {
        "api_key": os.environ.get("LLM_API_KEY", ""),
        "api_url": os.environ.get("LLM_API_URL", "https://api.deepseek.com/v1/chat/completions"),
        "model": os.environ.get("LLM_MODEL", "deepseek-chat"),
    }


def get_report_prompt(bazi: BaziResult, name: str, gender: str,
                      question_focus: str = "comprehensive") -> str:
    """生成报告提示词 — 基于共享知识库的专业技法"""
    elements_desc = ", ".join([f"{k}: {v}" for k, v in bazi.five_elements.items()])
    nayin_desc = ", ".join(bazi.nayin)
    luck_desc = ", ".join(bazi.great_luck[:6])

    return f"""You are a professional Chinese BaZi (Four Pillars of Destiny) consultant.
Write a comprehensive, personalized BaZi reading report for a client.

CLIENT INFO:
- Name: {name}
- Gender: {gender}
- Focus: {question_focus}

BAZI CHART:
- Four Pillars: {bazi.year_pillar} {bazi.month_pillar} {bazi.day_pillar} {bazi.hour_pillar}
- Day Master (日主): {bazi.day_tiangan}
- Five Elements Distribution: {elements_desc}
- Na Yin (纳音): {nayin_desc}
- Luck Cycle Starts At: {bazi.luck_start_age} years old
- Luck Direction: {bazi.luck_direction}
- Great Luck Cycles (first 6): {luck_desc}

WRITING GUIDELINES:
1. Use a warm, insightful, coaching-style tone — like a wise friend guiding self-discovery
2. Organize the report into these EXACT sections with headers:
   - "1. Your Day Master: The Core of Your Being"
   - "2. Five Elements: Your Internal Energy Blueprint"
   - "3. Career & Wealth: Your Professional Path"
   - "4. Relationships: Understanding Your Patterns"
   - "5. Timing & Life Cycles: When Things Happen"
   - "6. Practical Guidance: Your Actionable Path Forward"
3. Each section should be 2-4 paragraphs of substantive content
4. Use psychological/coaching frameworks to bridge Eastern wisdom with Western understanding
5. Connect each insight to actionable life advice
6. Reference the specific elements, stems, and branches from THEIR chart — make it personal
7. IMPORTANT: Include a disclaimer at the bottom: "This report is for entertainment and self-reflection purposes only. It is not a substitute for professional advice."
8. Write in clear, natural English, approximately 2000-3000 words total
9. Make each section feel personalized — reference their specific chart data throughout

OUTPUT ONLY THE REPORT CONTENT. No preamble, no explanation.
"""


def generate_report_via_api(prompt: str) -> Optional[str]:
    """调用 LLM API 生成报告（配置从环境变量实时读取）"""
    cfg = _llm_config()
    if not cfg["api_key"]:
        # Fallback: return a template-based report when no API key
        return None

    import requests
    try:
        resp = requests.post(
            cfg["api_url"],
            headers={
                "Authorization": f"Bearer {cfg['api_key']}",
                "Content-Type": "application/json",
            },
            json={
                "model": cfg["model"],
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.7,
                "max_tokens": 4000,
            },
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"⚠️ API call failed: {e}")
        return None


def generate_template_report(bazi: BaziResult, name: str) -> str:
    """生成模板报告（API不可用时的备用方案）"""
    day_master_meaning = {
        "甲": "Big Tree — natural leader, ambitious, growth-oriented",
        "乙": "Vine — flexible, cooperative, artistic",
        "丙": "Sun — warm, charismatic, radiant energy",
        "丁": "Candle — focused, refined, intense",
        "戊": "Mountain — stable, reliable, grounded",
        "己": "Soil — nurturing, adaptable, thoughtful",
        "庚": "Metal — strong, determined, cutting through obstacles",
        "辛": "Jewel — refined, precious, detail-oriented",
        "壬": "Ocean — expansive, intuitive, powerful",
        "癸": "Rain — gentle, wise, flowing",
    }

    dm = bazi.day_tiangan
    dm_desc = day_master_meaning.get(dm, "unique energy pattern")

    dominant = max(bazi.five_elements, key=bazi.five_elements.get)
    weakest = min(bazi.five_elements, key=bazi.five_elements.get)

    return f"""# PERSONALIZED BAZI READING
## For: {name}

---

### 1. Your Day Master: The Core of Your Being

Your Day Master is **{bazi.day_tiangan} ({dm_desc})**.
This represents your true self — the energy that runs through everything you do.

As a {dm_desc}, you possess unique strengths and natural tendencies that shape your life path.
Your Four Pillars — {bazi.year_pillar} {bazi.month_pillar} {bazi.day_pillar} {bazi.hour_pillar} —
create a specific energetic blueprint that influences your personality, relationships, and life journey.

The Heavenly Stem {bazi.day_tiangan} combined with the Earthly Branch {bazi.day_dizhi}
in your Day Pillar suggests someone who approaches life with depth and intention.

---

### 2. Five Elements: Your Internal Energy Blueprint

Your Five Element distribution: {dict(bazi.five_elements)}

- **Dominant Element: {dominant}** — This energy is abundant in your chart, representing your natural strength.
- **Element to Nurture: {weakest}** — This element is less present, suggesting areas for growth and balance.

The Five Elements (Wood, Fire, Earth, Metal, Water) interact in a constant cycle of creation and control.
Understanding your unique elemental makeup helps explain your natural tendencies and challenges.

Your Na Yin (纳音) readings — {', '.join(bazi.nayin)} — add additional layers of nuance to your energetic profile,
like subtle harmonies beneath the main melody of your chart.

---

### 3. Career & Wealth: Your Professional Path

Your chart reveals natural aptitudes that align with certain career paths.
The combination of your Day Master and the Element distribution suggests strengths in areas
that allow you to express your core {dm_desc} energy.

Your luck cycles indicate optimal timing for career moves and financial decisions.
Your first Luck Cycle begins at age {bazi.luck_start_age}, which marks a significant turning point.

---

### 4. Relationships: Understanding Your Patterns

The Earthly Branches in your chart reveal how you relate to others.
Your {bazi.day_dizhi} branch suggests particular patterns in close relationships.

Understanding these patterns empowers you to build stronger, more conscious connections
with partners, family, and colleagues.

---

### 5. Timing & Life Cycles: When Things Happen

Your Luck Cycle direction is {bazi.luck_direction}, with your first cycle beginning at age {bazi.luck_start_age}.

Your Great Luck Cycles:
{chr(10).join([f'  • {luck}' for luck in bazi.great_luck[:8]])}

Each 10-year cycle activates different aspects of your chart, creating favorable periods
for different life pursuits. Understanding where you are in this cycle helps you
make better-timed decisions.

---

### 6. Practical Guidance: Your Actionable Path Forward

1. **Career**: Focus on roles that align with your Day Master's natural strengths
2. **Relationships**: Be aware of your relational patterns indicated by your Earthly Branches
3. **Timing**: Your current Luck Cycle phase suggests optimal timing for [specific guidance based on your chart]
4. **Growth**: Nurture your weaker element ({weakest}) through associated activities, colors, and environments
5. **Self-Care**: Honor your dominant element ({dominant}) while creating space for balance

---

*This report is for entertainment and self-reflection purposes only.
It is not a substitute for professional advice.
For a more detailed reading, consider consulting a professional BaZi practitioner.*

Generated by AI BaZi Reading Engine
"""


def create_report(name: str, year: int, month: int, day: int,
                  hour: int = 12, minute: int = 0, gender: str = "male",
                  question_focus: str = "comprehensive") -> Dict:
    """完整流程：排盘 → 生成报告"""
    bazi = calculate_bazi(year, month, day, hour, minute, gender, name)

    # Try API first, fallback to template
    prompt = get_report_prompt(bazi, name, gender, question_focus)
    report = generate_report_via_api(prompt)
    if not report:
        report = generate_template_report(bazi, name)

    return {
        "client_name": name,
        "bazi_chart": {
            "year": bazi.year_pillar,
            "month": bazi.month_pillar,
            "day": bazi.day_pillar,
            "hour": bazi.hour_pillar,
        },
        "day_master": str(bazi.day_tiangan),
        "elements": bazi.five_elements,
        "luck_start_age": bazi.luck_start_age,
        "great_luck": bazi.great_luck[:6],
        "report_text": report,
        "report_word_count": len(report.split()),
    }


if __name__ == "__main__":
    result = create_report("Test Client", 1990, 5, 15, 10, 30, "male")
    print(f"报告长度: {result['report_word_count']} 词")
    print(f"八字: {result['bazi_chart']}")
    print(f"日主: {result['day_master']}")
    print(f"\n报告预览 (前500字):")
    print(result['report_text'][:500])
