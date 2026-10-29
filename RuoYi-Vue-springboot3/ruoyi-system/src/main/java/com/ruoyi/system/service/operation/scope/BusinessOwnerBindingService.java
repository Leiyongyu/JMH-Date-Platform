package com.ruoyi.system.service.operation.scope;

import com.ruoyi.common.exception.ServiceException;
import com.ruoyi.system.mapper.operation.BusinessDataScopeMapper;
import java.util.LinkedHashSet;
import java.util.List;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class BusinessOwnerBindingService
{
    private final BusinessDataScopeMapper mapper;
    public BusinessOwnerBindingService(BusinessDataScopeMapper mapper) { this.mapper = mapper; }

    /** Called only by administrative insert/update, in the same user transaction. */
    @Transactional(rollbackFor = Exception.class)
    public void save(Long userId, List<String> names)
    {
        if (names == null) return; // Older clients preserve the binding.
        if (userId == null || names.size() > 20) throw new ServiceException("无效业务负责人绑定");
        var normalized = new LinkedHashSet<String>();
        for (String name : names)
        {
            if (name == null || name.isBlank() || name.trim().length() > 100
                    || List.of("未分配", "--").contains(name.trim()))
                throw new ServiceException("业务负责人名称不能为空、未分配或超过100个字符");
            normalized.add(name.trim());
        }
        mapper.deleteBindings(userId);
        try { for (String name : normalized) mapper.insertBinding(userId, name); }
        catch (DuplicateKeyException ex) { throw new ServiceException("业务负责人名称已绑定其他账号，请先由管理员核对并解除原绑定"); }
    }
}
