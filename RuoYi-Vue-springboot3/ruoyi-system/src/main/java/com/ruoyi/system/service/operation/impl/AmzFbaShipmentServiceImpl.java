package com.ruoyi.system.service.operation.impl;

import com.ruoyi.system.domain.operation.EbayReplenishmentSearchRequest;
import com.ruoyi.system.domain.operation.external.AmzFbaShipment;
import com.ruoyi.system.mapper.operation.external.AmzFbaShipmentMapper;
import com.ruoyi.system.service.operation.IAmzFbaShipmentService;
import java.util.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

@Service
public class AmzFbaShipmentServiceImpl implements IAmzFbaShipmentService
{
    private static final Set<String> SORT_FIELDS = Set.of(
        "sid", "shipmentId", "sku", "msku", "quantityShipped", "quantityReceived",
        "declaredDiff", "gmtCreate"
    );
    private static final Set<String> TEXT_FIELDS = Set.of(
        "shipmentId", "sku", "msku", "storeName", "username"
    );
    private static final Set<String> DATE_FIELDS = Set.of(
        "gmtCreateStart", "gmtCreateEnd", "gmtModifiedStart", "gmtModifiedEnd"
    );
    private static final Map<String, String> NUM_MAP = new LinkedHashMap<>();
    static {
        NUM_MAP.put("quantityShipped", "quantity_shipped");
        NUM_MAP.put("quantityReceived", "quantity_received");
        NUM_MAP.put("quantityShippedLocal", "quantity_shipped_local");
        NUM_MAP.put("initQuantityShipped", "init_quantity_shipped");
        NUM_MAP.put("declaredDiff", "declared_diff");
    }
    private static final Set<String> ALLOWED_OPS = Set.of("=", ">", ">=", "<", "<=", "between", "isNull", "isNotNull");

    @Autowired
    private AmzFbaShipmentMapper mapper;

    @Override
    public List<AmzFbaShipment> search(EbayReplenishmentSearchRequest req)
    {
        return mapper.search(buildParams(req));
    }

    private Map<String, Object> buildParams(EbayReplenishmentSearchRequest req)
    {
        Map<String, Object> p = new HashMap<>();
        if (req.getSortField() != null && SORT_FIELDS.contains(req.getSortField()))
        {
            p.put("sortField", req.getSortField());
            p.put("sortOrder", "ascending".equals(req.getSortOrder()) ? "ascending" : "descending");
        }
        if (req.getFilters() == null || req.getFilters().isEmpty()) return p;
        for (EbayReplenishmentSearchRequest.FilterItem f : req.getFilters())
        {
            if (!StringUtils.hasText(f.getField())) continue;
            String field = f.getField().trim();
            if (TEXT_FIELDS.contains(field))
            {
                if (!StringUtils.hasText(f.getValue())) continue;
                p.put(field, f.getValue().trim());
                continue;
            }
            if (DATE_FIELDS.contains(field))
            {
                if (StringUtils.hasText(f.getValue())) p.put(field, f.getValue().trim() + " 00:00:00");
                continue;
            }
            if (NUM_MAP.containsKey(field)) parseNum(p, field, f);
        }
        return p;
    }

    private void parseNum(Map<String, Object> p, String field, EbayReplenishmentSearchRequest.FilterItem f)
    {
        String operator = f.getOperator();
        String value = f.getValue();
        String value2 = f.getValue2();
        String db = NUM_MAP.getOrDefault(field, field);
        if (StringUtils.hasText(operator) && ALLOWED_OPS.contains(operator))
        {
            if ("isNull".equals(operator)) { p.put(db + "_op", "isNull"); return; }
            if ("isNotNull".equals(operator)) { p.put(db + "_op", "isNotNull"); return; }
            if ("between".equals(operator) && StringUtils.hasText(value) && StringUtils.hasText(value2))
            {
                try { p.put(db + "_op", "between"); p.put(db + "_val", new java.math.BigDecimal(value.trim())); p.put(db + "_val2", new java.math.BigDecimal(value2.trim())); }
                catch (NumberFormatException ignored) {}
                return;
            }
            if (StringUtils.hasText(value))
            {
                try { p.put(db + "_op", operator); p.put(db + "_val", new java.math.BigDecimal(value.trim())); }
                catch (NumberFormatException ignored) {}
                return;
            }
            return;
        }
        if (!StringUtils.hasText(value)) return;
        String raw = value.trim(); String op, ns;
        if (raw.startsWith(">=")) { op = ">="; ns = raw.substring(2).trim(); }
        else if (raw.startsWith("<=")) { op = "<="; ns = raw.substring(2).trim(); }
        else if (raw.startsWith(">")) { op = ">"; ns = raw.substring(1).trim(); }
        else if (raw.startsWith("<")) { op = "<"; ns = raw.substring(1).trim(); }
        else if (raw.startsWith("=")) { op = "="; ns = raw.substring(1).trim(); }
        else { op = "="; ns = raw; }
        if (ns.isEmpty()) return;
        try { p.put(db + "_op", op); p.put(db + "_val", new java.math.BigDecimal(ns)); }
        catch (NumberFormatException e) { p.put(field, raw); }
    }
}
