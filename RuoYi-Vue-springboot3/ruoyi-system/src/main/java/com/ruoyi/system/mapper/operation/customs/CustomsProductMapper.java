package com.ruoyi.system.mapper.operation.customs;

import com.ruoyi.system.domain.operation.customs.CustomsFbaShipmentOption;
import com.ruoyi.system.domain.operation.customs.CustomsDeclarationItem;
import com.ruoyi.system.domain.operation.customs.CustomsProduct;
import com.ruoyi.system.domain.operation.customs.CustomsStockOrderOption;
import java.util.List;
import org.apache.ibatis.annotations.Param;

public interface CustomsProductMapper
{
    List<CustomsProduct> search(@Param("keyword") String keyword, @Param("limit") int limit);

    CustomsProduct selectBySku(@Param("sku") String sku);

    List<CustomsProduct> selectBySkus(@Param("skus") List<String> skus);

    List<CustomsProduct> selectExistingBySkuSource(@Param("products") List<CustomsProduct> products);

    List<CustomsStockOrderOption> searchStockOrders(@Param("keyword") String keyword, @Param("limit") int limit);

    List<CustomsDeclarationItem> selectProductsByStockOrders(@Param("orders") List<String> orders);

    List<String> selectMissingSkusByStockOrders(@Param("orders") List<String> orders);

    List<CustomsFbaShipmentOption> searchFbaShipments(@Param("keyword") String keyword, @Param("limit") int limit);

    List<CustomsProduct> selectProductsByFbaShipments(@Param("shipments") List<String> shipments);

    List<String> selectMissingSkusByFbaShipments(@Param("shipments") List<String> shipments);

    int batchInsert(@Param("products") List<CustomsProduct> products);

    int batchUpsert(@Param("products") List<CustomsProduct> products);

    int countAll();

    /** 关联overseas_stock_order_detail + customs_inventory_list + warehouse，全量刷新产品库 */
    int refreshFromJoin();

    /** 从 Amazon FBA 装箱明细补充不存在的 SKU */
    int insertMissingFromAmzShipmentBox();
}
