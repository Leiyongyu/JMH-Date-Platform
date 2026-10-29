package com.ruoyi.system.service.operation;

import com.ruoyi.common.exception.ServiceException;
import com.ruoyi.system.domain.operation.AmzMixedSalesQuery;
import com.ruoyi.system.mapper.operation.AmzMixedSalesMapper;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AmzMixedSalesService
{
    private static final Set<String> SORT_FIELDS = Set.of("sku", "fbaStock", "fbaInbound", "fbaTotalInventory", "sales30d");
    private final AmzMixedSalesMapper mapper;

    public AmzMixedSalesService(AmzMixedSalesMapper mapper) { this.mapper = mapper; }

    @Transactional(readOnly = true)
    public Map<String, Object> list(AmzMixedSalesQuery query)
    {
        normalize(query);
        return page(mapper.selectProducts(query), mapper.countProducts(query), query);
    }

    @Transactional(readOnly = true)
    public Map<String, Object> details(AmzMixedSalesQuery query)
    {
        normalize(query);
        if (query.getSku() == null) throw new ServiceException("请选择要查看的仓库SKU");
        return page(mapper.selectDetails(query), mapper.countDetails(query), query);
    }

    public List<Map<String, Object>> stores() { return mapper.selectStores(); }

    private void normalize(AmzMixedSalesQuery query)
    {
        query.setSku(trim(query.getSku()));
        if (query.getSku() != null) query.setSku(query.getSku().toUpperCase(Locale.ROOT));
        query.setProductName(trim(query.getProductName()));
        query.setPageNum(Math.max(query.getPageNum(), 1));
        query.setPageSize(Math.min(Math.max(query.getPageSize(), 1), 200));
        if (query.getSid() != null && query.getSid() <= 0) throw new ServiceException("店铺参数无效");
        if (!SORT_FIELDS.contains(query.getSortField() == null ? "" : query.getSortField()))
            query.setSortField("fbaTotalInventory");
        query.setSortOrder("ascending".equalsIgnoreCase(query.getSortOrder()) || "asc".equalsIgnoreCase(query.getSortOrder()) ? "asc" : "desc");
    }

    private String trim(String text) { return text == null || text.isBlank() ? null : text.trim(); }

    private Map<String, Object> page(List<Map<String, Object>> rows, long total, AmzMixedSalesQuery query)
    {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("items", rows);
        result.put("total", total);
        result.put("pageNum", query.getPageNum());
        result.put("pageSize", query.getPageSize());
        return result;
    }
}
