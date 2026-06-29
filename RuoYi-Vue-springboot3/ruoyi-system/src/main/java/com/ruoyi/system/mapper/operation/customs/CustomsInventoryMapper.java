package com.ruoyi.system.mapper.operation.customs;

import com.ruoyi.system.domain.operation.customs.CustomsInventoryItem;
import java.util.List;
import java.util.Map;
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

    /** 按 (sku, source_location) 批量更新申报要素 */
    int batchUpdateDeclarationElements(@Param("list") List<Map<String, Object>> list);

    /** 批量新增（只填 sku, source_location, declaration_elements） */
    int batchInsertDeclarationRows(@Param("list") List<Map<String, Object>> list);

    /** 按 (sku, source_location) 查已存在记录 */
    List<Map<String, Object>> selectExistingSkuSource(@Param("keys") List<Map<String, Object>> keys);
}
