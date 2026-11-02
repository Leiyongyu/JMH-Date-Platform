package com.ruoyi.web.task;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.ruoyi.common.core.domain.entity.SysUser;
import com.ruoyi.framework.web.service.SysPermissionService;
import com.ruoyi.system.service.ISysUserService;
import com.ruoyi.system.service.ai.AiAssistantPythonClient;
import com.ruoyi.system.service.operation.IOperationSyncLogService;
import com.ruoyi.system.service.operation.scope.BusinessDataScope;
import com.ruoyi.system.service.operation.scope.BusinessDataScopeService;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

class AiBriefTaskTest
{
    private static SysUser user(long id, String name, String status)
    {
        SysUser user = new SysUser();
        user.setUserId(id);
        user.setUserName(name);
        user.setStatus(status);
        user.setDelFlag("0");
        return user;
    }

    @Test
    @SuppressWarnings("unchecked")
    void dueBriefsRunWithOwnersCurrentAccessAndDisabledUsersAreSkipped()
    {
        AiAssistantPythonClient client = mock(AiAssistantPythonClient.class);
        ISysUserService users = mock(ISysUserService.class);
        SysPermissionService permissions = mock(SysPermissionService.class);
        BusinessDataScopeService scopes = mock(BusinessDataScopeService.class);
        when(client.dueBriefs(anyString())).thenReturn(List.of(
                Map.of("id", 3, "userId", 7, "username", "zhangsan"),
                Map.of("id", 4, "userId", 8, "username", "lisi")));
        SysUser active = user(7L, "zhangsan", "0");
        when(users.selectUserById(7L)).thenReturn(active);
        when(users.selectUserById(8L)).thenReturn(user(8L, "lisi", "1"));
        when(permissions.getMenuPermission(active)).thenReturn(Set.of("finance:salesDashboard:list"));
        when(scopes.resolve(7L, BusinessDataScopeService.EBAY)).thenReturn(new BusinessDataScope(false, List.of("张三")));
        when(scopes.resolve(7L, BusinessDataScopeService.AMZ)).thenReturn(new BusinessDataScope(true, List.of()));

        new AiBriefTask(client, users, permissions, scopes, mock(IOperationSyncLogService.class)).runDue();

        ArgumentCaptor<Map<String, Object>> body = ArgumentCaptor.forClass(Map.class);
        verify(client).runBrief(eq(3L), body.capture(), eq(7L), eq("zhangsan"), anyString());
        verify(client, never()).runBrief(eq(4L), any(), anyLong(), anyString(), anyString());
        Map<String, Object> access = (Map<String, Object>) body.getValue().get("access");
        assertEquals(List.of("finance:salesDashboard:list"), access.get("permissions"));
        Map<String, Object> scope = (Map<String, Object>) access.get("scopes");
        assertEquals(List.of("张三"), scope.get(BusinessDataScopeService.EBAY));
        assertNull(scope.get(BusinessDataScopeService.AMZ));
        assertEquals(false, body.getValue().get("force"));
    }
}
