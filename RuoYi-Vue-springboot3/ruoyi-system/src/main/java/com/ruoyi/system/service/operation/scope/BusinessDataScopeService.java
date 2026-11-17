package com.ruoyi.system.service.operation.scope;

import com.ruoyi.common.utils.SecurityUtils;
import com.ruoyi.system.mapper.operation.BusinessDataScopeMapper;
import java.util.List;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.stereotype.Service;

@Service
public class BusinessDataScopeService
{
    public static final String EBAY = "operations:ebayReplenishmentV2";
    public static final String AMZ = "operations:amzReplenishment";
    private final BusinessDataScopeMapper mapper;

    public BusinessDataScopeService(BusinessDataScopeMapper mapper) { this.mapper = mapper; }

    public BusinessDataScope resolve(String module) { return resolve(SecurityUtils.getUserId(), module); }

    public BusinessDataScope resolve(Long userId, String module)
    {
        // Authorization queries must not consume PageHelper's next business query.
        var page = com.github.pagehelper.PageHelper.getLocalPage();
        com.github.pagehelper.PageHelper.clearPage();
        boolean resolved = false;
        try
        {
            BusinessDataScope result = resolveUnpaged(userId, module);
            resolved = true;
            return result;
        }
        finally
        {
            com.github.pagehelper.PageHelper.clearPage();
            if (resolved && page != null) com.github.pagehelper.PageHelper.setLocalPage(page);
        }
    }

    private BusinessDataScope resolveUnpaged(Long userId, String module)
    {
        if (!List.of(EBAY, AMZ).contains(module)) throw new IllegalArgumentException("未知业务数据范围");
        if (userId == null) throw new AccessDeniedException("请先登录");
        if (SecurityUtils.isAdmin(userId)) return new BusinessDataScope(true, List.of());
        List<String> permissions = mapper.permissions(userId);
        if (permissions.contains(module + ":data:all")) return new BusinessDataScope(true, List.of());
        boolean department = permissions.contains(module + ":data:dept");
        if (!department && !permissions.contains(module + ":data:self"))
            return new BusinessDataScope(false, List.of());
        return new BusinessDataScope(false, mapper.ownerNames(userId, department));
    }

    public void requireAll(String module)
    {
        if (!resolve(module).isAll()) throw new AccessDeniedException("此操作影响共享数据，需要该模块的全部数据权限");
    }

    public void requireAmzRow(String sid, String sku)
    {
        BusinessDataScope scope = resolve(AMZ);
        if (scope.isAll()) return;
        List<String> owners = mapper.amzRowOwners(sid, sku);
        if (owners.isEmpty() || owners.stream().anyMatch(owner -> !scope.allows(owner)))
            throw new AccessDeniedException("无权操作该补货记录，或该记录涉及其他负责人的共享数据");
    }
}
