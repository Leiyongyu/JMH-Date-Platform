package com.ruoyi.system.service.operation.external.lingxing;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.ruoyi.system.mapper.operation.external.AmzMonthlyOrderProfitMapper;
import com.ruoyi.system.mapper.operation.external.ShopListMapper;
import com.ruoyi.system.service.operation.sync.OperationSyncResult;
import com.ruoyi.system.service.finance.PerformanceRankingService;
import java.time.LocalDate;
import java.time.YearMonth;
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 按完整自然月同步领星 Amazon MSKU 维度订单利润。
 * 远端全部分页成功后才替换目标月份，保留其他月份历史数据。
 */
@Service
public class AmzMonthlyOrderProfitSyncService
{
    private static final String API = "basicOpen/finance/mreport/OrderProfit";
    private static final int PAGE_SIZE = 5000;
    private static final int SID_BATCH_SIZE = 20;
    private static final int DB_BATCH_SIZE = 200;
    private static final List<String> NUMERIC_FIELDS = List.of(
            "gross_profit", "gross_margin", "avg_gross_profit", "volume",
            "replacement_quantity", "multi_channel_volume", "ad_sales_amount",
            "ad_volume", "amount", "tax_amount", "refund_amount",
            "refund_amount_rate", "shipping_cost", "promotion_discount",
            "return_quantity", "return_rate", "selling_fee", "fulfillment_fee",
            "other_order_fee", "spend", "ads_sb_cost", "ads_sbv_cost",
            "ads_sd_cost", "ads_sp_cost", "purchase_costs", "avg_purchase_costs",
            "logistics_costs", "avg_logistics_costs", "other_costs",
            "avg_other_costs", "total_costs", "refund_quantity",
            "ad_sales_amount_sp", "ad_sales_amount_sd", "ad_sales_amount_sb",
            "ad_sales_amount_sbv", "ad_volume_sp", "ad_volume_sd",
            "ad_volume_sb", "ad_volume_sbv", "afn_volume", "mfn_volume",
            "afn_amount", "mfn_amount", "pm_discount", "sp_discount",
            "net_gross_margin", "avg_volume", "net_amount", "avg_net_amount",
            "selling_fee_rate", "fulfillment_fee_rate", "spend_rate",
            "total_stock_fee", "total_stock_fee_rate", "promotion_fee",
            "shared_fba_international_inbound_fee", "adjustments_fee",
            "selling_other_fee", "inventory_credit",
            "shared_fba_inbound_convenience_fee", "cost_of_points_granted",
            "shared_cost_of_advertising", "total_other_granted",
            "shared_fba_liquidation_proceeds",
            "shared_fba_liquidation_proceeds_adjustments",
            "shared_amazon_shipping_reimbursement", "shared_safe_t_reimbursement",
            "shared_netco_transaction", "shared_reimbursements", "shared_clawbacks",
            "shared_commingling_vat_income", "gift_wrap_credits",
            "a_to_z_guarantee_claims", "shared_others", "fba_storage_fee",
            "shared_fba_storage_fee", "long_term_storage_fee",
            "shared_long_term_storage_fee", "shared_storage_renewal_billing",
            "shared_fba_disposal_fee", "shared_fba_removal_fee",
            "shared_fba_inbound_transportation_program_fee", "shared_labeling_fee",
            "shared_polybagging_fee", "shared_bubblewrap_fee", "shared_taping_fee",
            "shared_awd_processing_fee", "shared_awd_transportation_fee",
            "shared_awd_storage_fee", "shared_star_storage_fee",
            "shared_fba_customer_return_fee", "shared_fba_inbound_defect_fee",
            "shared_fba_overage_fee",
            "shared_amazon_partnered_carrier_shipment_fee",
            "shared_item_fee_adjustment", "shared_other_fba_inventory_fees",
            "fba_fulfillment_fee",
            "shared_fba_transaction_customer_return_fee", "off_site_promotion_fee");

    private final LingxingGatewayService gateway;
    private final ShopListMapper shopMapper;
    private final AmzMonthlyOrderProfitMapper mapper;
    private final ObjectMapper objectMapper;
    private final PerformanceRankingService performanceRankingService;

    public AmzMonthlyOrderProfitSyncService(
            LingxingGatewayService gateway,
            ShopListMapper shopMapper,
            AmzMonthlyOrderProfitMapper mapper,
            ObjectMapper objectMapper,
            PerformanceRankingService performanceRankingService)
    {
        this.gateway = gateway;
        this.shopMapper = shopMapper;
        this.mapper = mapper;
        this.objectMapper = objectMapper;
        this.performanceRankingService = performanceRankingService;
    }

    /** 定时任务固定同步上一个完整自然月。 */
    @Transactional(rollbackFor = Exception.class)
    public OperationSyncResult syncPreviousMonth() throws Exception
    {
        return syncMonth(YearMonth.now().minusMonths(1));
    }

    @Transactional(rollbackFor = Exception.class)
    public OperationSyncResult syncMonth(YearMonth month) throws Exception
    {
        long startedAt = System.currentTimeMillis();
        List<String> sids = shopMapper.selectSidsByPlatform("10001", 1);
        if (sids.isEmpty())
        {
            return OperationSyncResult.success(
                    "amz_monthly_order_profit", "领星-Amazon月度完整订单利润",
                    API, 0, 0, System.currentTimeMillis() - startedAt);
        }

        LocalDate startDate = month.atDay(1);
        LocalDate endDate = month.atEndOfMonth();
        List<Map<String, Object>> allRows = new ArrayList<>();

        for (int i = 0; i < sids.size(); i += SID_BATCH_SIZE)
        {
            List<Integer> sidBatch = sids.subList(
                    i, Math.min(i + SID_BATCH_SIZE, sids.size()))
                    .stream().map(Integer::parseInt).collect(Collectors.toList());
            int offset = 0;
            while (true)
            {
                Map<String, Object> body = new LinkedHashMap<>();
                body.put("offset", offset);
                body.put("length", PAGE_SIZE);
                body.put("sids", sidBatch);
                body.put("startDate", startDate.toString());
                body.put("endDate", endDate.toString());
                body.put("currencyCode", "CNY");

                Map<String, Object> response = gateway.post(API, body);
                validateResponse(response);
                List<Map<String, Object>> data = list(response.get("data"));
                for (Map<String, Object> item : data)
                {
                    Map<String, Object> row = toRow(month, item);
                    if (hasText(row.get("sid")) && hasText(row.get("seller_sku")))
                        allRows.add(row);
                }

                int remoteTotal = intValue(response.get("total"));
                if (data.isEmpty()
                        || data.size() < PAGE_SIZE
                        || (remoteTotal > 0 && offset + PAGE_SIZE >= remoteTotal))
                    break;
                offset += PAGE_SIZE;
            }
            if (i + SID_BATCH_SIZE < sids.size()) Thread.sleep(2000L);
        }

        mapper.deleteByStatMonth(month.toString());
        int stored = 0;
        for (int i = 0; i < allRows.size(); i += DB_BATCH_SIZE)
        {
            List<Map<String, Object>> batch = allRows.subList(
                    i, Math.min(i + DB_BATCH_SIZE, allRows.size()));
            stored += mapper.batchUpsert(batch);
        }
        performanceRankingService.refresh(month.toString());

        return OperationSyncResult.success(
                "amz_monthly_order_profit", "领星-Amazon月度完整订单利润",
                API, allRows.size(), stored, System.currentTimeMillis() - startedAt);
    }

    private Map<String, Object> toRow(
            YearMonth month, Map<String, Object> item) throws Exception
    {
        Map<String, Object> row = new LinkedHashMap<>(item);
        for (String field : NUMERIC_FIELDS)
            row.put(field, decimal(item.get(field)));
        List<Map<String, Object>> prices = list(item.get("price_list"));
        List<Map<String, Object>> localInfos = list(item.get("local_infos"));
        List<Map<String, Object>> asins = list(item.get("asins"));
        List<Map<String, Object>> countries = list(item.get("seller_store_countries"));
        List<Object> sidList = objectList(item.get("sids"));

        Map<String, Object> price = first(prices);
        Map<String, Object> localInfo = first(localInfos);
        Map<String, Object> asinInfo = first(asins);
        Map<String, Object> countryInfo = first(countries);

        row.put("stat_month", month.toString());
        row.put("sid", firstText(price.get("sid"), firstValue(sidList)));
        row.put("seller_sku", text(price.get("seller_sku")));
        row.put("local_sku", firstText(price.get("local_sku"), localInfo.get("local_sku")));
        row.put("asin", firstText(price.get("asin"), asinInfo.get("asin")));
        row.put("country", text(countryInfo.get("country")));
        row.put("price_list_json", json(item.get("price_list")));
        row.put("parent_asins_json", json(item.get("parent_asins")));
        row.put("local_infos_json", json(item.get("local_infos")));
        row.put("asins_json", json(item.get("asins")));
        row.put("sids_json", json(item.get("sids")));
        row.put("categories_json", json(item.get("categories")));
        row.put("seller_store_countries_json", json(item.get("seller_store_countries")));
        row.put("brands_json", json(item.get("brands")));
        row.put("raw_json", objectMapper.writeValueAsString(item));
        return row;
    }

    private void validateResponse(Map<String, Object> response)
    {
        if (response == null)
            throw new IllegalStateException("领星月度订单利润接口返回为空");
        if (intValue(response.get("code")) != 0)
            throw new IllegalStateException("领星月度订单利润接口失败："
                    + text(response.get("message")) + " "
                    + text(response.get("error_details")));
    }

    private String json(Object value) throws Exception
    {
        return value == null ? "[]" : objectMapper.writeValueAsString(value);
    }

    @SuppressWarnings("unchecked")
    private List<Map<String, Object>> list(Object value)
    {
        if (value instanceof List<?> source)
        {
            try
            {
                return objectMapper.convertValue(
                        source, new TypeReference<List<Map<String, Object>>>() {});
            }
            catch (Exception ignored) { return new ArrayList<>(); }
        }
        return new ArrayList<>();
    }

    @SuppressWarnings("unchecked")
    private List<Object> objectList(Object value)
    {
        return value instanceof List<?> source
                ? new ArrayList<>((List<Object>) source) : new ArrayList<>();
    }

    private Map<String, Object> first(List<Map<String, Object>> list)
    {
        return list.isEmpty() ? new LinkedHashMap<>() : list.get(0);
    }

    private Object firstValue(List<Object> list)
    {
        return list.isEmpty() ? null : list.get(0);
    }

    private String firstText(Object first, Object second)
    {
        String value = text(first);
        return value.isEmpty() ? text(second) : value;
    }

    private boolean hasText(Object value) { return !text(value).isEmpty(); }
    private String text(Object value) { return value == null ? "" : String.valueOf(value).trim(); }
    private int intValue(Object value)
    {
        if (value instanceof Number number) return number.intValue();
        try { return Integer.parseInt(text(value)); }
        catch (Exception ignored) { return 0; }
    }

    private BigDecimal decimal(Object value)
    {
        String source = text(value);
        if (source.isEmpty()) return null;
        try { return new BigDecimal(source.replace(",", "").replace("%", "")); }
        catch (Exception ignored) { return null; }
    }
}
