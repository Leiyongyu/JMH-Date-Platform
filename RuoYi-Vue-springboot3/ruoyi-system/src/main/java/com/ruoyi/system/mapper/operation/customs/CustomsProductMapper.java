package com.ruoyi.system.mapper.operation.customs;

import com.ruoyi.system.domain.operation.customs.CustomsProduct;
import java.util.List;
import org.apache.ibatis.annotations.Param;

public interface CustomsProductMapper
{
    List<CustomsProduct> search(@Param("keyword") String keyword, @Param("limit") int limit);

    CustomsProduct selectBySku(@Param("sku") String sku);

    List<CustomsProduct> selectBySkus(@Param("skus") List<String> skus);

    int batchUpsert(@Param("products") List<CustomsProduct> products);

    /** 关联overseas_stock_order_detail + customs_inventory_list + warehouse，全量刷新产品库 */
    int refreshFromJoin();
}
