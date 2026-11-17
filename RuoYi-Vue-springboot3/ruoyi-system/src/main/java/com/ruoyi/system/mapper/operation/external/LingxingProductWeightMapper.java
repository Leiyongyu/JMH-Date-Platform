package com.ruoyi.system.mapper.operation.external;

import com.ruoyi.system.domain.operation.external.LingxingProductWeight;
import java.util.List;

public interface LingxingProductWeightMapper
{
    int upsert(LingxingProductWeight entity);
    int count();
}
