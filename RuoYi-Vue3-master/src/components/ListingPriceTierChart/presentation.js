export function pricePresentation(platform) {
  return platform === 'ebay'
    ? { currency: 'USD', label: '美元', rateField: 'rate_org', ranges: ['< $50', '$50–<100', '$100–<150', '$150–250', '> $250'],
        formula: '美元原价直接使用；其他原币价格×该币种rate_org÷USDrate_org（先换人民币再换美元），人民币原价直接除以USDrate_org' }
    : { currency: 'CNY', label: '人民币', rateField: 'my_rate', ranges: ['< ¥340', '¥340–<680', '¥680–<1,020', '¥1,020–1,690', '> ¥1,690'],
        formula: '人民币=原币价格×my_rate' }
}
