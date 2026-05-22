# auto-fortune-report Etsy 上线 — 项目诏书

## 项目目标

全自动英文八字报告，上线 Etsy 销售。
客户付钱 → AI 排盘 → 生成 PDF → 自动交付，零人工干预。

## 产品线

| 产品 | 定价 | 内容 |
|------|:----:|------|
| BaZi Birth Chart Report | $29 | 八字全盘：性格/事业/财运/感情 |
| 2027 Yearly Fortune | $19 | 流年运势+每月吉凶 |
| Love Compatibility | $39 | 双方八字合盘 |
| BaZi + Zi Wei Combo | $49 | 八字+紫微双盘 |

## 后端架构

```
backend/
├── main.py              # FastAPI 服务器 + Etsy Webhook
├── bazi_engine.py        # 八字排盘引擎
├── report_generator.py   # AI 报告生成
└── pdf_renderer.py       # PDF 渲染
```

## 部署清单

1. 注册 Etsy 卖家账号 + 开通店铺
2. 注册 Payoneer 收款
3. 部署后端到 Railway（免费）
4. 配置域名和 Gmail 发件
5. 上架 4 个商品到 Etsy
6. 对接 Etsy Webhook（订单 → 自动生成 → 自动交付）
7. 测试全流程

## 调研参考

已有 12 份调研报告在 `auto-fortune-report/` 目录下，需要时查阅。

## 纠察院要求

- 上架前测试 3 份真实八字报告，确认英文质量和排盘准确
- 测试全自动交付流程，确认客户能收到 PDF
- 确认 Etsy 商品描述合规，没有违规词
