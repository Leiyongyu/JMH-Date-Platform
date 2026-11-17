package com.ruoyi.system.service.operation;

import com.ruoyi.common.exception.ServiceException;
import com.ruoyi.system.domain.operation.AmzMixedSalesQuery;
import com.ruoyi.system.mapper.operation.AmzMixedSalesMapper;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class AmzMixedSalesServiceTest
{
    @Test
    void pagesAreBoundedAndSortingIsWhitelisted()
    {
        var mapper = mock(AmzMixedSalesMapper.class);
        when(mapper.selectProducts(any())).thenReturn(List.of(Map.of("sku", "FRD-70327-0076")));
        when(mapper.countProducts(any())).thenReturn(1L);
        var service = new AmzMixedSalesService(mapper);
        var q = new AmzMixedSalesQuery();
        q.setSku(" frd-70327-0076 "); q.setPageNum(-1); q.setPageSize(999);
        q.setSortField("fba_stock;DROP TABLE x"); q.setSortOrder("ascending");
        var result = service.list(q);
        assertEquals("FRD-70327-0076", q.getSku());
        assertEquals("fbaTotalInventory", q.getSortField());
        assertEquals("asc", q.getSortOrder());
        assertEquals(1, q.getPageNum()); assertEquals(200, q.getPageSize());
        assertEquals(0L, q.getOffset()); assertEquals(1L, result.get("total"));
    }

    @Test
    void detailsRequireSkuAndPositiveStoreId()
    {
        var mapper = mock(AmzMixedSalesMapper.class);
        var service = new AmzMixedSalesService(mapper);
        var q = new AmzMixedSalesQuery();
        assertThrows(ServiceException.class, () -> service.details(q));
        q.setSku("BMW-1-2"); q.setSid(-1);
        assertThrows(ServiceException.class, () -> service.details(q));
        verifyNoInteractions(mapper);
    }
}
