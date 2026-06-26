package com.ruoyi.system.service.operation.external.lingxing;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.ruoyi.system.domain.operation.external.OverseasStockOrder;
import com.ruoyi.system.domain.operation.external.OverseasStockOrderDetail;
import com.ruoyi.system.mapper.operation.external.OverseasStockOrderDetailMapper;
import com.ruoyi.system.mapper.operation.external.OverseasStockOrderMapper;
import com.ruoyi.system.service.operation.sync.OperationSyncResult;
import java.math.BigDecimal;
import java.util.*;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

/** 领星备货单详情同步 → overseas_stock_order_detail */
@Service
public class OverseasStockOrderDetailSyncService
{
    private static final Logger LOG = LoggerFactory.getLogger(OverseasStockOrderDetailSyncService.class);
    private static final String API = "basicOpen/overSeaWarehouse/stockOrder/detail";

    private final LingxingGatewayService gw;
    private final OverseasStockOrderMapper stockOrderMapper;
    private final OverseasStockOrderDetailMapper mapper;
    private final ObjectMapper om;

    public OverseasStockOrderDetailSyncService(LingxingGatewayService gw,
                                                OverseasStockOrderMapper stockOrderMapper,
                                                OverseasStockOrderDetailMapper mapper,
                                                ObjectMapper om)
    { this.gw = gw; this.stockOrderMapper = stockOrderMapper; this.mapper = mapper; this.om = om; }

    public OperationSyncResult sync() throws Exception
    {
        long start = System.currentTimeMillis();
        List<OverseasStockOrder> orders = stockOrderMapper.selectAll();
        int total = 0, orderCount = 0;
        LOG.info("备货单详情 共 {} 个备货单", orders.size());

        for (OverseasStockOrder order : orders)
        {
            try
            {
                Map<String, Object> body = new LinkedHashMap<>();
                body.put("overseas_order_no", order.getOverseasOrderNo());
                Map<String, Object> resp = gw.post(API, body);
                Map<String, Object> dd = getMap(resp, "data");
                if (dd == null) continue;

                // 删除旧数据
                mapper.deleteByOrderNo(order.getOverseasOrderNo());

                // 解析 products 数组，建 SKU→产品信息 索引
                Map<String, Map<String, Object>> productBySku = new LinkedHashMap<>();
                List<Map<String, Object>> products = getList(dd, "products");
                if (products != null) {
                    for (Map<String, Object> p : products) {
                        String psku = str(p, "sku");
                        if (psku != null && !psku.isEmpty()) productBySku.put(psku, p);
                    }
                }

                // 解析 box_data
                Map<String, Object> boxData = getMap(dd, "box_data");
                Integer boxType = null;
                String boxRemark = null;
                Integer totalBoxNum = null;
                BigDecimal totalBoxW = null, totalBoxV = null, totalBoxVW = null;
                List<Map<String, Object>> boxContents = Collections.emptyList();
                if (boxData != null) {
                    boxType = intVal(boxData, "box_type");
                    boxRemark = str(boxData, "box_remark");
                    totalBoxNum = intVal(boxData, "total_box_num");
                    totalBoxW = bdVal(boxData, "total_box_weight");
                    totalBoxV = bdVal(boxData, "total_box_volume");
                    totalBoxVW = bdVal(boxData, "total_box_volume_weight");
                    boxContents = getList(boxData, "box_content");
                    if (boxContents == null) boxContents = Collections.emptyList();
                }

                // 扁平化: 每个 box_content × 每个 boxInfo → 一行
                List<OverseasStockOrderDetail> rows = new ArrayList<>();
                for (Map<String, Object> bc : boxContents) {
                    String bcSku = str(bc, "sku");
                    Map<String, Object> matchedProduct = bcSku != null ? productBySku.get(bcSku) : null;

                    List<Map<String, Object>> boxInfoList = getList(bc, "boxInfo");
                    if (boxInfoList == null || boxInfoList.isEmpty()) continue;
                    for (Map<String, Object> bi : boxInfoList) {
                        OverseasStockOrderDetail d = new OverseasStockOrderDetail();
                        d.setOverseasOrderNo(order.getOverseasOrderNo());
                        d.setSWid(intVal(dd, "s_wid"));
                        d.setRWid(intVal(dd, "r_wid"));
                        d.setStatus(intVal(dd, "status"));

                        // 产品层
                        if (matchedProduct != null) {
                            d.setProductCode(str(matchedProduct, "product_code"));
                            d.setSku(str(matchedProduct, "sku"));
                            d.setSellerId(str(matchedProduct, "seller_id"));
                            d.setPackageNum(intVal(matchedProduct, "package_num"));
                            d.setTariffsCurrencyUnit(str(matchedProduct, "tariffs_currency_unit"));
                        }

                        // 箱数据
                        d.setBoxType(boxType);
                        d.setBoxSku(bcSku);
                        d.setBoxThirdPartyProductName(str(bc, "third_party_product_name"));
                        d.setBoxThirdPartyProductCode(str(bc, "third_party_product_code"));
                        d.setBoxSellerId(str(bc, "seller_id"));
                        d.setBoxRange(str(bi, "boxRange"));
                        d.setBoxNumber(intVal(bi, "boxNumber"));
                        d.setCgBoxWeight(bdVal(bi, "cg_box_weight"));
                        d.setCgBoxLength(bdVal(bi, "cg_box_length"));
                        d.setCgBoxWidth(bdVal(bi, "cg_box_width"));
                        d.setCgBoxHeight(bdVal(bi, "cg_box_height"));
                        d.setQuantityInCase(intVal(bi, "quantity_in_case"));
                        d.setBoxCbm(bdVal(bi, "box_cbm"));
                        d.setTotalBoxVolume(bdVal(bi, "total_box_volume"));
                        d.setTotalBoxWeight(bdVal(bi, "total_box_weight"));
                        d.setTotalBoxVolumeWeight(bdVal(bi, "total_box_volume_weight"));

                        // 整单箱汇总
                        d.setBoxRemark(boxRemark);
                        d.setOrderTotalBoxNum(totalBoxNum);
                        d.setOrderTotalBoxWeight(totalBoxW);
                        d.setOrderTotalBoxVolume(totalBoxV);
                        d.setOrderTotalBoxVolumeWeight(totalBoxVW);
                        d.setCreateTime(new Date());

                        rows.add(d);
                    }
                }
                if (!rows.isEmpty()) { mapper.batchInsert(rows); total += rows.size(); orderCount++; }
            }
            catch (Exception e) { LOG.warn("备货单详情失败 {}: {}", order.getOverseasOrderNo(), e.getMessage()); }
        }
        LOG.info("备货单详情 完成: {}个订单, {}行", orderCount, total);
        return OperationSyncResult.success("stock_order_detail", "领星-备货单详情", API, total, total, System.currentTimeMillis() - start);
    }

    @SuppressWarnings("unchecked")
    private List<Map<String, Object>> getList(Map<String, Object> r, String k)
    { Object o = r.get(k); if (o instanceof List) return (List<Map<String, Object>>) o; try { return om.convertValue(o, new TypeReference<List<Map<String, Object>>>() {}); } catch (Exception e) { return null; } }
    @SuppressWarnings("unchecked")
    private Map<String, Object> getMap(Map<String, Object> r, String k)
    { Object o = r.get(k); return o instanceof Map ? (Map<String, Object>) o : null; }
    private String str(Map<String, Object> m, String k) { Object v = m.get(k); return v != null ? v.toString() : null; }
    private Integer intVal(Map<String, Object> m, String k) { Object v = m.get(k); if (v instanceof Number) return ((Number)v).intValue(); if (v != null) try { return Integer.parseInt(v.toString()); } catch (Exception e) {} return null; }
    private BigDecimal bdVal(Map<String, Object> m, String k) { Object v = m.get(k); if (v == null) return null; if (v instanceof Number) return BigDecimal.valueOf(((Number)v).doubleValue()); try { return new BigDecimal(v.toString()); } catch (Exception e) { return null; } }
}
