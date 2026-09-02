package com.ruoyi.system.service.operation.customs;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class CustomsProductServiceTest
{
    private static final String QUANTITIES = "20+66+30+50+50+30";
    private static final String PRICES = "1375/1265/1210/1089";

    @Test
    void shouldUseLatestPricedBatchWhenRemainingStockFitsIt()
    {
        assertThat(calculate("30")).isEqualByComparingTo("1089");
    }

    @Test
    void shouldWalkBackwardAcrossFifoBatchBoundaries()
    {
        assertThat(calculate("30.01")).isEqualByComparingTo("1210");
        assertThat(calculate("80.01")).isEqualByComparingTo("1265");
        assertThat(calculate("130.01")).isEqualByComparingTo("1375");
    }

    @Test
    void shouldUseEarliestAvailablePriceWhenRemainingStockExceedsPricedBatches()
    {
        assertThat(calculate("999")).isEqualByComparingTo("1375");
    }

    @Test
    void shouldRightAlignPricesWhenHistoricalQuantityBatchesHaveNoPrice()
    {
        BigDecimal price = CustomsProductService.calculateBatchUnitPrice(
                "10+20+30", "200/100", new BigDecimal("30.01"));

        assertThat(price).isEqualByComparingTo("200");
    }

    @Test
    void shouldRejectMissingNonPositiveOrMalformedInputs()
    {
        assertThat(CustomsProductService.calculateBatchUnitPrice(null, PRICES, BigDecimal.ONE)).isNull();
        assertThat(CustomsProductService.calculateBatchUnitPrice(QUANTITIES, "", BigDecimal.ONE)).isNull();
        assertThat(CustomsProductService.calculateBatchUnitPrice(QUANTITIES, PRICES, BigDecimal.ZERO)).isNull();
        assertThat(CustomsProductService.calculateBatchUnitPrice("20+bad", PRICES, BigDecimal.ONE)).isNull();
        assertThat(CustomsProductService.calculateBatchUnitPrice(QUANTITIES, "100/bad", BigDecimal.ONE)).isNull();
    }

    private static BigDecimal calculate(String remaining)
    {
        return CustomsProductService.calculateBatchUnitPrice(
                QUANTITIES, PRICES, new BigDecimal(remaining));
    }
}
