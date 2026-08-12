package com.ruoyi.system.service.operation.ebay;

import java.math.BigDecimal;
import java.math.RoundingMode;
import com.ruoyi.common.exception.ServiceException;
import com.ruoyi.system.domain.operation.ebay.EbayCompetitorFormulaConfig;
import com.ruoyi.system.domain.operation.ebay.EbayCompetitorProduct;
import org.springframework.stereotype.Component;

/** 按站点配置计算eBay竞品底价、利润率和目标产品成本。 */
@Component
public class EbayCompetitorCalculator
{
    private static final int INTERNAL_SCALE = 12;

    public void calculate(EbayCompetitorProduct product, EbayCompetitorFormulaConfig config)
    {
        BigDecimal length = dimension(product.getLengthCm());
        BigDecimal width = dimension(product.getWidthCm());
        BigDecimal height = dimension(product.getHeightCm());
        product.setLengthCm(length);
        product.setWidthCm(width);
        product.setHeightCm(height);

        BigDecimal rawVolume = divide(length.multiply(width).multiply(height), config.getVolumetricDivisor());
        BigDecimal volume = rawVolume.setScale(2, RoundingMode.HALF_UP);
        product.setVolumetricWeightKg(volume);
        product.setCurrency(config.getCurrency());
        product.setFormulaVersion(config.getFormulaVersion());

        if ("US".equals(config.getSiteCode()))
        {
            calculateUs(product, config, rawVolume);
        }
        else
        {
            calculateUkOrDe(product, config, volume);
        }
    }

    private void calculateUkOrDe(EbayCompetitorProduct product,
            EbayCompetitorFormulaConfig config, BigDecimal volume)
    {
        BigDecimal sale = product.getSalePrice();
        BigDecimal exchange = product.getExchangeRate();
        BigDecimal target = product.getTargetProfitRate();
        BigDecimal chargeable = volume.max(product.getActualWeightKg());
        BigDecimal fixed = config.getFixedFee();
        BigDecimal handling = config.getWeightHandlingRate().multiply(chargeable);
        BigDecimal netSale = sale.multiply(config.getPlatformNetRate());
        BigDecimal denominator = config.getPlatformNetRate().subtract(target);

        BigDecimal seaFirstLegCny = config.getSeaFirstLegRate().multiply(volume);
        BigDecimal seaCostLocal = divide(product.getProductCostCny().add(seaFirstLegCny), exchange);
        BigDecimal seaProfit = divide(netSale.subtract(seaCostLocal).subtract(fixed).subtract(handling), sale);
        BigDecimal seaFloor = divide(seaCostLocal.add(fixed).add(handling), denominator);
        BigDecimal targetSea = exchange.multiply(netSale.subtract(fixed).subtract(handling)
                .subtract(target.multiply(sale))).subtract(seaFirstLegCny);

        product.setSeaProfitRate(rate(seaProfit));
        product.setSeaFloorPrice(money(seaFloor));
        product.setTargetProductCostSea(money(targetSea));

        BigDecimal railFirstLegCny = config.getRailFirstLegRate().multiply(chargeable);
        BigDecimal railCostLocal = divide(product.getProductCostCny().add(railFirstLegCny), exchange);
        BigDecimal railProfit = divide(netSale.subtract(railCostLocal).subtract(fixed).subtract(handling), sale);
        BigDecimal railFloor = divide(railCostLocal.add(fixed).add(handling), denominator);
        BigDecimal targetRail = exchange.multiply(netSale.subtract(fixed).subtract(handling)
                .subtract(target.multiply(sale))).subtract(railFirstLegCny);

        product.setRailProfitRate(rate(railProfit));
        product.setRailFloorPrice(money(railFloor));
        product.setTargetProductCostRail(money(targetRail));
    }

    private void calculateUs(EbayCompetitorProduct product,
            EbayCompetitorFormulaConfig config, BigDecimal volume)
    {
        BigDecimal sale = product.getSalePrice();
        BigDecimal exchange = product.getExchangeRate();
        BigDecimal target = product.getTargetProfitRate();
        BigDecimal actual = product.getActualWeightKg();
        BigDecimal thresholdWeight = volume.max(actual);
        BigDecimal deliveryWeight = volume.multiply(config.getChargeableVolumeFactor()).max(actual);
        boolean small = thresholdWeight.compareTo(config.getSmallWeightThreshold()) < 0;
        BigDecimal fixed = small ? config.getSmallFixedFee() : config.getLargeFixedFee();
        BigDecimal deliveryRate = small ? config.getSmallDeliveryRate() : config.getLargeDeliveryRate();
        BigDecimal delivery = deliveryRate.multiply(deliveryWeight);
        BigDecimal floorFirstLegCny = config.getSeaFirstLegRate().multiply(volume);
        BigDecimal profitFirstLegCny = configuredRate(config.getProfitFirstLegRate(),
                config.getSeaFirstLegRate()).multiply(volume);
        BigDecimal targetFirstLegCny = configuredRate(config.getTargetCostFirstLegRate(),
                config.getSeaFirstLegRate()).multiply(volume);
        BigDecimal floorCostLocal = divide(product.getProductCostCny().add(floorFirstLegCny), exchange);
        BigDecimal profitCostLocal = divide(product.getProductCostCny().add(profitFirstLegCny), exchange);
        BigDecimal netSale = sale.multiply(config.getPlatformNetRate());
        BigDecimal denominator = config.getPlatformNetRate().subtract(target);

        BigDecimal profit = divide(netSale.subtract(profitCostLocal).subtract(fixed).subtract(delivery), sale);
        BigDecimal floor = divide(floorCostLocal.add(fixed).add(delivery), denominator);
        BigDecimal targetCost = exchange.multiply(netSale.subtract(fixed).subtract(delivery)
                .subtract(target.multiply(sale))).subtract(targetFirstLegCny);

        product.setSeaProfitRate(rate(profit));
        product.setSeaFloorPrice(money(floor));
        product.setTargetProductCostSea(money(targetCost));
        product.setRailProfitRate(null);
        product.setRailFloorPrice(null);
        product.setTargetProductCostRail(null);
    }

    private static BigDecimal divide(BigDecimal left, BigDecimal right)
    {
        if (right == null || right.compareTo(BigDecimal.ZERO) == 0)
        {
            throw new ServiceException("计算参数不能为0");
        }
        return left.divide(right, INTERNAL_SCALE, RoundingMode.HALF_UP);
    }

    private static BigDecimal rate(BigDecimal value)
    {
        return value.setScale(6, RoundingMode.HALF_UP);
    }

    private static BigDecimal money(BigDecimal value)
    {
        return value.setScale(2, RoundingMode.HALF_UP);
    }

    private static BigDecimal dimension(BigDecimal value)
    {
        return value.setScale(2, RoundingMode.HALF_UP);
    }

    private static BigDecimal configuredRate(BigDecimal configured, BigDecimal fallback)
    {
        return configured == null ? fallback : configured;
    }
}
