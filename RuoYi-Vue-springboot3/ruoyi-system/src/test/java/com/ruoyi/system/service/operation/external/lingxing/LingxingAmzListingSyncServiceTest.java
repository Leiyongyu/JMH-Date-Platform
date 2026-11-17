package com.ruoyi.system.service.operation.external.lingxing;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.ruoyi.system.domain.operation.external.AmzProductListing;
import com.ruoyi.system.mapper.operation.external.AmzProductListingMapper;
import com.ruoyi.system.mapper.operation.external.ShopListMapper;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.anyMap;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.*;

class LingxingAmzListingSyncServiceTest
{
    private static final String API = "erp/sc/data/mws/listing";

    @Test
    @SuppressWarnings({"unchecked", "rawtypes"})
    void preservesLegacyPairingAndDeletionFilters() throws Exception
    {
        LingxingGatewayService gateway = mock(LingxingGatewayService.class);
        AmzProductListingMapper mapper = mock(AmzProductListingMapper.class);
        ShopListMapper shops = mock(ShopListMapper.class);
        when(shops.selectSidsByPlatform("10001", 1)).thenReturn(List.of("12645", "12646"));
        when(gateway.post(eq(API), anyMap())).thenReturn(Map.of("code", 0, "total", 2,
                "data", List.of(
                        Map.of("sid", 12645, "seller_sku", "YCL-TEST-1", "status", 1),
                        Map.of("sid", 12646, "seller_sku", "YCL-TEST-2", "status", 0))));

        new LingxingAmzListingSyncService(gateway, mapper, shops, new ObjectMapper()).syncAll();

        ArgumentCaptor<Map<String, Object>> request = ArgumentCaptor.forClass((Class) Map.class);
        verify(gateway).post(eq(API), request.capture());
        assertThat(request.getValue()).containsExactlyInAnyOrderEntriesOf(
                Map.of("sid", "12645,12646", "is_pair", 1, "is_delete", 0, "offset", 0, "length", 1000));
        ArgumentCaptor<List<AmzProductListing>> inserted = ArgumentCaptor.forClass((Class) List.class);
        verify(mapper).batchInsert(inserted.capture());
        assertThat(inserted.getValue()).hasSize(2);
        assertThat(inserted.getValue().get(0).getLocalSku()).isNull();
        assertThat(inserted.getValue().get(1).getStatus()).isEqualTo(0);
    }

    @Test
    @SuppressWarnings({"unchecked", "rawtypes"})
    void continuesBeyondFirstThousandWithSameFilters() throws Exception
    {
        LingxingGatewayService gateway = mock(LingxingGatewayService.class);
        AmzProductListingMapper mapper = mock(AmzProductListingMapper.class);
        ShopListMapper shops = mock(ShopListMapper.class);
        when(shops.selectSidsByPlatform("10001", 1)).thenReturn(List.of("12645"));
        List<Map<String, Object>> firstPage = new ArrayList<>();
        for (int i = 0; i < 1000; i++)
            firstPage.add(Map.of("sid", 12645, "seller_sku", "YCL-" + i, "status", 1));
        when(gateway.post(eq(API), anyMap())).thenReturn(
                Map.of("code", 0, "total", 1001, "data", firstPage),
                Map.of("code", 0, "total", 1001, "data",
                        List.of(Map.of("sid", 12645, "seller_sku", "YCL-1000", "status", 1))));

        new LingxingAmzListingSyncService(gateway, mapper, shops, new ObjectMapper()).syncAll();

        ArgumentCaptor<Map<String, Object>> requests = ArgumentCaptor.forClass((Class) Map.class);
        verify(gateway, times(2)).post(eq(API), requests.capture());
        assertThat(requests.getAllValues()).containsExactly(
                Map.of("sid", "12645", "is_pair", 1, "is_delete", 0, "offset", 0, "length", 1000),
                Map.of("sid", "12645", "is_pair", 1, "is_delete", 0, "offset", 1000, "length", 1000));
        ArgumentCaptor<List<AmzProductListing>> inserted = ArgumentCaptor.forClass((Class) List.class);
        verify(mapper, times(2)).batchInsert(inserted.capture());
        assertThat(inserted.getAllValues().get(0)).hasSize(1000);
        assertThat(inserted.getAllValues().get(1)).hasSize(1);
    }
}
