// names/ranges 必须与 Date-Project/backend/services/listing_price_tier_service.py
// 里的 LABELS/RANGES、USD_LABELS/USD_RANGES 一一对应，长度也要一致：
// 人民币5档、美元7档。后端返回的 tiers 按序号排列，前端按下标取色和取名。
export function pricePresentation(platform) {
  return platform === 'ebay'
    ? { currency: 'USD', label: '美元', rateField: 'rate_org',
        // 美元档位不用业务分层叫法，图例和表头直接显示价格段。
        names: ['0-5', '5-20', '20-50', '50-100', '100-200', '200-500', '500以上'],
        shorts: ['0-5', '5-20', '20-50', '50-100', '100-200', '200-500', '500+'],
        // compacts 用在首页卡片那一行小字上：7列时带$的完整区间会折行，只放数字。
        compacts: ['0-5', '5-20', '20-50', '50-100', '100-200', '200-500', '500+'],
        ranges: ['$0–<5', '$5–<20', '$20–<50', '$50–<100', '$100–<200', '$200–<500', '≥ $500'],
        formula: '美元原价直接使用；其他原币价格×该币种rate_org÷USDrate_org（先换人民币再换美元），人民币原价直接除以USDrate_org' }
    : { currency: 'CNY', label: '人民币', rateField: 'my_rate',
        names: ['低价引流层', '基础走量层', '利润核心层', '高客单层', '专业/稀缺层'],
        shorts: ['引流', '走量', '核心', '高客单', '稀缺'],
        // 人民币只有5列，放得下完整区间，与改动前保持一致。
        compacts: ['< ¥340', '¥340–<680', '¥680–<1,020', '¥1,020–1,690', '> ¥1,690'],
        ranges: ['< ¥340', '¥340–<680', '¥680–<1,020', '¥1,020–1,690', '> ¥1,690'],
        formula: '人民币=原币价格×my_rate' }
}
