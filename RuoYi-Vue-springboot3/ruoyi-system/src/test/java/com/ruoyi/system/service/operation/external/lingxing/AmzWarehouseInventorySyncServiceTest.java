package com.ruoyi.system.service.operation.external.lingxing;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.anyList;
import static org.mockito.ArgumentMatchers.anyMap;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.ruoyi.system.domain.operation.external.AmzWarehouseInventoryDetail;
import java.math.BigDecimal;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

class AmzWarehouseInventorySyncServiceTest
{
    @Test
    void shouldMergeGatewayDuplicatesBeforeReplacement() throws Exception
    {
        LingxingGatewayService gateway = mock(LingxingGatewayService.class);
        AmzWarehouseInventoryReplaceService replaceService =
                mock(AmzWarehouseInventoryReplaceService.class);
        when(gateway.post(anyString(), anyMap())).thenAnswer(invocation -> {
            Map<String, Object> body = invocation.getArgument(1);
            if (!"18678".equals(String.valueOf(body.get("wid"))))
            {
                return Map.of("data", List.of(), "total", 0);
            }

            Map<String, Object> boundRow = new LinkedHashMap<>();
            boundRow.put("sku", "TYT-90249-0695");
            boundRow.put("seller_id", "12655");
            boundRow.put("product_valid_num", 0);
            boundRow.put("quantity_receive", 0);
            boundRow.put("product_lock_num", 1);
            boundRow.put("product_qc_num", 0);

            Map<String, Object> unboundRow = new LinkedHashMap<>();
            unboundRow.put("sku", " tyt-90249-0695 ");
            unboundRow.put("product_valid_num", 15);
            unboundRow.put("quantity_receive", 8);
            unboundRow.put("product_lock_num", 0);
            unboundRow.put("product_qc_num", 3);
            return Map.of("data", List.of(boundRow, unboundRow), "total", 2);
        });
        when(replaceService.replaceAll(anyList()))
                .thenAnswer(invocation -> ((List<?>) invocation.getArgument(0)).size());

        AmzWarehouseInventorySyncService service =
                new AmzWarehouseInventorySyncService(
                        gateway, new ObjectMapper(), replaceService);
        service.syncAll();

        @SuppressWarnings("unchecked")
        ArgumentCaptor<List<AmzWarehouseInventoryDetail>> captor =
                ArgumentCaptor.forClass(List.class);
        verify(replaceService).replaceAll(captor.capture());
        verify(gateway, times(5)).post(anyString(), anyMap());

        List<AmzWarehouseInventoryDetail> rows = captor.getValue();
        assertThat(rows).hasSize(1);
        AmzWarehouseInventoryDetail merged = rows.get(0);
        assertThat(merged.getWid()).isEqualTo(18678);
        assertThat(merged.getSellerId()).isEqualTo("12655");
        assertThat(merged.getProductValidNum()).isEqualTo(15);
        assertThat(merged.getQuantityReceive()).isEqualByComparingTo("8");
        assertThat(merged.getProductLockNum()).isEqualTo(1);
        assertThat(merged.getProductQcNum()).isEqualTo(3);
    }

    @Test
    void shouldNotReplaceExistingRowsWhenAnyGatewayCallFails() throws Exception
    {
        LingxingGatewayService gateway = mock(LingxingGatewayService.class);
        AmzWarehouseInventoryReplaceService replaceService =
                mock(AmzWarehouseInventoryReplaceService.class);
        when(gateway.post(anyString(), anyMap()))
                .thenThrow(new IllegalStateException("remote failed"));

        AmzWarehouseInventorySyncService service =
                new AmzWarehouseInventorySyncService(
                        gateway, new ObjectMapper(), replaceService);

        assertThatThrownBy(service::syncAll)
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("remote failed");
        verify(replaceService, never()).replaceAll(anyList());
    }

    @Test
    void shouldMergeDuplicateWarehouseSkuUsingMaximumInventory()
    {
        AmzWarehouseInventoryDetail current = inventory(
                "12655", "TYT-90249-0695", 0, "0", 2, 1);
        AmzWarehouseInventoryDetail incoming = inventory(
                null, "TYT-90249-0695", 15, "8", 1, 3);

        AmzWarehouseInventorySyncService.mergeInventory(current, incoming);

        assertThat(current.getSellerId()).isEqualTo("12655");
        assertThat(current.getProductValidNum()).isEqualTo(15);
        assertThat(current.getQuantityReceive()).isEqualByComparingTo("8");
        assertThat(current.getProductLockNum()).isEqualTo(2);
        assertThat(current.getProductQcNum()).isEqualTo(3);
    }

    @Test
    void shouldFillSellerIdWhenFirstDuplicateIsUnbound()
    {
        AmzWarehouseInventoryDetail current = inventory(
                null, "TYT-90249-0695", 15, null, null, null);
        AmzWarehouseInventoryDetail incoming = inventory(
                "12655", "TYT-90249-0695", 0, "0", 0, 0);

        AmzWarehouseInventorySyncService.mergeInventory(current, incoming);

        assertThat(current.getSellerId()).isEqualTo("12655");
        assertThat(current.getProductValidNum()).isEqualTo(15);
    }

    @Test
    void shouldUseDatabaseCompatibleCaseInsensitiveTrimmedKey()
    {
        assertThat(AmzWarehouseInventorySyncService.inventoryKey(
                18678, "  TYT-90249-0695  "))
                .isEqualTo(AmzWarehouseInventorySyncService.inventoryKey(
                        18678, "tyt-90249-0695"));
    }

    private static AmzWarehouseInventoryDetail inventory(
            String sellerId,
            String sku,
            Integer validNum,
            String quantityReceive,
            Integer lockNum,
            Integer qcNum)
    {
        AmzWarehouseInventoryDetail row = new AmzWarehouseInventoryDetail();
        row.setWid(18678);
        row.setSellerId(sellerId);
        row.setSku(sku);
        row.setProductValidNum(validNum);
        row.setQuantityReceive(
                quantityReceive == null ? null : new BigDecimal(quantityReceive));
        row.setProductLockNum(lockNum);
        row.setProductQcNum(qcNum);
        return row;
    }
}
