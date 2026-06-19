package com.ruoyi.system.mapper.operation.external;

import java.util.List;
import com.ruoyi.system.domain.operation.external.GoodcangGrnList;

public interface GoodcangGrnListMapper
{
    List<GoodcangGrnList> selectAll();
    List<GoodcangGrnList> selectByReceivingCodes(List<String> receivingCodes);
    int insert(GoodcangGrnList entity);
    int updateById(GoodcangGrnList entity);
}
