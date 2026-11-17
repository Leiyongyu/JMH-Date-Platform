package com.ruoyi.system.service.operation;

import com.github.pagehelper.PageHelper;
import com.ruoyi.system.mapper.operation.BusinessDataScopeMapper;
import com.ruoyi.system.service.operation.scope.BusinessDataScopeService;
import com.ruoyi.system.service.operation.scope.BusinessOwnerBindingService;
import java.util.List;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class BusinessDataScopeServiceTest
{
    @Test void modulesAreIndependentAndMissingPermissionsDeny()
    {
        var mapper = mock(BusinessDataScopeMapper.class);
        var service = new BusinessDataScopeService(mapper);
        when(mapper.permissions(2L)).thenReturn(List.of(BusinessDataScopeService.EBAY + ":data:self",
                BusinessDataScopeService.AMZ + ":data:all"));
        when(mapper.ownerNames(2L, false)).thenReturn(List.of("甲"));
        assertEquals(List.of("甲"), service.resolve(2L, BusinessDataScopeService.EBAY).getOwners());
        assertTrue(service.resolve(2L, BusinessDataScopeService.AMZ).isAll());
        when(mapper.permissions(2L)).thenReturn(List.of());
        var denied = service.resolve(2L, BusinessDataScopeService.EBAY);
        assertFalse(denied.isAll()); assertTrue(denied.getOwners().isEmpty());
        assertTrue(service.resolve(1L, BusinessDataScopeService.EBAY).isAll());
    }

    @Test void departmentUnionAndPaginationArePreserved()
    {
        var mapper = mock(BusinessDataScopeMapper.class);
        var service = new BusinessDataScopeService(mapper);
        when(mapper.permissions(2L)).thenAnswer(invocation -> {
            assertNull(PageHelper.getLocalPage());
            return List.of(BusinessDataScopeService.EBAY + ":data:self", BusinessDataScopeService.EBAY + ":data:dept");
        });
        when(mapper.ownerNames(2L, true)).thenReturn(List.of("甲", "乙"));
        var page = PageHelper.startPage(2, 20);
        try {
            assertEquals(List.of("甲", "乙"), service.resolve(2L, BusinessDataScopeService.EBAY).getOwners());
            assertSame(page, PageHelper.getLocalPage());
        } finally { PageHelper.clearPage(); }
    }

    @Test void bindingValidationDoesNotModifyDataAndLegacyClientsPreserveBindings()
    {
        var mapper = mock(BusinessDataScopeMapper.class);
        var service = new BusinessOwnerBindingService(mapper);
        service.save(2L, null);
        assertThrows(RuntimeException.class, () -> service.save(2L, List.of("未分配")));
        verifyNoInteractions(mapper);
        service.save(2L, List.of("甲", " 甲 "));
        verify(mapper).deleteBindings(2L);
        verify(mapper, times(1)).insertBinding(2L, "甲");
    }
}
