package com.ruoyi.web.controller.system;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.ruoyi.common.core.domain.entity.SysUser;
import com.ruoyi.common.core.domain.model.LoginUser;
import com.ruoyi.system.service.ai.AiAssistantPythonClient;
import com.ruoyi.system.service.operation.scope.BusinessDataScope;
import com.ruoyi.system.service.operation.scope.BusinessDataScopeService;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;

class AiAssistantAgentControllerTest
{
    @AfterEach
    void clear()
    {
        SecurityContextHolder.clearContext();
    }

    private void login(Set<String> permissions)
    {
        SysUser sysUser = new SysUser();
        sysUser.setUserName("zhangsan");
        LoginUser user = new LoginUser(7L, 1L, sysUser, permissions);
        SecurityContextHolder.getContext().setAuthentication(
                new UsernamePasswordAuthenticationToken(user, null, List.of()));
    }

    @Test
    @SuppressWarnings("unchecked")
    void clientSuppliedAccessIsReplacedByLoginUserPermissionsAndScopes()
    {
        login(Set.of("finance:performanceRanking:list"));
        AiAssistantPythonClient client = mock(AiAssistantPythonClient.class);
        BusinessDataScopeService scopes = mock(BusinessDataScopeService.class);
        when(scopes.resolve(7L, BusinessDataScopeService.EBAY)).thenReturn(new BusinessDataScope(false, List.of("张三")));
        when(scopes.resolve(7L, BusinessDataScopeService.AMZ)).thenReturn(new BusinessDataScope(true, List.of()));
        when(client.startAgentRun(any(), anyLong(), anyString(), any())).thenReturn(Map.of("runId", "r"));

        new AiAssistantController(client, scopes).startAgentRun(Map.of(
                "message", "10月排名",
                "access", Map.of("permissions", List.of("*:*:*"), "scopes", Map.of())), "req");

        ArgumentCaptor<Map<String, Object>> body = ArgumentCaptor.forClass(Map.class);
        verify(client).startAgentRun(body.capture(), eq(7L), eq("zhangsan"), eq("req"));
        Map<String, Object> access = (Map<String, Object>) body.getValue().get("access");
        assertEquals(List.of("finance:performanceRanking:list"), access.get("permissions"));
        Map<String, Object> scope = (Map<String, Object>) access.get("scopes");
        assertEquals(List.of("张三"), scope.get(BusinessDataScopeService.EBAY));
        assertNull(scope.get(BusinessDataScopeService.AMZ));
        assertEquals("10月排名", body.getValue().get("message"));
    }

    @Test
    void runIdMustBeUuid()
    {
        login(Set.of());
        AiAssistantPythonClient client = mock(AiAssistantPythonClient.class);
        AiAssistantController controller = new AiAssistantController(client, mock(BusinessDataScopeService.class));
        assertThrows(IllegalArgumentException.class, () -> controller.agentRun("../conversations", "req"));
        verify(client, never()).getAgentRun(anyString(), anyLong(), anyString(), any());
    }
}
