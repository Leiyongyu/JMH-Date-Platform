package com.ruoyi.system.service.operation.external.goodcang;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyList;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.inOrder;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.verifyNoMoreInteractions;
import static org.mockito.Mockito.when;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.ruoyi.system.mapper.operation.external.GoodcangInventoryAgeSnapshotMapper;
import com.ruoyi.system.service.operation.sync.OperationSyncResult;
import java.time.YearMonth;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.mockito.ArgumentCaptor;
import org.mockito.InOrder;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.SimpleTransactionStatus;

class GoodcangInventoryAgeSyncServiceTest
{
    private GoodcangClient client;
    private GoodcangInventoryAgeSnapshotMapper mapper;
    private PlatformTransactionManager transactionManager;
    private SimpleTransactionStatus transaction;
    private GoodcangInventoryAgeSyncService service;

    @BeforeEach
    void setUp()
    {
        client = mock(GoodcangClient.class);
        mapper = mock(GoodcangInventoryAgeSnapshotMapper.class);
        transactionManager = mock(PlatformTransactionManager.class);
        transaction = new SimpleTransactionStatus();
        when(transactionManager.getTransaction(any(TransactionDefinition.class)))
                .thenReturn(transaction);
        service = new GoodcangInventoryAgeSyncService(
                client, mapper, new ObjectMapper(), transactionManager);
    }

    @ParameterizedTest
    @ValueSource(booleans = {true, false})
    void fetchesAllPagesBeforeReplacingOnlyRequestedSnapshot(boolean latest)
            throws Exception
    {
        mockFourPages();
        String currentMonth = YearMonth.now().toString();

        OperationSyncResult result = sync(latest);

        @SuppressWarnings("unchecked")
        ArgumentCaptor<List<Map<String, Object>>> batches =
                ArgumentCaptor.forClass(List.class);
        InOrder order = inOrder(client, mapper, transactionManager);
        for (int page = 1; page <= 4; page++)
            order.verify(client).getInventoryAgeList(page, 200);
        order.verify(transactionManager)
                .getTransaction(any(TransactionDefinition.class));
        if (latest)
        {
            order.verify(mapper).deleteLatest();
            order.verify(mapper, times(2)).batchInsertLatest(batches.capture());
            verify(mapper, never()).deleteBySnapshotMonth(anyString());
            verify(mapper, never()).batchInsert(anyList());
        }
        else
        {
            order.verify(mapper).deleteBySnapshotMonth(currentMonth);
            order.verify(mapper, times(2)).batchInsert(batches.capture());
            verify(mapper, never()).deleteLatest();
            verify(mapper, never()).batchInsertLatest(anyList());
        }
        order.verify(transactionManager).commit(transaction);
        verify(transactionManager, never()).rollback(any());
        verifyNoMoreInteractions(client, mapper, transactionManager);

        assertThat(batches.getAllValues()).extracting(List::size)
                .containsExactly(500, 101);
        List<Map<String, Object>> rows = new ArrayList<>();
        batches.getAllValues().forEach(rows::addAll);
        assertThat(rows).hasSize(601);
        assertThat(rows).extracting(row -> row.get("snapshotMonth"))
                .containsOnly(currentMonth);
        assertThat(rows).extracting(row -> row.get("syncBatchId"))
                .containsOnly(result.getDetails().get("sync_batch_id"));
        assertThat(rows).extracting(row -> row.get("pulledAt"))
                .containsOnly(rows.get(0).get("pulledAt"));
        assertThat(rows.get(0)).containsEntry("sourcePage", 1)
                .containsEntry("sourceRowNo", 1)
                .containsEntry("warehouseCode", "USWE")
                .containsEntry("productSku", "GC-SKU-1")
                .containsEntry("ibaQuantity", 3L)
                .containsEntry("warehouseAge", 91);
        assertThat(rows.get(600)).containsEntry("sourcePage", 4)
                .containsEntry("sourceRowNo", 1)
                .containsEntry("productSku", "GC-SKU-601");
        assertThat(rows.get(0).get("rawJson").toString())
                .contains("\"warehouse_age\":91");
        assertThat(result.getStatus()).isEqualTo(OperationSyncResult.STATUS_SUCCESS);
        assertThat(result.getSyncType()).isEqualTo(latest
                ? "goodcang_inventory_age_latest" : "goodcang_inventory_age_monthly");
        assertThat(result.getSyncName()).isEqualTo(latest
                ? "谷仓-eBay库存库龄每周刷新" : "谷仓-eBay库存库龄月快照");
        assertThat(result.getDetails()).containsEntry("stored_rows", 601)
                .containsEntry("api_total", 601L)
                .containsEntry("snapshot_month", currentMonth);
    }

    @ParameterizedTest
    @ValueSource(booleans = {true, false})
    void rejectsEmptyResponseWithoutStartingReplacement(boolean latest)
            throws Exception
    {
        when(client.getInventoryAgeList(1, 200)).thenReturn(page(0, 1, 0));

        assertThatThrownBy(() -> sync(latest))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("返回0条")
                .hasMessageContaining(latest ? "最新快照" : "当月快照");

        verifyNoInteractions(mapper, transactionManager);
    }

    @ParameterizedTest
    @ValueSource(booleans = {true, false})
    void rejectsIncompletePaginationBeforeDeletingAnySnapshot(boolean latest)
            throws Exception
    {
        when(client.getInventoryAgeList(1, 200)).thenReturn(page(401, 1, 200));
        when(client.getInventoryAgeList(2, 200)).thenReturn(page(401, 201, 1));

        assertThatThrownBy(() -> sync(latest))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("分页不完整")
                .hasMessageContaining("应返回401条，实际201条");

        verifyNoInteractions(mapper, transactionManager);
    }

    @ParameterizedTest
    @ValueSource(booleans = {true, false})
    void leavesSnapshotsUntouchedWhenLaterPageFails(boolean latest)
            throws Exception
    {
        when(client.getInventoryAgeList(1, 200)).thenReturn(page(401, 1, 200));
        when(client.getInventoryAgeList(2, 200))
                .thenThrow(new IllegalStateException("remote failed"));

        assertThatThrownBy(() -> sync(latest)).hasMessage("remote failed");

        verifyNoInteractions(mapper, transactionManager);
    }

    @ParameterizedTest
    @ValueSource(booleans = {true, false})
    void rejectsApiFailureWithoutReplacingSnapshot(boolean latest)
            throws Exception
    {
        when(client.getInventoryAgeList(1, 200))
                .thenReturn(Map.of("code", 1, "message", "failed"));

        assertThatThrownBy(() -> sync(latest))
                .hasMessageContaining("谷仓库龄接口失败: code=1");

        verifyNoInteractions(mapper, transactionManager);
    }

    @ParameterizedTest
    @ValueSource(booleans = {true, false})
    void rejectsMalformedDataWithoutReplacingSnapshot(boolean latest)
            throws Exception
    {
        when(client.getInventoryAgeList(1, 200))
                .thenReturn(Map.of("code", 0, "data", List.of()));

        assertThatThrownBy(() -> sync(latest))
                .hasMessageContaining("data不是对象");

        verifyNoInteractions(mapper, transactionManager);
    }

    @ParameterizedTest
    @ValueSource(booleans = {true, false})
    void rollsBackDeletionAndEarlierBatchWhenLaterInsertFails(boolean latest)
            throws Exception
    {
        mockFourPages();
        if (latest)
            when(mapper.batchInsertLatest(anyList())).thenReturn(500)
                    .thenThrow(new IllegalStateException("insert failed"));
        else
            when(mapper.batchInsert(anyList())).thenReturn(500)
                    .thenThrow(new IllegalStateException("insert failed"));

        assertThatThrownBy(() -> sync(latest)).hasMessage("insert failed");

        InOrder order = inOrder(mapper, transactionManager);
        order.verify(transactionManager)
                .getTransaction(any(TransactionDefinition.class));
        if (latest)
        {
            order.verify(mapper).deleteLatest();
            order.verify(mapper, times(2)).batchInsertLatest(anyList());
            verify(mapper, never()).deleteBySnapshotMonth(anyString());
            verify(mapper, never()).batchInsert(anyList());
        }
        else
        {
            order.verify(mapper).deleteBySnapshotMonth(anyString());
            order.verify(mapper, times(2)).batchInsert(anyList());
            verify(mapper, never()).deleteLatest();
            verify(mapper, never()).batchInsertLatest(anyList());
        }
        order.verify(transactionManager).rollback(transaction);
        verify(transactionManager, never()).commit(any());
        verifyNoMoreInteractions(mapper, transactionManager);
    }

    private OperationSyncResult sync(boolean latest) throws Exception
    {
        return latest ? service.syncLatest() : service.syncCurrentMonth();
    }

    private void mockFourPages() throws Exception
    {
        for (int page = 1; page <= 4; page++)
            when(client.getInventoryAgeList(page, 200))
                    .thenReturn(page(601, (page - 1) * 200 + 1,
                            page == 4 ? 1 : 200));
    }

    private Map<String, Object> page(int total, int start, int count)
    {
        List<Map<String, Object>> rows = new ArrayList<>();
        for (int index = start; index < start + count; index++)
            rows.add(Map.of("warehouse_code", "USWE",
                    "product_sku", "GC-SKU-" + index,
                    "iba_quantity", 3, "warehouse_age", 91));
        return Map.of("code", 0, "message", "Success",
                "data", Map.of("total", total, "list", rows));
    }
}
