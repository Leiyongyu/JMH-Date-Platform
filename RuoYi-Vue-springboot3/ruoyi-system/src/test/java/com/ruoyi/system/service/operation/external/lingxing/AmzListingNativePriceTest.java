package com.ruoyi.system.service.operation.external.lingxing;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.ruoyi.system.domain.operation.external.AmzProductListing;
import com.ruoyi.system.mapper.operation.external.AmzProductListingMapper;
import com.ruoyi.system.mapper.operation.external.ShopListMapper;
import java.math.BigDecimal;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class AmzListingNativePriceTest
{
    @Test
    void listingPriceAndOriginalCurrencyAreStoredTogether() throws Exception
    {
        var gateway=mock(LingxingGatewayService.class);
        var mapper=mock(AmzProductListingMapper.class);
        var shops=mock(ShopListMapper.class);
        when(shops.selectSidsByPlatform("10001",1)).thenReturn(List.of("1"));
        when(gateway.post(anyString(),anyMap())).thenReturn(Map.of("data",List.of(Map.of(
                "sid",1,"seller_sku","SKU","price","19.95","currency_code","GBP")),"total",1));
        new LingxingAmzListingSyncService(gateway,mapper,shops,new ObjectMapper()).syncAll();
        ArgumentCaptor<List<AmzProductListing>> rows=ArgumentCaptor.forClass(List.class);
        verify(mapper).batchInsert(rows.capture());
        assertEquals(new BigDecimal("19.95"),rows.getValue().get(0).getPrice());
        assertEquals("GBP",rows.getValue().get(0).getCurrencyCode());
    }
}
