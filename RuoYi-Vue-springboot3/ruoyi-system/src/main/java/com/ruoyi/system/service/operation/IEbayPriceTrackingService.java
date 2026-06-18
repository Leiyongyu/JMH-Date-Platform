package com.ruoyi.system.service.operation;

import java.util.List;
import java.util.Map;

import com.ruoyi.system.domain.operation.EbayPriceTrackingSnapshot;
import com.ruoyi.system.domain.operation.EbayReplenishmentSearchRequest;
import com.ruoyi.system.domain.operation.external.EbayLinkTemplate;

public interface IEbayPriceTrackingService
{
    /** SQL 下推搜索 */
    List<EbayPriceTrackingSnapshot> search(EbayReplenishmentSearchRequest req);

    /** distinct 候选值 */
    List<String> distinctValues(String field, String keyword);

    /** 全量重算并批量写入 */
    void refreshSnapshot();

    /** 跟卖利润率 & 底线价计算 */
    Map<String, Object> calcTracking(String site, String sku, String trackingPrice);

    /** 保存跟卖价到 ebay_product_dedup */
    void saveTrackingPrice(String site, String sku, String trackingPrice);

    /** 保存 OE 号 */
    void saveOeNumber(String site, String sku, String oeNumber);

    /** 保存备注 */
    void saveRemark(String site, String sku, String remark);

    /** 链接模板管理 */
    List<EbayLinkTemplate> listLinkTemplates();
    void saveLinkTemplate(EbayLinkTemplate template);

    /** 列表查询（导出用） */
    List<EbayPriceTrackingSnapshot> listAll(EbayPriceTrackingSnapshot filter);
}
