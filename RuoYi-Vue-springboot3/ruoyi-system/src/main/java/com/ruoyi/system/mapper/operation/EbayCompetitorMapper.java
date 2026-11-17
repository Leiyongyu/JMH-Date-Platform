package com.ruoyi.system.mapper.operation;

import java.util.List;
import org.apache.ibatis.annotations.Param;
import com.ruoyi.system.domain.operation.ebay.EbayCompetitorFormulaConfig;
import com.ruoyi.system.domain.operation.ebay.EbayCompetitorProduct;
import com.ruoyi.system.domain.operation.ebay.EbayCompetitorProductImage;

/** eBay选竞品商品库Mapper。 */
public interface EbayCompetitorMapper
{
    List<EbayCompetitorProduct> selectProductList(EbayCompetitorProduct query);

    List<EbayCompetitorProduct> selectProductsForExport(@Param("ids") List<Long> ids);

    List<EbayCompetitorProductImage> selectProductImagesByProductIds(
            @Param("productIds") List<Long> productIds);

    EbayCompetitorProduct selectProductById(@Param("id") Long id);

    EbayCompetitorProduct selectBySiteAndItemId(@Param("siteCode") String siteCode,
            @Param("ebayItemId") String ebayItemId);

    int insertProduct(EbayCompetitorProduct product);

    int updateProduct(EbayCompetitorProduct product);

    int deleteProductById(@Param("id") Long id);

    int insertProductImage(EbayCompetitorProductImage image);

    List<EbayCompetitorProductImage> selectImagesByProductId(@Param("productId") Long productId);

    EbayCompetitorFormulaConfig selectFormulaConfig(@Param("siteCode") String siteCode);
}
