package com.ruoyi.system.service.ai;

import com.ruoyi.system.service.operation.scope.BusinessDataScope;
import com.ruoyi.system.service.operation.scope.BusinessDataScopeService;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;

/** 组装传给 Python 数据助手的 access：菜单权限 + eBay/AMZ 业务数据范围。在线提问和定时简报共用。 */
public final class AiAgentAccessBuilder
{
    private AiAgentAccessBuilder()
    {
    }

    public static Map<String, Object> build(Long userId, Set<String> permissions, BusinessDataScopeService dataScope)
    {
        Map<String, Object> scopes = new LinkedHashMap<>();
        for (String module : new String[] { BusinessDataScopeService.EBAY, BusinessDataScopeService.AMZ })
        {
            BusinessDataScope scope = dataScope.resolve(userId, module);
            // JSON null 表示全部数据，空列表表示无数据，与补货接口的 allowed_principals 约定一致。
            scopes.put(module, scope.isAll() ? null : new ArrayList<>(scope.getOwners()));
        }
        Map<String, Object> access = new LinkedHashMap<>();
        access.put("permissions", permissions == null ? new ArrayList<>() : new ArrayList<>(permissions));
        access.put("scopes", scopes);
        return access;
    }
}
