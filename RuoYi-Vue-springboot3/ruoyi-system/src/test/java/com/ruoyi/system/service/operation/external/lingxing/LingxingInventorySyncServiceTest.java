package com.ruoyi.system.service.operation.external.lingxing;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.ruoyi.system.domain.operation.external.WarehouseInventoryDetail;
import com.ruoyi.system.mapper.operation.external.WarehouseInventoryDetailMapper;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

class LingxingInventorySyncServiceTest
{
    @Test
    @SuppressWarnings("unchecked")
    void pendingQcQuantityIsStoredAndMissingStaysNull() throws Exception
    {
        LingxingGatewayService gateway = mock(LingxingGatewayService.class);
        WarehouseInventoryDetailMapper mapper = mock(WarehouseInventoryDetailMapper.class);
        LingxingProperties props = new LingxingProperties();
        props.setInventoryWids("18674");
        when(gateway.post(eq("erp/sc/routing/data/local_inventory/inventoryDetails"), any())).thenReturn(Map.of("data", List.of(
                Map.of("sku", "FRD-70327-0076", "product_valid_num", 11, "product_qc_num", 5, "quantity_receive", "20"),
                Map.of("sku", "BMW-30032-0018", "product_valid_num", 0))));
        new LingxingInventorySyncService(gateway, mapper, new ObjectMapper(), props).syncAll();
        ArgumentCaptor<List<WarehouseInventoryDetail>> captor = ArgumentCaptor.forClass(List.class);
        verify(mapper).batchInsert(captor.capture());
        List<WarehouseInventoryDetail> rows = captor.getValue();
        assertEquals("5", rows.get(0).getProductQcNum(), "待检待上架量按领星原值写入");
        assertEquals(11, rows.get(0).getProductValidNum());
        assertNull(rows.get(1).getProductQcNum(), "领星没返回时保持空，不当 0 件");
    }

    @Test
    void mapperWritesTheQcColumn() throws Exception
    {
        String xml = Files.readString(Path.of("src/main/resources/mapper/operation/external/WarehouseInventoryDetailMapper.xml"),
                StandardCharsets.UTF_8);
        String insert = xml.substring(xml.indexOf("<insert id=\"batchInsert\""));
        assertEquals(true, insert.contains("product_lock_num,product_qc_num,product_onway"), insert);
        assertEquals(true, insert.contains("#{e.productLockNum},#{e.productQcNum},#{e.productOnway}"), insert);
    }
}
