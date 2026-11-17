package com.ruoyi.system.service.report.impl;

import com.ruoyi.system.domain.report.InventoryOpeningValue;
import com.ruoyi.system.mapper.report.InventoryOpeningMapper;
import com.ruoyi.system.service.report.IInventoryOpeningService;
import java.util.List;
import org.springframework.stereotype.Service;

@Service
public class InventoryOpeningServiceImpl implements IInventoryOpeningService
{
    private final InventoryOpeningMapper mapper;

    public InventoryOpeningServiceImpl(InventoryOpeningMapper mapper)
    {
        this.mapper = mapper;
    }

    @Override
    public List<InventoryOpeningValue> selectList(InventoryOpeningValue vo)
    {
        return mapper.selectList(vo);
    }
}
