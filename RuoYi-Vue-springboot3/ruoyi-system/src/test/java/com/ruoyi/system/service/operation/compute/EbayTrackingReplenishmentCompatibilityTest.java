package com.ruoyi.system.service.operation.compute;

import com.ruoyi.system.domain.operation.EbayReplenishmentSnapshot;
import com.ruoyi.system.mapper.operation.EbayReplenishmentSnapshotMapper;
import com.ruoyi.system.service.operation.impl.EbayReplenishmentSnapshotServiceImpl;
import java.util.List;
import org.apache.ibatis.builder.xml.XMLMapperBuilder;
import org.apache.ibatis.session.Configuration;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

class EbayTrackingReplenishmentCompatibilityTest
{
    @Test
    void emptyCalculationPreservesTrackingSnapshot()
    {
        var mapper = mock(EbayReplenishmentSnapshotMapper.class);
        var compute = mock(EbayReplenishmentComputeService.class);
        when(compute.compute()).thenReturn(List.of());
        assertEquals(0, new EbayReplenishmentSnapshotServiceImpl(mapper, compute).refreshSnapshot());
        verifyNoInteractions(mapper);
    }

    @Test
    void calculationPublishesTrackingSnapshotBeforeRemovingOldBatch()
    {
        var mapper = mock(EbayReplenishmentSnapshotMapper.class);
        var compute = mock(EbayReplenishmentComputeService.class);
        var rows = List.of(new EbayReplenishmentSnapshot());
        when(compute.compute()).thenReturn(rows);
        assertEquals(1, new EbayReplenishmentSnapshotServiceImpl(mapper, compute).refreshSnapshot());
        var order = inOrder(mapper);
        order.verify(mapper).batchInsertSnapshots(eq(rows), startsWith("EBAY_REPL-"));
        order.verify(mapper).activateBatch(startsWith("EBAY_REPL-"));
        order.verify(mapper).deleteNonCurrent();
    }

    @Test
    void trimmedMapperRetainsTrackingReadAndRefreshStatements() throws Exception
    {
        var config = new Configuration();
        String resource = "mapper/operation/EbayReplenishmentSnapshotMapper.xml";
        try (var input = getClass().getClassLoader().getResourceAsStream(resource))
        {
            assertNotNull(input);
            new XMLMapperBuilder(input, config, resource, config.getSqlFragments()).parse();
        }
        String prefix = EbayReplenishmentSnapshotMapper.class.getName() + ".";
        for (String name : List.of("selectEbayReplenishmentSnapshotList", "batchInsertSnapshots", "activateBatch", "deleteNonCurrent"))
            assertTrue(config.hasStatement(prefix + name), name);
        assertFalse(config.hasStatement(prefix + "search"));
        assertFalse(config.hasStatement(prefix + "selectDistinctValues"));
    }
}
