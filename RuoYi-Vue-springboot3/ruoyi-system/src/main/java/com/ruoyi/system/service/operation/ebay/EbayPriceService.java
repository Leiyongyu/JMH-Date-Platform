package com.ruoyi.system.service.operation.ebay;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.regex.Pattern;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.fasterxml.jackson.databind.node.JsonNodeFactory;
import com.ruoyi.common.exception.ServiceException;
import com.ruoyi.system.domain.operation.ebay.EbayItemDetail;
import com.ruoyi.system.domain.operation.ebay.EbayPriceSearchRequest;
import com.ruoyi.system.domain.operation.ebay.EbaySkuOeMapping;
import com.ruoyi.system.mapper.operation.EbaySkuOeMappingMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.stereotype.Service;

/**
 * eBay SP 价格查询业务服务。
 */
@Service
public class EbayPriceService
{
    private static final Logger LOG = LoggerFactory.getLogger(EbayPriceService.class);
    private static final Pattern IMAGE_SIZE_PATTERN = Pattern.compile("s-l\\d+", Pattern.CASE_INSENSITIVE);
    private static final Set<String> SUPPORTED_SITES = Set.of("de", "uk", "us");
    private static final Set<String> SUPPORTED_INPUT_TYPES = Set.of("auto", "sku", "oe");

    private final EbaySkuOeMappingMapper mapper;
    private final EbayBrowseApiClient apiClient;
    private final EbayProperties properties;
    private final ThreadPoolTaskExecutor searchExecutor;
    private final ThreadPoolTaskExecutor detailExecutor;

    public EbayPriceService(EbaySkuOeMappingMapper mapper, EbayBrowseApiClient apiClient,
            EbayProperties properties,
            @Qualifier("ebaySearchExecutor") ThreadPoolTaskExecutor searchExecutor,
            @Qualifier("ebayDetailExecutor") ThreadPoolTaskExecutor detailExecutor)
    {
        this.mapper = mapper;
        this.apiClient = apiClient;
        this.properties = properties;
        this.searchExecutor = searchExecutor;
        this.detailExecutor = detailExecutor;
    }

    public Map<String, Object> search(EbayPriceSearchRequest request, String requestId)
    {
        long started = System.currentTimeMillis();
        if (request == null)
        {
            throw new ServiceException("查询参数不能为空");
        }
        String site = normalize(request.getSite(), "de");
        String inputType = normalize(request.getInputType(), "auto");
        if (!SUPPORTED_SITES.contains(site))
        {
            throw new ServiceException("不支持的 eBay 站点: " + site);
        }
        if (!SUPPORTED_INPUT_TYPES.contains(inputType))
        {
            throw new ServiceException("inputType 仅支持 auto、sku、oe");
        }
        List<String> keywords = normalizeKeywords(request.getKeywords());
        if (keywords.isEmpty())
        {
            throw new ServiceException("请输入至少一个 SKU 或 OE 号");
        }
        if (keywords.size() > Math.max(1, properties.getSearchMaxKeywords()))
        {
            throw new ServiceException("单次最多查询 " + properties.getSearchMaxKeywords() + " 个关键词");
        }

        LinkedHashMap<String, List<String>> skuMapping = new LinkedHashMap<>();
        List<String> notFoundSkus = new ArrayList<>();
        List<String> oeList = new ArrayList<>();
        if ("oe".equals(inputType))
        {
            oeList.addAll(keywords);
        }
        else
        {
            Map<String, List<String>> databaseMappings = loadMappings(keywords);
            for (String keyword : keywords)
            {
                List<String> oes = databaseMappings.get(key(keyword));
                if (oes != null && !oes.isEmpty())
                {
                    skuMapping.put(keyword, oes);
                    oeList.addAll(oes);
                }
                else if ("sku".equals(inputType))
                {
                    notFoundSkus.add(keyword);
                }
                else
                {
                    oeList.add(keyword);
                }
            }
            if ("sku".equals(inputType) && oeList.isEmpty())
            {
                throw new ServiceException("未找到任何 SKU 对应的 OE 号");
            }
        }
        oeList = unique(oeList);
        if (oeList.isEmpty())
        {
            throw new ServiceException("未解析到可查询的 OE 号");
        }

        List<CompletableFuture<Map<String, Object>>> futures = new ArrayList<>();
        for (String oe : oeList)
        {
            futures.add(CompletableFuture.supplyAsync(() -> searchOneOe(oe, site), searchExecutor));
        }
        List<Map<String, Object>> results = new ArrayList<>();
        try
        {
            for (CompletableFuture<Map<String, Object>> future : futures)
            {
                results.add(future.join());
            }
        }
        catch (CompletionException e)
        {
            Throwable cause = e.getCause();
            if (cause instanceof ServiceException serviceException)
            {
                throw serviceException;
            }
            throw new ServiceException("eBay 价格查询失败: "
                    + (cause == null ? e.getMessage() : cause.getMessage()));
        }

        LinkedHashMap<String, Object> response = new LinkedHashMap<>();
        response.put("site", site);
        response.put("inputType", inputType);
        response.put("oeList", oeList);
        response.put("skuMapping", skuMapping);
        response.put("notFoundSkus", notFoundSkus);
        response.put("results", results);
        int itemCount = results.stream().mapToInt(row -> ((Number) row.get("count")).intValue()).sum();
        LOG.info("eBay价格查询完成 requestId={}, site={}, oeCount={}, itemCount={}, costMs={}",
                requestId, site, oeList.size(), itemCount, System.currentTimeMillis() - started);
        return response;
    }

    private Map<String, Object> searchOneOe(String oe, String site)
    {
        int groupSize = Math.min(Math.max(properties.getSearchTopN(), 1), 10);
        JsonNode highPayload = apiClient.searchItems(oe, site, "-price", groupSize);
        JsonNode lowPayload = apiClient.searchItems(oe, site, "price", groupSize);
        List<JsonNode> highCandidates = priceCandidates(highPayload, true, groupSize);
        List<JsonNode> lowCandidates = priceCandidates(lowPayload, false, groupSize);

        LinkedHashMap<String, JsonNode> uniqueCandidates = new LinkedHashMap<>();
        for (JsonNode candidate : highCandidates)
        {
            uniqueCandidates.putIfAbsent(candidateKey(candidate), candidate);
        }
        for (JsonNode candidate : lowCandidates)
        {
            uniqueCandidates.putIfAbsent(candidateKey(candidate), candidate);
        }

        List<CompletableFuture<EbayItemDetail>> futures = new ArrayList<>();
        List<String> candidateKeys = new ArrayList<>();
        for (Map.Entry<String, JsonNode> entry : uniqueCandidates.entrySet())
        {
            candidateKeys.add(entry.getKey());
            futures.add(CompletableFuture.supplyAsync(
                    () -> formatWithDetails(entry.getValue(), oe, site), detailExecutor));
        }
        LinkedHashMap<String, EbayItemDetail> itemByCandidateKey = new LinkedHashMap<>();
        for (int index = 0; index < futures.size(); index++)
        {
            itemByCandidateKey.put(candidateKeys.get(index), futures.get(index).join());
        }

        List<EbayItemDetail> highPriceItems = resolveItems(
                highCandidates, itemByCandidateKey, true);
        List<EbayItemDetail> lowPriceItems = resolveItems(
                lowCandidates, itemByCandidateKey, false);
        List<EbayItemDetail> items = uniqueItems(highPriceItems, lowPriceItems);
        long incomplete = items.stream().filter(item -> !item.isImageDetailComplete()).count();

        LinkedHashMap<String, Object> result = new LinkedHashMap<>();
        result.put("oe", oe);
        result.put("count", items.size());
        result.put("items", items);
        result.put("priceGroupSize", groupSize);
        result.put("highPriceCount", highPriceItems.size());
        result.put("lowPriceCount", lowPriceItems.size());
        result.put("highPriceItems", highPriceItems);
        result.put("lowPriceItems", lowPriceItems);
        if (items.isEmpty())
        {
            result.put("warning", "OE '" + oe + "' 未找到结果");
        }
        else if (incomplete > 0)
        {
            result.put("warning", incomplete + " 件商品详情读取失败，已回退使用搜索摘要图片");
        }
        else
        {
            result.put("warning", null);
        }
        return result;
    }

    /**
     * 批量人工审核只查询最低价组，避免高价查询和无用详情请求造成额外等待。
     */
    public List<EbayItemDetail> searchLowestItems(String oe, String site)
    {
        String normalizedOe = oe == null ? "" : oe.trim();
        String normalizedSite = normalize(site, "de");
        if (normalizedOe.isEmpty())
        {
            throw new ServiceException("OE号不能为空");
        }
        if (!SUPPORTED_SITES.contains(normalizedSite))
        {
            throw new ServiceException("不支持的 eBay 站点: " + normalizedSite);
        }
        int groupSize = Math.min(Math.max(properties.getSearchTopN(), 1), 10);
        JsonNode payload = apiClient.searchItems(normalizedOe, normalizedSite, "price", groupSize);
        List<JsonNode> candidates = priceCandidates(payload, false, groupSize);
        List<CompletableFuture<EbayItemDetail>> futures = new ArrayList<>();
        for (JsonNode candidate : candidates)
        {
            futures.add(CompletableFuture.supplyAsync(
                    () -> formatWithDetails(candidate, normalizedOe, normalizedSite), detailExecutor));
        }
        List<EbayItemDetail> items = new ArrayList<>();
        for (CompletableFuture<EbayItemDetail> future : futures)
        {
            items.add(future.join());
        }
        items.sort(Comparator.comparing(EbayItemDetail::getPf));
        return items;
    }

    static List<JsonNode> priceCandidates(JsonNode payload, boolean descending, int limit)
    {
        List<JsonNode> candidates = new ArrayList<>();
        JsonNode summaries = payload == null ? null : payload.path("itemSummaries");
        if (summaries != null && summaries.isArray())
        {
            summaries.forEach(candidate -> {
                if (candidate.has("price") && priceValue(candidate).compareTo(BigDecimal.ZERO) > 0)
                {
                    candidates.add(candidate);
                }
            });
        }
        Comparator<JsonNode> comparator = Comparator.comparing(EbayPriceService::priceValue);
        candidates.sort(descending ? comparator.reversed() : comparator);
        int safeLimit = Math.min(candidates.size(), Math.max(limit, 1));
        return new ArrayList<>(candidates.subList(0, safeLimit));
    }

    private static List<EbayItemDetail> resolveItems(
            List<JsonNode> candidates, Map<String, EbayItemDetail> itemByCandidateKey,
            boolean descending)
    {
        List<EbayItemDetail> items = new ArrayList<>();
        for (JsonNode candidate : candidates)
        {
            EbayItemDetail item = itemByCandidateKey.get(candidateKey(candidate));
            if (item != null)
            {
                items.add(item);
            }
        }
        Comparator<EbayItemDetail> comparator = Comparator.comparing(EbayItemDetail::getPf);
        items.sort(descending ? comparator.reversed() : comparator);
        return items;
    }

    private static List<EbayItemDetail> uniqueItems(
            List<EbayItemDetail> highPriceItems, List<EbayItemDetail> lowPriceItems)
    {
        LinkedHashMap<String, EbayItemDetail> result = new LinkedHashMap<>();
        for (EbayItemDetail item : highPriceItems)
        {
            result.putIfAbsent(itemKey(item), item);
        }
        for (EbayItemDetail item : lowPriceItems)
        {
            result.putIfAbsent(itemKey(item), item);
        }
        return new ArrayList<>(result.values());
    }

    private static String candidateKey(JsonNode source)
    {
        String itemId = text(source, "itemId");
        if (!itemId.isBlank())
        {
            return "ID:" + itemId;
        }
        return "FALLBACK:" + text(source, "itemWebUrl") + "|"
                + text(source, "title") + "|" + priceValue(source);
    }

    private static String itemKey(EbayItemDetail item)
    {
        if (item.getItemId() != null && !item.getItemId().isBlank())
        {
            return "ID:" + item.getItemId();
        }
        return "FALLBACK:" + item.getLink() + "|" + item.getTitle() + "|" + item.getPf();
    }

    private EbayItemDetail formatWithDetails(JsonNode summary, String oe, String site)
    {
        String itemId = text(summary, "itemId");
        JsonNode source = summary;
        boolean detailComplete = false;
        String detailError = null;
        if (!itemId.isBlank())
        {
            try
            {
                JsonNode detail = apiClient.getItem(itemId, site);
                ObjectNode merged = summary != null && summary.isObject()
                        ? ((ObjectNode) summary).deepCopy()
                        : JsonNodeFactory.instance.objectNode();
                if (detail != null && detail.isObject())
                {
                    merged.setAll((ObjectNode) detail);
                }
                source = merged;
                detailComplete = true;
            }
            catch (Exception e)
            {
                detailError = e.getMessage();
            }
        }
        EbayItemDetail item = formatItem(source);
        item.setOe(oe);
        item.setImageDetailComplete(detailComplete);
        item.setImageDetailError(detailError);
        return item;
    }

    static EbayItemDetail formatItem(JsonNode source)
    {
        EbayItemDetail item = new EbayItemDetail();
        BigDecimal price = priceValue(source);
        String currency = source.path("price").path("currency").asText("");
        item.setTitle(text(source, "title"));
        item.setPf(price);
        item.setCurrency(currency);
        item.setPrice(price.setScale(2, RoundingMode.HALF_UP).toPlainString()
                + (currency.isBlank() ? "" : " " + currency));
        item.setEstimatedSoldQuantity(estimatedSoldQuantity(source));
        item.setCondition(text(source, "condition"));
        item.setConditionId(text(source, "conditionId"));
        item.setImages(images(source));
        item.setLink(cleanItemUrl(text(source, "itemWebUrl")));
        item.setItemId(text(source, "itemId"));
        item.setProductId(productId(source));
        item.setSeller(source.path("seller").path("username").asText(""));
        item.setSellerFeedback(source.path("seller").path("feedbackPercentage").asText(""));
        item.setShipping(shipping(source, currency));
        List<String> buyingOptions = new ArrayList<>();
        JsonNode options = source.path("buyingOptions");
        if (options.isArray())
        {
            options.forEach(option -> buyingOptions.add(option.asText("")));
        }
        item.setBuyingOptions(buyingOptions);
        return item;
    }

    private Map<String, List<String>> loadMappings(List<String> keywords)
    {
        LinkedHashMap<String, List<String>> result = new LinkedHashMap<>();
        for (EbaySkuOeMapping mapping : mapper.selectBySkus(keywords))
        {
            result.computeIfAbsent(key(mapping.getSku()), ignored -> new ArrayList<>()).add(mapping.getOe());
        }
        return result;
    }

    static List<String> normalizeKeywords(List<String> keywords)
    {
        List<String> values = new ArrayList<>();
        if (keywords != null)
        {
            for (String keyword : keywords)
            {
                values.addAll(EbaySkuOeImportService.splitValues(keyword));
            }
        }
        return unique(values);
    }

    private static List<String> unique(List<String> values)
    {
        LinkedHashMap<String, String> unique = new LinkedHashMap<>();
        for (String value : values)
        {
            if (value != null && !value.trim().isEmpty())
            {
                unique.putIfAbsent(key(value), value.trim());
            }
        }
        return new ArrayList<>(unique.values());
    }

    private static List<String> images(JsonNode source)
    {
        LinkedHashSet<String> values = new LinkedHashSet<>();
        addImage(values, source.path("image").path("imageUrl").asText(""));
        addImages(values, source.path("additionalImages"));
        addImages(values, source.path("thumbnailImages"));
        return new ArrayList<>(values);
    }

    private static void addImages(Set<String> target, JsonNode nodes)
    {
        if (nodes.isArray())
        {
            nodes.forEach(node -> addImage(target, node.path("imageUrl").asText("")));
        }
    }

    private static void addImage(Set<String> target, String value)
    {
        if (value != null && !value.isBlank())
        {
            target.add(IMAGE_SIZE_PATTERN.matcher(value).replaceAll("s-l500"));
        }
    }

    private static Integer estimatedSoldQuantity(JsonNode source)
    {
        Integer result = null;
        JsonNode values = source.path("estimatedAvailabilities");
        if (values.isArray())
        {
            for (JsonNode value : values)
            {
                JsonNode quantity = value.get("estimatedSoldQuantity");
                if (quantity == null || quantity.isNull())
                {
                    continue;
                }
                try
                {
                    int parsed = Math.max(Integer.parseInt(quantity.asText()), 0);
                    result = result == null ? parsed : Math.max(result, parsed);
                }
                catch (NumberFormatException ignored)
                {
                    // eBay 未返回有效整数时保持 null 语义。
                }
            }
        }
        return result;
    }

    private static String shipping(JsonNode source, String defaultCurrency)
    {
        JsonNode options = source.path("shippingOptions");
        if (!options.isArray() || options.isEmpty())
        {
            return "";
        }
        JsonNode cost = options.get(0).path("shippingCost");
        if (cost.isMissingNode() || cost.isNull() || !cost.has("value"))
        {
            return "";
        }
        BigDecimal value = decimal(cost.path("value").asText("0"));
        if (value.compareTo(BigDecimal.ZERO) <= 0)
        {
            return "免运费";
        }
        String currency = cost.path("currency").asText(defaultCurrency == null ? "" : defaultCurrency);
        return value.setScale(2, RoundingMode.HALF_UP).toPlainString()
                + (currency.isBlank() ? "" : " " + currency);
    }

    private static BigDecimal priceValue(JsonNode source)
    {
        return source == null ? BigDecimal.ZERO : decimal(source.path("price").path("value").asText("0"));
    }

    private static BigDecimal decimal(String value)
    {
        try
        {
            return new BigDecimal(value == null || value.isBlank() ? "0" : value);
        }
        catch (NumberFormatException e)
        {
            return BigDecimal.ZERO;
        }
    }

    private static String cleanItemUrl(String url)
    {
        if (url == null)
        {
            return "";
        }
        int itemIndex = url.indexOf("/itm/");
        if (itemIndex < 0)
        {
            return url;
        }
        int queryIndex = url.indexOf('?', itemIndex);
        int hashIndex = url.indexOf('#', itemIndex);
        int end = url.length();
        if (queryIndex >= 0)
        {
            end = Math.min(end, queryIndex);
        }
        if (hashIndex >= 0)
        {
            end = Math.min(end, hashIndex);
        }
        return url.substring(0, end);
    }

    /**
     * 页面、Excel 和图片文件夹统一使用可在 Windows 文件系统中保存的商品ID。
     * Browse API 的 itemId 通常为 v1|legacyId|variationId，优先取 legacyItemId。
     */
    private static String productId(JsonNode source)
    {
        String legacyItemId = text(source, "legacyItemId").trim();
        if (!legacyItemId.isEmpty())
        {
            return safeFileName(legacyItemId);
        }
        String itemId = text(source, "itemId").trim();
        String[] parts = itemId.split("\\|", -1);
        if (parts.length >= 2 && !parts[1].isBlank())
        {
            return safeFileName(parts[1]);
        }
        return safeFileName(itemId);
    }

    private static String safeFileName(String value)
    {
        if (value == null)
        {
            return "";
        }
        String safe = value.trim().replaceAll("[\\\\/:*?\"<>|]", "_");
        safe = safe.replaceAll("[. ]+$", "");
        return safe.length() <= 120 ? safe : safe.substring(0, 120);
    }

    private static String text(JsonNode source, String field)
    {
        return source == null ? "" : source.path(field).asText("");
    }

    private static String key(String value)
    {
        return value == null ? "" : value.trim().toUpperCase(Locale.ROOT);
    }

    private static String normalize(String value, String defaultValue)
    {
        return value == null || value.trim().isEmpty()
                ? defaultValue
                : value.trim().toLowerCase(Locale.ROOT);
    }
}
