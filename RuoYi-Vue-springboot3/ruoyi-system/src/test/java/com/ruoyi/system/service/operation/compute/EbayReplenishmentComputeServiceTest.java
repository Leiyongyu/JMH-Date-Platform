package com.ruoyi.system.service.operation.compute;

import java.math.BigDecimal;
import java.util.stream.Stream;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;

import com.ruoyi.system.domain.operation.EbayReplenishmentSnapshot;

import static org.assertj.core.api.Assertions.assertThat;

class EbayReplenishmentComputeServiceTest
{
    @Test
    void shouldForecastNewProductFromSalesAndOutboundDays()
    {
        EbayReplenishmentSnapshot snapshot = snapshot(0, 0, 10, 20, 2);

        assertThat(EbayReplenishmentComputeService.calcMonthlySalesForecast(snapshot)).isEqualTo(15);
    }

    @Test
    void shouldReturnZeroForNewProductWithoutPositiveOutboundDays()
    {
        EbayReplenishmentSnapshot snapshot = snapshot(0, 0, 10, 0, 2);

        assertThat(EbayReplenishmentComputeService.calcMonthlySalesForecast(snapshot)).isZero();
    }

    @Test
    void shouldApplyRecentSalesWeightsForOldProduct()
    {
        EbayReplenishmentSnapshot snapshot = snapshot(14, 15, 30, 100, 1);

        assertThat(EbayReplenishmentComputeService.calcMonthlySalesForecast(snapshot)).isEqualTo(51);
    }

    @Test
    void shouldFallBackToThirtyDaySalesWhenNoRecentSalesExist()
    {
        EbayReplenishmentSnapshot snapshot = snapshot(0, 0, 12, null, null);

        assertThat(EbayReplenishmentComputeService.calcMonthlySalesForecast(snapshot)).isEqualTo(12);
    }

    @ParameterizedTest(name = "退货率={0}, ROI={1}, 动销率={2} => {3}")
    @MethodSource("returnLevelCases")
    void shouldClassifyReturnLevelByBusinessBoundaries(
            String returnRate, String roi, String turnover, String expected)
    {
        assertThat(EbayReplenishmentComputeService.calcReturnLevel(
                decimal(returnRate), decimal(roi), decimal(turnover)))
                .isEqualTo(expected);
    }

    private static Stream<Arguments> returnLevelCases()
    {
        return Stream.of(
                Arguments.of("0.0601", "30", "30", "问题产品"),
                Arguments.of("0.0300", "17.99", "30", "问题产品"),
                Arguments.of("0.0299", "11.99", "12", "问题产品"),
                Arguments.of("0.0300", "18", "30", "长尾产品"),
                Arguments.of("0.0299", "11.99", "12.01", "长尾产品"),
                Arguments.of("0.0299", "12", "11.99", "长尾产品"),
                Arguments.of("0.0299", "22", "14.99", "长尾产品"),
                Arguments.of("0.0299", "12", "12", "主力产品"),
                Arguments.of("0.0299", "22", "15", "明星产品"));
    }

    private static EbayReplenishmentSnapshot snapshot(
            Integer sales7d, Integer sales15d, Integer sales30d,
            Integer outboundDays, Integer productNature)
    {
        EbayReplenishmentSnapshot snapshot = new EbayReplenishmentSnapshot();
        snapshot.setSales7d(sales7d);
        snapshot.setSales15d(sales15d);
        snapshot.setSales30d(sales30d);
        snapshot.setOutboundDays(outboundDays);
        snapshot.setProductNature(productNature);
        return snapshot;
    }

    private static BigDecimal decimal(String value)
    {
        return new BigDecimal(value);
    }
}
