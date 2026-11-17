package com.ruoyi.system.service.operation.external.lingxing;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.anyList;
import static org.mockito.Mockito.inOrder;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.ruoyi.system.domain.operation.external.AmzWarehouseInventoryDetail;
import com.ruoyi.system.mapper.operation.external.AmzWarehouseInventoryDetailMapper;
import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.InOrder;
import org.mockito.Mockito;

class AmzWarehouseInventoryReplaceServiceTest
{
    private AmzWarehouseInventoryDetailMapper mapper;
    private AmzWarehouseInventoryReplaceService service;

    @BeforeEach
    void setUp()
    {
        mapper = Mockito.mock(AmzWarehouseInventoryDetailMapper.class);
        service = new AmzWarehouseInventoryReplaceService(mapper);
    }

    @Test
    void shouldDeleteOnlyAfterRowsAreReadyAndInsertAllBatches()
    {
        List<AmzWarehouseInventoryDetail> rows = rows(1001);
        when(mapper.batchInsert(anyList()))
                .thenAnswer(invocation -> ((List<?>) invocation.getArgument(0)).size());

        assertThat(service.replaceAll(rows)).isEqualTo(1001);

        InOrder order = inOrder(mapper);
        order.verify(mapper).deleteAll();
        order.verify(mapper, times(2)).batchInsert(anyList());
    }

    @Test
    void shouldRejectEmptyReplacementBeforeDeletingExistingRows()
    {
        assertThatThrownBy(() -> service.replaceAll(List.of()))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("不能为空");

        verify(mapper, never()).deleteAll();
        verify(mapper, never()).batchInsert(anyList());
    }

    private static List<AmzWarehouseInventoryDetail> rows(int count)
    {
        List<AmzWarehouseInventoryDetail> rows = new ArrayList<>();
        for (int index = 0; index < count; index++)
        {
            AmzWarehouseInventoryDetail row = new AmzWarehouseInventoryDetail();
            row.setWid(18678);
            row.setSku("SKU-" + index);
            row.setProductValidNum(index);
            rows.add(row);
        }
        return rows;
    }
}
