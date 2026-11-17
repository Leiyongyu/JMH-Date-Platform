package com.ruoyi.system.mapper.operation.external;

import com.ruoyi.system.domain.operation.external.AmzFormulaConfig;
import java.util.List;

public interface AmzFormulaConfigMapper
{
    List<AmzFormulaConfig> selectAll();
    AmzFormulaConfig selectById(Long id);
    int insert(AmzFormulaConfig config);
    int updateById(AmzFormulaConfig config);
}
