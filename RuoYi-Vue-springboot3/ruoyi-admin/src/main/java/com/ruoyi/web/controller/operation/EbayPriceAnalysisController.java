package com.ruoyi.web.controller.operation;

import com.ruoyi.common.annotation.Log;
import com.ruoyi.common.constant.Constants;
import com.ruoyi.common.core.controller.BaseController;
import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.common.enums.BusinessType;
import com.ruoyi.common.exception.ServiceException;
import com.ruoyi.system.service.operation.ebay.EbayPriceAnalysisPythonClient;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.util.StringUtils;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * 运营中心-eBay价格分析看板。只做转发：所有口径、状态判定和聚合都在 Python 侧算，
 * Java 不重算任何指标，只负责权限、参数名转换和导出列过滤。
 */
@Tag(name = "运营中心-eBay价格分析")
@RestController
@RequestMapping("/operations/ebay/price-analysis")
public class EbayPriceAnalysisController extends BaseController
{
    public static final String LIST_PERMISSION = "operations:ebayPriceAnalysis:list";
    public static final String EXPORT_PERMISSION = "operations:ebayPriceAnalysis:export";
    public static final String COLUMN_PERMISSION_PREFIX =
            "operations:ebayPriceAnalysis:exportColumn:";

    private static final int MAX_PAGE_SIZE = 200;
    /** 与 Python 侧 sku-listings 的 sku 参数限长一致。 */
    static final int MAX_SKU_LENGTH = 255;

    /**
     * 导出列全集，顺序即导出顺序，key 与 Python detail 响应字段名一致。
     * 页面展示不受这些权限控制，只有 Excel 导出列按角色过滤（沿用补货2.0 的做法）。
     */
    private static final List<String> EXPORT_COLUMNS = List.of(
            "seller_account", "site_name", "sku", "owner_name", "title",
            "listing_start_time", "currency",
            "current_price", "price_usd", "ebay_quantity_available",
            "overseas_sellable", "overseas_in_transit", "chengdu_sellable",
            "pending_outbound", "sales_qty_7d", "sales_qty_30d", "cover_days",
            "stock_gap", "purchase_cost_cny", "inventory_qty", "unit_price_tax", "inventory_value_cny",
            "status", "view_item_url");

    private final EbayPriceAnalysisPythonClient client;

    public EbayPriceAnalysisController(EbayPriceAnalysisPythonClient client)
    {
        this.client = client;
    }

    /** 店铺维度汇总：每个店铺 + 站点一行，不分页（店铺只有几十个）。 */
    @PreAuthorize("@ss.hasPermi('operations:ebayPriceAnalysis:list')")
    @GetMapping("/stores")
    public AjaxResult stores(
            @RequestParam(required = false) String sites,
            @RequestParam(required = false) String accounts,
            @RequestHeader(value = "X-Request-ID", required = false) String requestId)
    {
        Map<String, Object> params = new LinkedHashMap<>();
        params.put("sites", trimToNull(sites));
        params.put("accounts", trimToNull(accounts));
        return success(client.stores(params, requestId).get("data"));
    }

    /** 负责人维度汇总：每个负责人一行，不分页（负责人只有个位数）；只受站点、店铺筛选。 */
    @PreAuthorize("@ss.hasPermi('operations:ebayPriceAnalysis:list')")
    @GetMapping("/owners")
    public AjaxResult owners(
            @RequestParam(required = false) String sites,
            @RequestParam(required = false) String accounts,
            @RequestHeader(value = "X-Request-ID", required = false) String requestId)
    {
        Map<String, Object> params = new LinkedHashMap<>();
        params.put("sites", trimToNull(sites));
        params.put("accounts", trimToNull(accounts));
        return success(client.owners(params, requestId).get("data"));
    }

    /** 某个 SKU 在各店铺、各站点的在售与库存对比；SKU 必填，精确匹配。 */
    @PreAuthorize("@ss.hasPermi('operations:ebayPriceAnalysis:list')")
    @GetMapping("/sku-listings")
    public AjaxResult skuListings(
            @RequestParam(required = false) String sku,
            @RequestHeader(value = "X-Request-ID", required = false) String requestId)
    {
        String value = trimToNull(sku);
        if (value == null)
            throw new ServiceException("请填写要查看的 SKU", 400);
        if (value.length() > MAX_SKU_LENGTH)
            throw new ServiceException("SKU 不能超过 " + MAX_SKU_LENGTH + " 个字符", 400);
        return success(client.skuListings(Map.of("sku", value), requestId).get("data"));
    }

    @PreAuthorize("@ss.hasPermi('operations:ebayPriceAnalysis:list')")
    @GetMapping("/detail")
    public AjaxResult detail(
            @RequestParam(required = false) String statDate,
            @RequestParam(required = false) String sites,
            @RequestParam(required = false) String accounts,
            @RequestParam(required = false) String owners,
            @RequestParam(required = false) String status,
            @RequestParam(required = false) String keyword,
            @RequestParam(defaultValue = "detail") String mode,
            @RequestParam(defaultValue = "1") int pageNum,
            @RequestParam(defaultValue = "50") int pageSize,
            @RequestParam(required = false) String sortBy,
            @RequestParam(required = false) String sortOrder,
            @RequestParam(required = false) Boolean siteOversell,
            @RequestParam(required = false) Boolean outOfStockListed,
            @RequestParam(required = false) Boolean unmatched,
            @RequestHeader(value = "X-Request-ID", required = false) String requestId)
    {
        Map<String, Object> params = filters(statDate, sites, accounts, owners, status, keyword);
        params.put("mode", trimToNull(mode));
        // 不传时为 null，不出现在查询串里，Python 按「不筛选」处理。
        params.put("site_oversell", siteOversell);
        params.put("out_of_stock_listed", outOfStockListed);
        params.put("unmatched", unmatched);
        params.put("page", Math.max(pageNum, 1));
        params.put("page_size", Math.min(Math.max(pageSize, 1), MAX_PAGE_SIZE));
        params.put("sort_by", trimToNull(sortBy));
        params.put("sort_order", trimToNull(sortOrder));
        return success(client.detail(params, requestId).get("data"));
    }

    /**
     * 导出当前筛选下的全部明细，不带分页；多店超卖、断货在售、只看未匹配三个筛选与 /detail 一致。
     * GET 与 POST 等价，前端按既有下载方式任选其一。
     */
    @PreAuthorize("@ss.hasPermi('operations:ebayPriceAnalysis:list')"
            + " and @ss.hasPermi('operations:ebayPriceAnalysis:export')")
    @Log(title = "eBay价格分析导出", businessType = BusinessType.EXPORT)
    @GetMapping("/export")
    public void exportByGet(
            @RequestParam(required = false) String statDate,
            @RequestParam(required = false) String sites,
            @RequestParam(required = false) String accounts,
            @RequestParam(required = false) String owners,
            @RequestParam(required = false) String status,
            @RequestParam(required = false) String keyword,
            @RequestParam(defaultValue = "detail") String mode,
            @RequestParam(required = false) String sortBy,
            @RequestParam(required = false) String sortOrder,
            @RequestParam(required = false) Boolean siteOversell,
            @RequestParam(required = false) Boolean outOfStockListed,
            @RequestParam(required = false) Boolean unmatched,
            @RequestHeader(value = "X-Request-ID", required = false) String requestId,
            HttpServletResponse response) throws IOException
    {
        export(statDate, sites, accounts, owners, status, keyword, mode, sortBy, sortOrder,
                siteOversell, outOfStockListed, unmatched, requestId, response);
    }

    @PreAuthorize("@ss.hasPermi('operations:ebayPriceAnalysis:list')"
            + " and @ss.hasPermi('operations:ebayPriceAnalysis:export')")
    @Log(title = "eBay价格分析导出", businessType = BusinessType.EXPORT)
    @PostMapping("/export")
    public void exportByPost(
            @RequestParam(required = false) String statDate,
            @RequestParam(required = false) String sites,
            @RequestParam(required = false) String accounts,
            @RequestParam(required = false) String owners,
            @RequestParam(required = false) String status,
            @RequestParam(required = false) String keyword,
            @RequestParam(defaultValue = "detail") String mode,
            @RequestParam(required = false) String sortBy,
            @RequestParam(required = false) String sortOrder,
            @RequestParam(required = false) Boolean siteOversell,
            @RequestParam(required = false) Boolean outOfStockListed,
            @RequestParam(required = false) Boolean unmatched,
            @RequestHeader(value = "X-Request-ID", required = false) String requestId,
            HttpServletResponse response) throws IOException
    {
        export(statDate, sites, accounts, owners, status, keyword, mode, sortBy, sortOrder,
                siteOversell, outOfStockListed, unmatched, requestId, response);
    }

    private void export(String statDate, String sites, String accounts, String owners,
            String status,
            String keyword, String mode, String sortBy, String sortOrder,
            Boolean siteOversell, Boolean outOfStockListed, Boolean unmatched,
            String requestId, HttpServletResponse response) throws IOException
    {
        Set<String> permissions = getLoginUser().getPermissions();
        Map<String, Object> params = filters(statDate, sites, accounts, owners, status, keyword);
        params.put("mode", trimToNull(mode));
        // 与 /detail 相同：导出跟着页面筛选走；不传为 null，查询串里不出现。
        params.put("site_oversell", siteOversell);
        params.put("out_of_stock_listed", outOfStockListed);
        params.put("unmatched", unmatched);
        params.put("sort_by", trimToNull(sortBy));
        params.put("sort_order", trimToNull(sortOrder));
        params.put("columns", String.join(",", permittedColumns(permissions)));

        EbayPriceAnalysisPythonClient.ExcelFile file = client.export(params, requestId);
        response.setContentType(EbayPriceAnalysisPythonClient.EXCEL_CONTENT_TYPE);
        response.setHeader("Content-Disposition", file.contentDisposition());
        response.setHeader("Access-Control-Expose-Headers", "Content-Disposition");
        response.setHeader("Cache-Control", "no-store");
        response.setContentLengthLong(file.content().length);
        response.getOutputStream().write(file.content());
    }

    /** 无任何导出列权限时直接 403，不把空列传给 Python 换回一个空表格。 */
    static List<String> permittedColumns(Set<String> permissions)
    {
        List<String> allowed = permissions == null ? List.of()
                : EXPORT_COLUMNS.stream()
                        .filter(key -> permissions.contains(Constants.ALL_PERMISSION)
                                || permissions.contains(COLUMN_PERMISSION_PREFIX + key))
                        .toList();
        if (allowed.isEmpty())
            throw new ServiceException(
                    "未配置eBay价格分析导出字段权限，请联系管理员在角色管理中勾选导出字段", 403);
        return allowed;
    }

    private static Map<String, Object> filters(String statDate, String sites,
            String accounts, String owners, String status, String keyword)
    {
        Map<String, Object> params = new LinkedHashMap<>();
        params.put("stat_date", trimToNull(statDate));
        params.put("sites", trimToNull(sites));
        params.put("accounts", trimToNull(accounts));
        params.put("owners", trimToNull(owners));
        params.put("status", trimToNull(status));
        params.put("keyword", trimToNull(keyword));
        return params;
    }

    private static String trimToNull(String value)
    {
        return StringUtils.hasText(value) ? value.trim() : null;
    }
}
