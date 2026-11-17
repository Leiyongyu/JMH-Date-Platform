package com.ruoyi.system.service.procurement;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.ruoyi.common.core.redis.RedisCache;
import com.ruoyi.common.exception.ServiceException;
import com.ruoyi.system.mapper.procurement.PendingPurchaseStatusMapper;
import com.ruoyi.system.service.operation.IOperationSyncLogService;
import com.ruoyi.system.service.operation.external.lingxing.LingxingGatewayService;
import com.ruoyi.system.service.operation.sync.OperationSyncContext;
import com.ruoyi.system.service.operation.sync.OperationSyncResult;
import java.io.InputStream;
import java.time.LocalDate;
import java.util.*;
import java.util.function.Consumer;
import org.apache.ibatis.builder.xml.XMLMapperBuilder;
import org.apache.ibatis.session.Configuration;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.transaction.TransactionStatus;
import org.springframework.transaction.support.SimpleTransactionStatus;
import org.springframework.transaction.support.TransactionTemplate;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

class PendingPurchaseStatusServiceTest
{
    private final PendingPurchaseStatusMapper mapper = mock(PendingPurchaseStatusMapper.class);
    private final LingxingGatewayService gateway = mock(LingxingGatewayService.class);
    private final RedisCache redis = mock(RedisCache.class);
    private final IOperationSyncLogService logs = mock(IOperationSyncLogService.class);
    private final TransactionTemplate tx = mock(TransactionTemplate.class);
    private final LocalDate day = LocalDate.of(2026, 10, 29);
    private PendingPurchaseStatusService service;

    @BeforeEach
    void setup()
    {
        service = new PendingPurchaseStatusService(mapper, gateway, new ObjectMapper(), tx, redis, logs);
        when(mapper.selectSkus()).thenReturn(List.of("FRD-70327-0076"));
        when(mapper.selectWarehouses()).thenReturn(List.of(Map.of("wid", 19578, "name", "CTUebay-1组中转仓")));
        when(mapper.start()).thenReturn(1);
        when(mapper.publish(any(), any(), anyInt())).thenReturn(1);
        when(redis.tryLock(anyString(), anyLong())).thenReturn(true);
        doAnswer(inv -> {
            Consumer<TransactionStatus> callback = inv.getArgument(0);
            callback.accept(new SimpleTransactionStatus());
            return null;
        }).when(tx).executeWithoutResult(any());
    }

    private Map<String, Object> item(int id, String wid, String sku)
    { return new HashMap<>(Map.of("id", id, "wid", wid, "sku", sku, "quantity_real", 8, "quantity_entry", 3, "quantity_receive", 5)); }

    private Map<String, Object> order(String sn, List<Map<String, Object>> items)
    {
        return new HashMap<>(Map.of("order_sn", sn, "create_time", day+" 09:00:00", "wid", "18674",
            "ware_house_name", "CTUeBay-DE中转仓", "status", 2, "status_shipped", 2, "pay_status", 3, "item_list", items));
    }
    private Map<String, Object> response(List<Map<String, Object>> orders) { return Map.of("code", 0, "data", orders); }

    @Test
    void keepsEveryMatchingItemAndExcludesAmzDeletedAndOtherSkus() throws Exception
    {
        Map<String, Object> deleted = item(5, "18674", "FRD-70327-0076"); deleted.put("is_delete", 1);
        var order = order("PO1", List.of(item(1,"18674","OTHER"), item(2,"18675","frd-70327-0076"),
            item(3,"18674","FRD-70327-0076"), item(4,"18677","FRD-70327-0076"), deleted));
        when(gateway.post(anyString(), anyMap())).thenReturn(response(List.of(order)));
        var rows = service.collect(day, day, Long.MAX_VALUE);
        assertEquals(2, rows.size());
        assertEquals("UK", rows.get(0).get("site"));
        assertEquals("DE", rows.get(1).get("site"));
        assertEquals("部分到货", rows.get(0).get("arrivalStatus"));
        assertEquals("已付款", rows.get(0).get("payStatus"));
        assertEquals("FRD-70327-0076", rows.get(0).get("sku"));
    }

    @Test
    void groupWarehouseDoesNotBorrowHeaderSiteAndMissingItemWarehouseFallsBack() throws Exception
    {
        when(gateway.post(anyString(), anyMap())).thenReturn(response(List.of(order("PO1", List.of(
            item(1,"19578","FRD-70327-0076"), item(2,"","FRD-70327-0076"))))));
        var rows = service.collect(day, day, Long.MAX_VALUE);
        assertEquals("UNKNOWN", rows.get(0).get("site"));
        assertEquals("DE", rows.get(1).get("site"));
        assertEquals("CTUebay-1组中转仓", rows.get(0).get("warehouseName"));
        assertNull(PendingPurchaseStatusService.warehouseSite("999", "AMZ-US2-MJ中转仓"));
        assertEquals("UK", PendingPurchaseStatusService.warehouseSite("999", "CTUebay-UK中转仓"));
    }

    @Test
    void multipleOrdersForOneSkuRemainSeparateAndUnknownStatusIsVisible() throws Exception
    {
        var first = order("PO1", List.of(item(1,"18674","FRD-70327-0076"))); first.put("pay_status", 99);
        when(gateway.post(anyString(), anyMap())).thenReturn(response(List.of(first,
            order("PO2", List.of(item(2,"18674","FRD-70327-0076"))))));
        var rows = service.collect(day, day, Long.MAX_VALUE);
        assertEquals(2, rows.size());
        assertEquals("未知状态(99)", rows.get(0).get("payStatus"));
    }

    private List<Map<String, Object>> fullPage()
    {
        List<Map<String, Object>> rows = new ArrayList<>();
        for (int i=0; i<500; i++) rows.add(order("PO"+i, List.of(item(i,"18674","OTHER"))));
        return rows;
    }

    @Test
    void missingTotalStillReadsFollowingPage() throws Exception
    {
        when(gateway.post(anyString(), anyMap())).thenReturn(response(fullPage()), response(List.of(
            order("PO-last", List.of(item(501,"18674","FRD-70327-0076"))))));
        assertEquals(1, service.collect(day, day, Long.MAX_VALUE).size());
        verify(gateway).post(anyString(), argThat(body -> Integer.valueOf(500).equals(body.get("offset"))));
    }

    @Test
    void rejectsRepeatedPagesAndPrematureEnd() throws Exception
    {
        var page = response(fullPage());
        when(gateway.post(anyString(), anyMap())).thenReturn(page, page);
        assertThrows(IllegalStateException.class, () -> service.collect(day, day, Long.MAX_VALUE));
        when(gateway.post(anyString(), anyMap())).thenReturn(Map.of("code",0,"total",10,"data",List.of()));
        assertThrows(IllegalStateException.class, () -> service.collect(day, day, Long.MAX_VALUE));
    }

    @Test
    void rejectsMalformedOrOutOfRangeSourceData() throws Exception
    {
        when(gateway.post(anyString(), anyMap())).thenReturn(Map.of("code",0,"data", Map.of()));
        assertThrows(IllegalStateException.class, () -> service.collect(day, day, Long.MAX_VALUE));
        var old = order("PO1", List.of()); old.put("create_time", "2026-01-01 00:00:00");
        when(gateway.post(anyString(), anyMap())).thenReturn(response(List.of(old)));
        assertThrows(IllegalStateException.class, () -> service.collect(day, day, Long.MAX_VALUE));
    }

    @Test
    void failureBeforePublishNeverClearsSnapshotAndReleasesLock() throws Exception
    {
        when(gateway.post(anyString(), anyMap())).thenReturn(Map.of("code", 100));
        assertThrows(ServiceException.class, () -> service.sync("MANUAL", "test"));
        verify(mapper, never()).clearSnapshot();
        verify(mapper).fail();
        verify(redis).unlock("lock:sync:lingxing:ebay");
        verify(tx, never()).executeWithoutResult(any());
    }

    @Test
    void zeroMatchesAreSuccessfulAndSixMonthRangeIsPublishedAtomically()
    {
        when(mapper.selectSkus()).thenReturn(List.of());
        service.sync("MANUAL", "test");
        var order = inOrder(mapper);
        order.verify(mapper).clearSnapshot();
        order.verify(mapper).publish(eq(LocalDate.now().minusMonths(6)), eq(LocalDate.now()), eq(0));
        assertEquals(OperationSyncResult.STATUS_SUCCESS, OperationSyncContext.get().getStatus());
        verify(mapper, never()).fail();
        verify(tx).executeWithoutResult(any());
    }

    @Test
    void busyGroupLockDoesNotChangeSnapshotOrCallUpstream() throws Exception
    {
        when(redis.tryLock(anyString(), anyLong())).thenReturn(false);
        service.sync("JOB", "SYSTEM");
        verifyNoInteractions(mapper, gateway, tx);
        assertEquals(OperationSyncResult.STATUS_SKIPPED, OperationSyncContext.get().getStatus());
    }

    @Test
    void summaryValidatesIdsAndNeverAcceptsArbitrarySku()
    {
        assertThrows(ServiceException.class, () -> service.summary(List.of()));
        assertThrows(ServiceException.class, () -> service.summary(List.of(-1L)));
        service.summary(List.of(1L,1L,2L));
        verify(mapper).selectSummary(List.of(1L,2L));
    }

    @Test
    void mapperParsesAndRestrictsBothQueriesToExistingPendingIds() throws Exception
    {
        Configuration config = new Configuration();
        String resource = "mapper/procurement/PendingPurchaseStatusMapper.xml";
        try (InputStream input = getClass().getClassLoader().getResourceAsStream(resource))
        { new XMLMapperBuilder(input, config, resource, config.getSqlFragments()).parse(); }
        String ns = PendingPurchaseStatusMapper.class.getName()+".";
        String summary = config.getMappedStatement(ns+"selectSummary").getBoundSql(Map.of("ids", List.of(1L,2L))).getSql();
        String details = config.getMappedStatement(ns+"selectDetails").getBoundSql(Map.of("id",1L)).getSql();
        assertTrue(summary.contains("p.id IN"));
        assertTrue(summary.contains("CASE WHEN s.site!='UNKNOWN'"));
        assertTrue(details.contains("p.id=?"));
        assertTrue(details.contains("s.sku=UPPER(TRIM(p.sku))"));
        assertTrue(details.contains("INTERVAL 6 MONTH"));
    }
}
