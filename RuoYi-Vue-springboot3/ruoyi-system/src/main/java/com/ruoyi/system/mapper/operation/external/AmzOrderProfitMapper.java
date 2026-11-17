package com.ruoyi.system.mapper.operation.external;

import com.ruoyi.system.domain.operation.external.AmzOrderProfit;
import org.apache.ibatis.annotations.Param;
import java.util.List;

public interface AmzOrderProfitMapper
{
    List<AmzOrderProfit> selectBySidSku(@Param("sid") Integer sid, @Param("sellerSku") String sellerSku);
    int insert(AmzOrderProfit entity);
    int updateById(AmzOrderProfit entity);
    int batchInsert(@Param("list") List<AmzOrderProfit> list);
    int deleteAll();
}
