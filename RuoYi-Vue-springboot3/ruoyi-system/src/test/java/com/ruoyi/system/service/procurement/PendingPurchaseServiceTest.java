package com.ruoyi.system.service.procurement;

import com.ruoyi.common.exception.ServiceException;
import com.ruoyi.system.domain.procurement.PendingPurchase;
import com.ruoyi.system.mapper.procurement.PendingPurchaseMapper;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.transaction.annotation.Transactional;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

/** Offline only: the mapper is mocked, no procurement rows are deleted. */
class PendingPurchaseServiceTest
{
    @Test
    void deletesOnlyAfterAllSelectedRowsAreLocked()
    {
        PendingPurchaseMapper mapper = mock(PendingPurchaseMapper.class);
        List<Long> ids = List.of(1L, 2L);
        when(mapper.selectDeletableByIdsForUpdate(ids)).thenReturn(List.of(new PendingPurchase(), new PendingPurchase()));
        when(mapper.deletePendingByIds(ids)).thenReturn(2);
        new PendingPurchaseService(mapper).deletePending(ids);
        var order = inOrder(mapper);
        order.verify(mapper).selectDeletableByIdsForUpdate(ids);
        order.verify(mapper).deletePendingByIds(ids);
    }

    @Test
    void missingRowRejectsEntireSelection()
    {
        PendingPurchaseMapper mapper = mock(PendingPurchaseMapper.class);
        when(mapper.selectDeletableByIdsForUpdate(List.of(1L, 2L))).thenReturn(List.of(new PendingPurchase()));
        assertThrows(ServiceException.class, () -> new PendingPurchaseService(mapper).deletePending(List.of(1L, 2L)));
        verify(mapper, never()).deletePendingByIds(anyList());
    }

    @Test
    void invalidIdsNeverReachMapper()
    {
        PendingPurchaseMapper mapper = mock(PendingPurchaseMapper.class);
        PendingPurchaseService service = new PendingPurchaseService(mapper);
        assertThrows(ServiceException.class, () -> service.deletePending(null));
        assertThrows(ServiceException.class, () -> service.deletePending(List.of()));
        assertThrows(ServiceException.class, () -> service.deletePending(List.of(-1L)));
        verifyNoInteractions(mapper);
    }

    @Test
    void purchasedAndPendingRowsCanBeDeletedTogether()
    {
        PendingPurchaseMapper mapper = mock(PendingPurchaseMapper.class);
        PendingPurchase pending = new PendingPurchase();
        pending.setStatus("0");
        PendingPurchase purchased = new PendingPurchase();
        purchased.setStatus("1");
        List<Long> ids = List.of(1L, 2L);
        when(mapper.selectDeletableByIdsForUpdate(ids)).thenReturn(List.of(pending, purchased));
        when(mapper.deletePendingByIds(ids)).thenReturn(2);
        new PendingPurchaseService(mapper).deletePending(ids);
        verify(mapper).deletePendingByIds(ids);
        verify(mapper, never()).selectPendingByIdsForUpdate(anyList());
    }

    @Test
    void exportStillRejectsPurchasedRows() throws Exception
    {
        PendingPurchaseMapper mapper = mock(PendingPurchaseMapper.class);
        when(mapper.selectPendingByIdsForUpdate(List.of(2L))).thenReturn(List.of());
        assertThrows(ServiceException.class, () ->
                new PendingPurchaseService(mapper).exportAndMarkPurchased(List.of(2L), "test", null));
        verify(mapper, never()).markPurchased(anyList(), anyString());
        verify(mapper, never()).selectDeletableByIdsForUpdate(anyList());
    }

    @Test
    void duplicateIdsAreNormalizedAndAffectedRowMismatchThrows()
    {
        PendingPurchaseMapper mapper = mock(PendingPurchaseMapper.class);
        when(mapper.selectDeletableByIdsForUpdate(List.of(1L))).thenReturn(List.of(new PendingPurchase()));
        when(mapper.deletePendingByIds(List.of(1L))).thenReturn(0);
        assertThrows(ServiceException.class, () -> new PendingPurchaseService(mapper).deletePending(List.of(1L,1L)));
    }

    @Test
    void transactionAndSqlHaveDefenceInDepth() throws Exception
    {
        var annotation = PendingPurchaseService.class.getMethod("deletePending", List.class).getAnnotation(Transactional.class);
        assertNotNull(annotation);
        assertTrue(List.of(annotation.rollbackFor()).contains(Exception.class));
        String sql = Files.readString(Path.of("src/main/resources/mapper/procurement/PendingPurchaseMapper.xml"));
        String delete = sql.substring(sql.indexOf("<delete id=\"deletePendingByIds\""), sql.indexOf("</delete>"));
        assertTrue(delete.contains("WHERE status IN ('0', '1') AND id IN"));
        assertTrue(sql.contains("FOR UPDATE"));
        String exportLock = sql.substring(sql.indexOf("<select id=\"selectPendingByIdsForUpdate\""),
                sql.indexOf("<select id=\"selectDeletableByIdsForUpdate\""));
        assertTrue(exportLock.contains("WHERE status = '0'"));
    }
}
