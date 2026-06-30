package com.ruoyi.system.mapper.operation.external;

import com.ruoyi.system.domain.operation.external.EbayReplenishFormula;
import java.util.List;

public interface EbayReplenishFormulaMapper
{
    List<EbayReplenishFormula> selectAll();
    List<EbayReplenishFormula> selectActive();
    EbayReplenishFormula selectById(Long id);
    int update(EbayReplenishFormula formula);
}
