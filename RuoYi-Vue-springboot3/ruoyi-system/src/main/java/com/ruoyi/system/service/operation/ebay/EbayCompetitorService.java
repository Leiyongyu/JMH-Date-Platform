package com.ruoyi.system.service.operation.ebay;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.net.URI;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import com.fasterxml.jackson.databind.JsonNode;
import com.ruoyi.common.exception.ServiceException;
import com.ruoyi.system.domain.operation.ebay.EbayCompetitorFormulaConfig;
import com.ruoyi.system.domain.operation.ebay.EbayCompetitorProduct;
import com.ruoyi.system.domain.operation.ebay.EbayCompetitorProductImage;
import com.ruoyi.system.mapper.operation.EbayCompetitorMapper;
import com.ruoyi.system.service.operation.ebay.EbayCompetitorImageStore.StoredImage;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import org.springframework.util.StringUtils;

/** eBay竞品链接查询、利润计算与商品库保存。 */
@Service
public class EbayCompetitorService
{
    private static final Pattern ITEM_PATH = Pattern.compile(
            "(?:^|/)itm/(?:[^/]+/)?(\\d{9,15})(?:/|$)", Pattern.CASE_INSENSITIVE);

    private final EbayBrowseApiClient browseApiClient;
    private final EbayCompetitorMapper mapper;
    private final EbayCompetitorCalculator calculator;
    private final EbayCompetitorImageStore imageStore;

    public EbayCompetitorService(EbayBrowseApiClient browseApiClient,
            EbayCompetitorMapper mapper, EbayCompetitorCalculator calculator,
            EbayCompetitorImageStore imageStore)
    {
        this.browseApiClient = browseApiClient;
        this.mapper = mapper;
        this.calculator = calculator;
        this.imageStore = imageStore;
    }

    public List<EbayCompetitorProduct> listProducts(EbayCompetitorProduct query)
    {
        EbayCompetitorProduct normalized = query == null ? new EbayCompetitorProduct() : query;
        normalized.setOe(trimToNull(normalized.getOe()));
        normalized.setSku(trimToNull(normalized.getSku()));
        if (StringUtils.hasText(normalized.getSiteCode()))
        {
            normalized.setSiteCode(normalized.getSiteCode().trim().toUpperCase(Locale.ROOT));
        }
        List<EbayCompetitorProduct> products = mapper.selectProductList(normalized);
        Map<String, EbayCompetitorFormulaConfig> configs = new LinkedHashMap<>();
        for (EbayCompetitorProduct product : products)
        {
            String siteCode = product.getSiteCode();
            if (!configs.containsKey(siteCode))
            {
                configs.put(siteCode, mapper.selectFormulaConfig(siteCode));
            }
            product.setFormulaConfig(configs.get(siteCode));
        }
        return products;
    }

    public Map<String, Object> queryByUrl(String rawUrl)
    {
        ParsedLink link = parseLink(rawUrl);
        JsonNode item = browseApiClient.getItemByLegacyId(
                link.legacyItemId(), link.legacyVariationId(), link.site());
        EbayCompetitorFormulaConfig config = requireConfig(link.siteCode());

        LinkedHashMap<String, Object> result = new LinkedHashMap<>();
        result.put("sourceUrl", link.sourceUrl());
        result.put("siteCode", link.siteCode());
        result.put("marketplaceId", text(item, "listingMarketplaceId", link.marketplaceId()));
        result.put("ebayItemId", text(item, "legacyItemId", link.legacyItemId()));
        result.put("referenceUrl", text(item, "itemWebUrl", link.sourceUrl()));
        result.put("salePrice", decimal(item.path("price"), "value", "eBay商品售价"));
        result.put("currency", text(item.path("price"), "currency", config.getCurrency()));
        List<String> imageUrls = imageUrls(item);
        result.put("remoteImageUrl", imageUrls.isEmpty() ? null : imageUrls.get(0));
        result.put("remoteImageUrls", imageUrls);
        result.put("imageCount", imageUrls.size());
        result.put("formulaConfig", config);
        return result;
    }

    @Transactional(rollbackFor = Exception.class)
    public EbayCompetitorProduct saveProduct(EbayCompetitorProduct product, String username)
    {
        if (product == null)
        {
            throw new ServiceException("保存参数不能为空");
        }
        ParsedLink link = parseLink(product.getReferenceUrl());
        product.setSiteCode(link.siteCode());
        product.setMarketplaceId(link.marketplaceId());
        product.setEbayItemId(link.legacyItemId());
        product.setReferenceUrl(link.sourceUrl());
        normalizeManualFields(product);

        if (mapper.selectBySiteAndItemId(product.getSiteCode(), product.getEbayItemId()) != null)
        {
            throw new ServiceException("该站点商品已保存，请到商品库中查询，不能重复保存");
        }

        EbayCompetitorFormulaConfig config = requireConfig(product.getSiteCode());
        JsonNode item = browseApiClient.getItemByLegacyId(
                link.legacyItemId(), link.legacyVariationId(), link.site());
        product.setMarketplaceId(text(item, "listingMarketplaceId", link.marketplaceId()));
        product.setSalePrice(twoDecimals(decimal(item.path("price"), "value", "eBay商品售价")));
        product.setCurrency(text(item.path("price"), "currency", config.getCurrency()));
        List<String> remoteImages = imageUrls(item);
        product.setRemoteImageUrls(remoteImages);
        product.setRemoteImageUrl(remoteImages.isEmpty() ? null : remoteImages.get(0));
        String canonicalUrl = text(item, "itemWebUrl");
        if (StringUtils.hasText(canonicalUrl))
        {
            product.setReferenceUrl(canonicalUrl);
        }

        validate(product, config);
        calculator.calculate(product, config);
        product.setCreateBy(StringUtils.hasText(username) ? username.trim() : "SYSTEM");

        List<StoredImage> storedImages = new ArrayList<>();
        try
        {
            if (remoteImages.isEmpty())
            {
                throw new ServiceException("eBay商品没有返回图片，无法保存");
            }
            for (int index = 0; index < remoteImages.size(); index++)
            {
                storedImages.add(imageStore.download(remoteImages.get(index),
                        product.getSiteCode(), product.getEbayItemId(), index + 1));
            }
            product.setLocalImageUrl(storedImages.get(0).resourceUrl());
            mapper.insertProduct(product);

            List<EbayCompetitorProductImage> productImages = new ArrayList<>();
            for (int index = 0; index < storedImages.size(); index++)
            {
                EbayCompetitorProductImage image = new EbayCompetitorProductImage();
                image.setProductId(product.getId());
                image.setSortNo(index + 1);
                image.setLocalImageUrl(storedImages.get(index).resourceUrl());
                mapper.insertProductImage(image);
                productImages.add(image);
            }
            product.setImages(productImages);
            product.setRemoteImageUrl(null);
            product.setRemoteImageUrls(null);
            return product;
        }
        catch (DuplicateKeyException e)
        {
            storedImages.forEach(imageStore::deleteQuietly);
            throw new ServiceException("该站点商品已保存，不能重复保存");
        }
        catch (RuntimeException e)
        {
            storedImages.forEach(imageStore::deleteQuietly);
            throw e;
        }
    }

    @Transactional(rollbackFor = Exception.class)
    public EbayCompetitorProduct updateProduct(Long id, EbayCompetitorProduct changes, String username)
    {
        if (id == null || changes == null)
        {
            throw new ServiceException("编辑参数不能为空");
        }
        EbayCompetitorProduct product = mapper.selectProductById(id);
        if (product == null)
        {
            throw new ServiceException("竞品商品不存在或已被删除");
        }

        product.setOe(changes.getOe());
        product.setSku(changes.getSku());
        product.setRemark(changes.getRemark());
        product.setSalePrice(changes.getSalePrice());
        product.setProductCostCny(changes.getProductCostCny());
        product.setLengthCm(changes.getLengthCm());
        product.setWidthCm(changes.getWidthCm());
        product.setHeightCm(changes.getHeightCm());
        product.setActualWeightKg(changes.getActualWeightKg());
        product.setExchangeRate(changes.getExchangeRate());
        product.setTargetProfitRate(changes.getTargetProfitRate());
        normalizeManualFields(product);

        EbayCompetitorFormulaConfig config = requireConfig(product.getSiteCode());
        validate(product, config);
        calculator.calculate(product, config);
        product.setUpdateBy(StringUtils.hasText(username) ? username.trim() : "SYSTEM");
        if (mapper.updateProduct(product) != 1)
        {
            throw new ServiceException("竞品商品更新失败，请刷新后重试");
        }
        EbayCompetitorProduct updated = mapper.selectProductById(id);
        updated.setFormulaConfig(config);
        return updated;
    }

    @Transactional(rollbackFor = Exception.class)
    public int deleteProduct(Long id)
    {
        if (id == null)
        {
            throw new ServiceException("商品ID不能为空");
        }
        EbayCompetitorProduct product = mapper.selectProductById(id);
        if (product == null)
        {
            throw new ServiceException("竞品商品不存在或已被删除");
        }
        Set<String> imageUrls = new LinkedHashSet<>();
        if (StringUtils.hasText(product.getLocalImageUrl()))
        {
            imageUrls.add(product.getLocalImageUrl());
        }
        if (product.getImages() != null)
        {
            product.getImages().stream()
                    .map(EbayCompetitorProductImage::getLocalImageUrl)
                    .filter(StringUtils::hasText)
                    .forEach(imageUrls::add);
        }
        int rows = mapper.deleteProductById(id);
        if (rows != 1)
        {
            throw new ServiceException("竞品商品删除失败，请刷新后重试");
        }
        TransactionSynchronizationManager.registerSynchronization(new TransactionSynchronization()
        {
            @Override
            public void afterCommit()
            {
                imageUrls.forEach(imageStore::deleteByResourceUrlQuietly);
            }
        });
        return rows;
    }

    private EbayCompetitorFormulaConfig requireConfig(String siteCode)
    {
        EbayCompetitorFormulaConfig config = mapper.selectFormulaConfig(siteCode);
        if (config == null)
        {
            throw new ServiceException("未配置" + siteCode + "站点的竞品计算公式");
        }
        return config;
    }

    private void validate(EbayCompetitorProduct product, EbayCompetitorFormulaConfig config)
    {
        if (!StringUtils.hasText(product.getOe()) && !StringUtils.hasText(product.getSku()))
        {
            throw new ServiceException("OE号和SKU至少填写一个");
        }
        positive(product.getSalePrice(), "实际卖价");
        positive(product.getProductCostCny(), "产品成本");
        positive(product.getLengthCm(), "长");
        positive(product.getWidthCm(), "宽");
        positive(product.getHeightCm(), "高");
        positive(product.getActualWeightKg(), "实重");
        positive(product.getExchangeRate(), "实时汇率");
        positive(product.getTargetProfitRate(), "目标利润率");
        if (product.getTargetProfitRate().compareTo(config.getPlatformNetRate()) >= 0)
        {
            throw new ServiceException("目标利润率必须小于平台净收入比例"
                    + config.getPlatformNetRate().stripTrailingZeros().toPlainString());
        }
    }

    private void normalizeManualFields(EbayCompetitorProduct product)
    {
        product.setOe(clean(product.getOe(), 500, "OE号"));
        product.setSku(clean(product.getSku(), 255, "SKU"));
        product.setRemark(clean(product.getRemark(), 1000, "备注"));
        product.setSalePrice(twoDecimals(product.getSalePrice()));
        product.setProductCostCny(twoDecimals(product.getProductCostCny()));
        product.setLengthCm(twoDecimals(product.getLengthCm()));
        product.setWidthCm(twoDecimals(product.getWidthCm()));
        product.setHeightCm(twoDecimals(product.getHeightCm()));
        product.setActualWeightKg(twoDecimals(product.getActualWeightKg()));
        product.setExchangeRate(twoDecimals(product.getExchangeRate()));
        product.setTargetProfitRate(rateFromPercent(product.getTargetProfitRate()));
    }

    private static BigDecimal twoDecimals(BigDecimal value)
    {
        return value == null ? null : value.setScale(2, RoundingMode.HALF_UP);
    }

    /** 前端利润率按百分比保留2位，换成比例后需要保留4位。 */
    private static BigDecimal rateFromPercent(BigDecimal value)
    {
        return value == null ? null : value.setScale(4, RoundingMode.HALF_UP);
    }

    private ParsedLink parseLink(String rawUrl)
    {
        if (!StringUtils.hasText(rawUrl))
        {
            throw new ServiceException("请输入eBay商品链接");
        }
        String value = rawUrl.trim();
        try
        {
            URI uri = URI.create(value);
            String scheme = uri.getScheme();
            if (!("https".equalsIgnoreCase(scheme) || "http".equalsIgnoreCase(scheme)))
            {
                throw new ServiceException("eBay商品链接必须以http://或https://开头");
            }
            String host = uri.getHost();
            if (!StringUtils.hasText(host))
            {
                throw new ServiceException("无法识别eBay商品链接域名");
            }
            String normalizedHost = host.toLowerCase(Locale.ROOT);
            String site;
            String siteCode;
            String marketplaceId;
            if (isHost(normalizedHost, "ebay.co.uk"))
            {
                site = "uk";
                siteCode = "UK";
                marketplaceId = "EBAY_GB";
            }
            else if (isHost(normalizedHost, "ebay.de"))
            {
                site = "de";
                siteCode = "DE";
                marketplaceId = "EBAY_DE";
            }
            else if (isHost(normalizedHost, "ebay.com"))
            {
                site = "us";
                siteCode = "US";
                marketplaceId = "EBAY_US";
            }
            else
            {
                throw new ServiceException("只支持eBay德国站、英国站和美国站商品链接");
            }

            Matcher matcher = ITEM_PATH.matcher(uri.getPath() == null ? "" : uri.getPath());
            if (!matcher.find())
            {
                throw new ServiceException("无法从链接中识别eBay商品ID，请确认链接包含/itm/商品ID");
            }
            String legacyItemId = matcher.group(1);
            String variationId = queryParameter(uri.getRawQuery(), "var");
            if (StringUtils.hasText(variationId) && !variationId.matches("\\d{6,20}"))
            {
                variationId = null;
            }
            return new ParsedLink(value, site, siteCode, marketplaceId, legacyItemId, variationId);
        }
        catch (ServiceException e)
        {
            throw e;
        }
        catch (IllegalArgumentException e)
        {
            throw new ServiceException("eBay商品链接格式不正确");
        }
    }

    private static void positive(BigDecimal value, String label)
    {
        if (value == null || value.compareTo(BigDecimal.ZERO) <= 0)
        {
            throw new ServiceException(label + "必须大于0");
        }
    }

    private static String clean(String value, int maxLength, String label)
    {
        String result = trimToNull(value);
        if (result != null && result.length() > maxLength)
        {
            throw new ServiceException(label + "不能超过" + maxLength + "个字符");
        }
        return result;
    }

    private static String trimToNull(String value)
    {
        if (!StringUtils.hasText(value))
        {
            return null;
        }
        return value.trim();
    }

    private static boolean isHost(String actual, String expected)
    {
        return actual.equals(expected) || actual.endsWith("." + expected);
    }

    private static String queryParameter(String rawQuery, String name)
    {
        if (!StringUtils.hasText(rawQuery))
        {
            return null;
        }
        for (String part : rawQuery.split("&"))
        {
            int separator = part.indexOf('=');
            String key = separator < 0 ? part : part.substring(0, separator);
            if (name.equals(URLDecoder.decode(key, StandardCharsets.UTF_8)))
            {
                String value = separator < 0 ? "" : part.substring(separator + 1);
                return URLDecoder.decode(value, StandardCharsets.UTF_8);
            }
        }
        return null;
    }

    private static String text(JsonNode node, String field)
    {
        return text(node, field, null);
    }

    private static String text(JsonNode node, String field, String fallback)
    {
        JsonNode value = node == null ? null : node.get(field);
        if (value == null || value.isNull() || value.isMissingNode())
        {
            return fallback;
        }
        String result = value.asText("").trim();
        return result.isEmpty() ? fallback : result;
    }

    private static BigDecimal decimal(JsonNode node, String field, String label)
    {
        String value = text(node, field);
        if (!StringUtils.hasText(value))
        {
            throw new ServiceException(label + "为空，无法计算");
        }
        try
        {
            return new BigDecimal(value);
        }
        catch (NumberFormatException e)
        {
            throw new ServiceException(label + "格式不正确");
        }
    }

    private static List<String> imageUrls(JsonNode item)
    {
        Set<String> values = new LinkedHashSet<>();
        String primary = text(item.path("image"), "imageUrl");
        if (StringUtils.hasText(primary))
        {
            values.add(primary);
        }
        JsonNode additional = item.path("additionalImages");
        if (additional.isArray())
        {
            additional.forEach(image -> {
                String url = text(image, "imageUrl");
                if (StringUtils.hasText(url))
                {
                    values.add(url);
                }
            });
        }
        return new ArrayList<>(values);
    }

    private record ParsedLink(String sourceUrl, String site, String siteCode,
            String marketplaceId, String legacyItemId, String legacyVariationId) {}
}
