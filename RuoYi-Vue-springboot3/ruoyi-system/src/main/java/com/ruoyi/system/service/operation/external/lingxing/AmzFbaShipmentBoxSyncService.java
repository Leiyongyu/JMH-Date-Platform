package com.ruoyi.system.service.operation.external.lingxing;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.ruoyi.system.domain.operation.external.AmzFbaShipmentBox;
import com.ruoyi.system.mapper.operation.external.AmzFbaShipmentBoxMapper;
import com.ruoyi.system.mapper.operation.external.AmzFbaShipmentMapper;
import com.ruoyi.system.mapper.operation.external.ShopListMapper;
import com.ruoyi.system.service.operation.sync.OperationSyncResult;
import java.util.*;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

/** 领星 FBA 货件装箱信息 → amz_fba_shipment_box */
@Service
public class AmzFbaShipmentBoxSyncService
{
    private static final Logger LOG = LoggerFactory.getLogger(AmzFbaShipmentBoxSyncService.class);
    private static final String API = "erp/sc/routing/fba/shipment/boxInfo";

    private final LingxingGatewayService gw;
    private final AmzFbaShipmentBoxMapper mapper;
    private final AmzFbaShipmentMapper shipmentMapper;
    private final ShopListMapper shopMapper;
    private final ObjectMapper om;

    public AmzFbaShipmentBoxSyncService(LingxingGatewayService gw, AmzFbaShipmentBoxMapper mapper,
                                         AmzFbaShipmentMapper shipmentMapper, ShopListMapper shopMapper, ObjectMapper om)
    { this.gw = gw; this.mapper = mapper; this.shipmentMapper = shipmentMapper; this.shopMapper = shopMapper; this.om = om; }

    /** 表空全量拉，有数据拉最近5天 */
    public OperationSyncResult sync() throws Exception {
        int days = mapper.count() == 0 ? 365 : 5;
        return sync(days);
    }

    /** 全量拉取：最近N天已完成的货件 */
    public OperationSyncResult sync(int days) throws Exception
    {
        long start = System.currentTimeMillis();
        List<String> sids = shopMapper.selectSidsByPlatform("10001", 1);
        // CLOSED货件 + 最近N天
        List<Map<String, Object>> refs = shipmentMapper.selectClosedSidShipmentByDays(days);
        LOG.info("FBA装箱信息 共 {} 个sid, {} 条已完成货件(最近{}天)", sids.size(), refs.size(), days);

        int total = 0;
        for (Map<String, Object> ref : refs)
        {
            Integer sid = (Integer) ref.get("sid");
            String shipmentId = (String) ref.get("shipment_id");
            if (sid == null || shipmentId == null || shipmentId.isEmpty()) continue;

            try
            {
                Map<String, Object> body = new LinkedHashMap<>();
                body.put("sid", sid);
                body.put("shipment_id", shipmentId);
                Map<String, Object> resp = gw.post(API, body);
                Map<String, Object> dd = getMap(resp, "data");
                if (dd == null) continue;

                String boxType = str(dd, "box_type");
                List<Map<String, Object>> boxList = getList(dd, "box_list");
                if (boxList == null || boxList.isEmpty()) continue;

                mapper.deleteByShipmentId(shipmentId);
                List<AmzFbaShipmentBox> batch = new ArrayList<>();
                for (Map<String, Object> box : boxList)
                {
                    Integer boxNum = intVal(box, "box_num");
                    List<Map<String, Object>> mskus = getList(box, "box_mskus");
                    if (mskus == null || mskus.isEmpty())
                    {
                        AmzFbaShipmentBox b = buildBox(sid, shipmentId, boxType, box, boxNum, null);
                        batch.add(b);
                    }
                    else
                    {
                        for (Map<String, Object> ms : mskus)
                        {
                            AmzFbaShipmentBox b = buildBox(sid, shipmentId, boxType, box, boxNum, ms);
                            batch.add(b);
                        }
                    }
                }
                if (!batch.isEmpty()) { mapper.batchInsert(batch); total += batch.size(); }
            }
            catch (Exception e) { LOG.warn("FBA装箱信息失败 {}/{}: {}", sid, shipmentId, e.getMessage()); }
        }
        int skuMapped = mapper.updateSkuFromListing();
        LOG.info("FBA装箱信息 完成: {} 条, SKU映射: {} 条", total, skuMapped);
        return OperationSyncResult.success("amz_fba_box", "领星-FBA装箱信息", API, total, total, System.currentTimeMillis() - start);
    }

    private AmzFbaShipmentBox buildBox(Integer sid, String shipmentId, String boxType,
                                        Map<String, Object> box, Integer boxNum, Map<String, Object> msku)
    {
        AmzFbaShipmentBox b = new AmzFbaShipmentBox();
        b.setSid(sid);
        b.setShipmentId(shipmentId);
        b.setBoxType(boxType);
        b.setBoxLength(str(box, "box_length"));
        b.setBoxWidth(str(box, "box_width"));
        b.setBoxHeight(str(box, "box_height"));
        b.setBoxWeight(str(box, "box_weight"));
        b.setBoxDimensionsUnit(str(box, "box_dimensions_unit"));
        b.setBoxWeightUnit(str(box, "box_weight_unit"));
        b.setBoxNum(boxNum);
        if (msku != null)
        {
            b.setMsku(str(msku, "msku"));
            b.setFulfillmentNetworkSku(str(msku, "fulfillment_network_sku"));
            b.setQuantityInCase(str(msku, "quantity_in_case"));
        }
        return b;
    }

    @SuppressWarnings("unchecked")
    private List<Map<String, Object>> getList(Map<String, Object> r, String k)
    { Object o = r.get(k); if (o instanceof List) return (List<Map<String, Object>>) o; try { return om.convertValue(o, new TypeReference<List<Map<String, Object>>>() {}); } catch (Exception e) { return null; } }
    @SuppressWarnings("unchecked")
    private Map<String, Object> getMap(Map<String, Object> r, String k)
    { Object o = r.get(k); return o instanceof Map ? (Map<String, Object>) o : null; }
    private String str(Map<String, Object> m, String k) { Object v = m.get(k); return v != null ? v.toString() : null; }
    private Integer intVal(Map<String, Object> m, String k) { Object v = m.get(k); if (v instanceof Number) return ((Number)v).intValue(); if (v != null) try { return Integer.parseInt(v.toString()); } catch (Exception e) {} return null; }
}
