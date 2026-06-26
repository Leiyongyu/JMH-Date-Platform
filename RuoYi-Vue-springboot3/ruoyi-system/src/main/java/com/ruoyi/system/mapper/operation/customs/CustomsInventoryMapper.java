package com.ruoyi.system.mapper.operation.customs;

import com.ruoyi.system.domain.operation.customs.CustomsInventoryItem;
import java.util.List;
import org.apache.ibatis.annotations.Param;

public interface CustomsInventoryMapper
{
    List<CustomsInventoryItem> selectList(@Param("keyword") String keyword);

    CustomsInventoryItem selectById(@Param("id") Long id);

    List<CustomsInventoryItem> selectByIds(@Param("ids") List<Long> ids);

    List<CustomsInventoryItem> selectProductOptions(@Param("productCode") String productCode,
                                                    @Param("productName") String productName,
                                                    @Param("sku") String sku,
                                                    @Param("unit") String unit,
                                                    @Param("limit") int limit);

    int insert(CustomsInventoryItem item);

    int update(CustomsInventoryItem item);

    int deleteAll();

    int batchInsert(@Param("items") List<CustomsInventoryItem> items);
}
