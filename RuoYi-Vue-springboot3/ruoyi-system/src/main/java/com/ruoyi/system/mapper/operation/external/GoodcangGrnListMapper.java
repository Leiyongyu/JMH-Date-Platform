package com.ruoyi.system.mapper.operation.external;

import java.util.List;
import com.ruoyi.system.domain.operation.external.GoodcangGrnList;
import org.apache.ibatis.annotations.Param;

public interface GoodcangGrnListMapper
{
    List<GoodcangGrnList> selectAll();
    List<GoodcangGrnList> selectByReceivingCodes(List<String> receivingCodes);
    /** 按 create_at 筛选最近 N 天的入库单 */
    List<GoodcangGrnList> selectRecentByCreateAt(int days);
    int insert(GoodcangGrnList entity);
    int updateById(GoodcangGrnList entity);
    int updateCaAddress1(@Param("id") Long id, @Param("caAddress1") String caAddress1);
}
