package com.ruoyi.system.service.operation.compute;

import java.math.BigDecimal;
import java.math.RoundingMode;

import org.springframework.stereotype.Service;

import com.ruoyi.system.domain.operation.external.EbayLinkTemplate;
import com.ruoyi.system.domain.operation.external.GoodcangProductInfo;

/**
 * 跟卖利润率 & 底线价计算器。
 * 从旧项目 GoodcangCallbackController.calcTracking() 移植。
 *
 * 公式（按站点不同）：
 *   变量: M=跟卖价, N=商品成本, O=体积重, P=实重, Q=汇率, T=目标利润率
 *   美国: cw=max(0.8*O,P), platformRate=0.8575, poundCost=(N+6*O)/Q
 *   德国: cw=max(O,P), platformRate=0.678, poundCost=(N+8.42*O)/Q
 *   英国: cw=max(O,P), platformRate=0.705, poundCost=(N+9.85*O)/Q
 *
 *   利润 = M*platformRate - poundCost - freightCost
 *   利润率 = 利润 / M
 *   底线价 = (poundCost + freightCost) / (platformRate - T)
 */
@Service
public class TrackingProfitCalcService
{
    public CalcResult calc(String site, BigDecimal trackingPrice, GoodcangProductInfo product, EbayLinkTemplate linkTemplate)
    {
        BigDecimal M = trackingPrice;
        if (M == null || M.compareTo(BigDecimal.ZERO) <= 0) return new CalcResult(null, null);

        BigDecimal N = product.getPrice();
        if (N == null) return new CalcResult(null, null);

        BigDecimal O = product.getVolume() != null ? product.getVolume() : BigDecimal.ZERO;
        BigDecimal P = product.getRealWeight() != null ? product.getRealWeight() : BigDecimal.ZERO;

        double pw = P.doubleValue();
        double vw = O.doubleValue();

        if (linkTemplate == null || linkTemplate.getExchangeRate() == null
                || linkTemplate.getExchangeRate().compareTo(BigDecimal.ZERO) == 0)
            return new CalcResult(null, null);

        BigDecimal Q = linkTemplate.getExchangeRate();
        BigDecimal T = linkTemplate.getProfitRate() != null
                ? BigDecimal.valueOf(linkTemplate.getProfitRate()).divide(BigDecimal.valueOf(100), 6, RoundingMode.HALF_UP)
                : BigDecimal.valueOf(0.08);

        BigDecimal poundCost, freightCost, platformRate;
        double cw;

        if ("美国".equals(site))
        {
            cw = Math.max(0.8 * vw, pw);
            platformRate = BigDecimal.valueOf(0.8575);
            poundCost = N.add(BigDecimal.valueOf(6).multiply(O)).divide(Q, 6, RoundingMode.HALF_UP);
            if (Math.max(vw, pw) < 0.5)
                freightCost = BigDecimal.valueOf(4).add(BigDecimal.valueOf(8).multiply(BigDecimal.valueOf(cw)));
            else
                freightCost = BigDecimal.valueOf(8).add(BigDecimal.valueOf(1.7).multiply(BigDecimal.valueOf(cw)));
        }
        else if ("德国".equals(site))
        {
            cw = Math.max(vw, pw);
            platformRate = BigDecimal.valueOf(0.678);
            poundCost = N.add(BigDecimal.valueOf(8.42).multiply(O)).divide(Q, 6, RoundingMode.HALF_UP);
            freightCost = BigDecimal.valueOf(3.5).add(BigDecimal.valueOf(0.3).multiply(BigDecimal.valueOf(cw)));
        }
        else // 英国
        {
            cw = Math.max(vw, pw);
            platformRate = BigDecimal.valueOf(0.705);
            poundCost = N.add(BigDecimal.valueOf(9.85).multiply(O)).divide(Q, 6, RoundingMode.HALF_UP);
            freightCost = BigDecimal.valueOf(2).add(BigDecimal.valueOf(0.3).multiply(BigDecimal.valueOf(cw)));
        }

        BigDecimal netIncome = M.multiply(platformRate);
        BigDecimal profit = netIncome.subtract(poundCost).subtract(freightCost);
        BigDecimal margin = M.compareTo(BigDecimal.ZERO) > 0
                ? profit.divide(M, 6, RoundingMode.HALF_UP)
                : BigDecimal.ZERO;

        BigDecimal denominator = platformRate.subtract(T);
        BigDecimal floorPrice = null;
        if (denominator.compareTo(BigDecimal.ZERO) > 0)
        {
            floorPrice = poundCost.add(freightCost).divide(denominator, 2, RoundingMode.HALF_UP);
        }

        return new CalcResult(margin, floorPrice);
    }

    public static class CalcResult
    {
        public final BigDecimal trackingProfitMargin;
        public final BigDecimal floorPrice;

        CalcResult(BigDecimal margin, BigDecimal floor)
        {
            this.trackingProfitMargin = margin;
            this.floorPrice = floor;
        }
    }
}
