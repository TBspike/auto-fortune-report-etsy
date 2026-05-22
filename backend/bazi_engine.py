"""
八字排盘引擎 — 基于 lunar_python
输入：公历日期 + 时间 → 输出八字/五行/十神/大运/流年
"""
from lunar_python import Solar, Lunar
from typing import Dict, List, Optional
from dataclasses import dataclass


@dataclass
class BaziResult:
    """八字排盘结果"""
    year_pillar: str       # 年柱
    month_pillar: str      # 月柱
    day_pillar: str        # 日柱
    hour_pillar: str       # 时柱
    year_tiangan: str      # 年天干
    month_tiangan: str     # 月天干
    day_tiangan: str       # 日天干
    hour_tiangan: str      # 时天干
    year_dizhi: str        # 年地支
    month_dizhi: str       # 月地支
    day_dizhi: str         # 日地支
    hour_dizhi: str        # 时地支
    day_master: str        # 日主
    five_elements: Dict    # 五行
    nayin: List[str]       # 纳音
    luck_start_age: int    # 起运年龄
    luck_direction: str    # 大运顺逆
    great_luck: List[str]  # 大运
    current_luck: str      # 当前大运
    shens: Dict            # 神煞


# 天干 → 五行 映射表
TIANGAN_WUXING = {'甲': '木', '乙': '木', '丙': '火', '丁': '火',
                  '戊': '土', '己': '土', '庚': '金', '辛': '金',
                  '壬': '水', '癸': '水'}
# 地支 → 五行 映射表
DIZHI_WUXING = {'子': '水', '丑': '土', '寅': '木', '卯': '木',
                '辰': '土', '巳': '火', '午': '火', '未': '土',
                '申': '金', '酉': '金', '戌': '土', '亥': '水'}


def calculate_bazi(year: int, month: int, day: int, hour: int, minute: int = 0,
                   gender: str = "male", name: str = "Client") -> BaziResult:
    """
    核心排盘函数
    """
    solar = Solar.fromYmdHms(year, month, day, hour, minute, 0)
    lunar = solar.getLunar()

    # 八字
    bazi = lunar.getEightChar()

    # 日主
    day_master = bazi.getDayGan()

    # 四柱八字
    gan_zhi_list = [
        f"{bazi.getYearGan()}{bazi.getYearZhi()}",
        f"{bazi.getMonthGan()}{bazi.getMonthZhi()}",
        f"{bazi.getDayGan()}{bazi.getDayZhi()}",
        f"{bazi.getTimeGan()}{bazi.getTimeZhi()}",
    ]

    # 五行含量（用映射表替代 getWuXing 方法）
    elements_map = {
        '金': 0, '木': 0, '水': 0, '火': 0, '土': 0
    }
    for gan in [bazi.getYearGan(), bazi.getMonthGan(),
                bazi.getDayGan(), bazi.getTimeGan()]:
        wuxing = TIANGAN_WUXING.get(gan)
        if wuxing:
            elements_map[wuxing] += 1
    for zhi in [bazi.getYearZhi(), bazi.getMonthZhi(),
                bazi.getDayZhi(), bazi.getTimeZhi()]:
        wuxing = DIZHI_WUXING.get(zhi)
        if wuxing:
            elements_map[wuxing] += 1

    # 纳音
    nayin = [
        bazi.getYearNaYin(),
        bazi.getMonthNaYin(),
        bazi.getDayNaYin(),
        bazi.getTimeNaYin(),
    ]

    # 大运 (via getYun)
    gender_key = '男' if gender == 'male' else '女'
    yun = bazi.getYun(gender_key)
    start_age = max(0, yun.getStartYear())
    forward = yun.isForward()
    luck_direction = "顺排" if forward else "逆排"
    luck_cycles = yun.getDaYun()
    great_luck = [dy.getGanZhi() for dy in luck_cycles if dy.getGanZhi()]

    # 当前大运（第一个有意义的大运）
    current_luck = great_luck[0] if great_luck else ""

    # 神煞
    shens = {}
    try:
        shens = {
            "year_shen": str(bazi.getYearShen()),
            "month_shen": str(bazi.getMonthShen()),
            "day_shen": str(bazi.getDayShen()),
            "time_shen": str(bazi.getTimeShen()),
        }
    except:
        pass

    return BaziResult(
        year_pillar=gan_zhi_list[0],
        month_pillar=gan_zhi_list[1],
        day_pillar=gan_zhi_list[2],
        hour_pillar=gan_zhi_list[3],
        year_tiangan=str(bazi.getYearGan()),
        month_tiangan=str(bazi.getMonthGan()),
        day_tiangan=str(bazi.getDayGan()),
        hour_tiangan=str(bazi.getTimeGan()),
        year_dizhi=str(bazi.getYearZhi()),
        month_dizhi=str(bazi.getMonthZhi()),
        day_dizhi=str(bazi.getDayZhi()),
        hour_dizhi=str(bazi.getTimeZhi()),
        day_master=str(day_master),
        five_elements=elements_map,
        nayin=nayin,
        luck_start_age=start_age,
        luck_direction=luck_direction,
        great_luck=great_luck,
        current_luck=current_luck,
        shens=shens,
    )


def analyze_elements_balance(elements: Dict) -> List[str]:
    """分析五行平衡，返回分析文本"""
    dominant = max(elements, key=elements.get)
    weakest = min(elements, key=elements.get)
    return [
        f"Dominant element: {dominant}",
        f"Weakest element: {weakest}",
        f"Element distribution: {elements}",
    ]


# Test
if __name__ == "__main__":
    r = calculate_bazi(1990, 5, 15, 10, 30, "male")
    print(f"八字: {r.year_pillar} {r.month_pillar} {r.day_pillar} {r.hour_pillar}")
    print(f"日主: {r.day_master}")
    print(f"五行: {r.five_elements}")
    print(f"纳音: {r.nayin}")
    print(f"起运: {r.luck_start_age}岁")
    print(f"大运: {', '.join(r.great_luck[:4])}")
