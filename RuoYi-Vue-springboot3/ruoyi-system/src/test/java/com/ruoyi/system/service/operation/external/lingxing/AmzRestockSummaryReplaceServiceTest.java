package com.ruoyi.system.service.operation.external.lingxing;

import com.ruoyi.system.domain.operation.external.AmzRestockSummary;
import com.ruoyi.system.mapper.operation.external.AmzRestockSummaryMapper;
import java.util.List;
import java.util.stream.IntStream;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class AmzRestockSummaryReplaceServiceTest
{
    @Test
    void emptyAndCancelledResultsCannotDeletePreviousData()
    {
        var mapper=mock(AmzRestockSummaryMapper.class);
        var service=new AmzRestockSummaryReplaceService(mapper);
        assertThrows(IllegalArgumentException.class,()->service.replaceAll(List.of()));
        Thread.currentThread().interrupt();
        try { assertThrows(IllegalStateException.class,()->service.replaceAll(List.of(new AmzRestockSummary()))); }
        finally { Thread.interrupted(); }
        verifyNoInteractions(mapper);
    }

    @Test
    void allInsertBatchesAreCountedAndPartialWritesAreRejected()
    {
        var mapper=mock(AmzRestockSummaryMapper.class);
        var service=new AmzRestockSummaryReplaceService(mapper);
        var rows=IntStream.range(0,501).mapToObj(i->new AmzRestockSummary()).toList();
        when(mapper.batchInsert(anyList())).thenAnswer(i->((List<?>)i.getArgument(0)).size());
        assertEquals(501,service.replaceAll(rows));
        verify(mapper,times(2)).batchInsert(anyList());
        when(mapper.batchInsert(anyList())).thenReturn(0);
        assertThrows(IllegalStateException.class,()->service.replaceAll(rows));
    }
}
