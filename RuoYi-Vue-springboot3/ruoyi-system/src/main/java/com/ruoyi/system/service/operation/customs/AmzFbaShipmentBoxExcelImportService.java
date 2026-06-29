package com.ruoyi.system.service.operation.customs;

import com.ruoyi.system.domain.operation.external.AmzFbaShipmentBox;
import com.ruoyi.system.domain.operation.external.ShopList;
import com.ruoyi.system.mapper.operation.external.AmzFbaShipmentBoxMapper;
import com.ruoyi.system.mapper.operation.external.ShopListMapper;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import org.apache.poi.ss.usermodel.Cell;
import org.apache.poi.ss.usermodel.DataFormatter;
import org.apache.poi.ss.usermodel.Row;
import org.apache.poi.ss.usermodel.Sheet;
import org.apache.poi.ss.usermodel.Workbook;
import org.apache.poi.ss.usermodel.WorkbookFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.util.StringUtils;
import org.springframework.web.multipart.MultipartFile;

/** 导入领星导出的 FBA 装箱明细 Excel → amz_fba_shipment_box。 */
@Service
public class AmzFbaShipmentBoxExcelImportService
{
    private static final String AMAZON_PLATFORM = "10001";
    private static final int BATCH_SIZE = 500;
    private static final Pattern FIRST_NUMBER = Pattern.compile("\\d+");

    private final AmzFbaShipmentBoxMapper boxMapper;
    private final ShopListMapper shopMapper;

    public AmzFbaShipmentBoxExcelImportService(AmzFbaShipmentBoxMapper boxMapper, ShopListMapper shopMapper)
    {
        this.boxMapper = boxMapper;
        this.shopMapper = shopMapper;
    }

    @Transactional
    public Map<String, Object> importFile(MultipartFile file) throws Exception
    {
        if (file == null || file.isEmpty()) throw new IllegalArgumentException("请选择要导入的 Excel 文件");

        List<ExcelBoxRow> excelRows;
        try (Workbook workbook = WorkbookFactory.create(file.getInputStream()))
        {
            Sheet sheet = findBoxSheet(workbook);
            if (sheet == null) throw new IllegalArgumentException("未找到装箱明细工作表");
            excelRows = parseSheet(sheet);
        }

        Set<String> shipmentIds = new LinkedHashSet<>();
        for (ExcelBoxRow row : excelRows) shipmentIds.add(row.shipmentId);

        Set<String> existingShipmentIds = shipmentIds.isEmpty() ? Set.of()
            : new HashSet<>(boxMapper.selectExistingShipmentIds(new ArrayList<>(shipmentIds)));
        Map<String, Integer> sidByShipment = shipmentIds.isEmpty() ? Map.of()
            : loadSidByShipment(new ArrayList<>(shipmentIds));
        List<ShopList> shops = shopMapper.selectByPlatformStatus(AMAZON_PLATFORM, 1);

        List<AmzFbaShipmentBox> rows = new ArrayList<>();
        Set<String> importedShipments = new LinkedHashSet<>();
        Set<String> skippedShipments = new LinkedHashSet<>();
        Set<String> unmatchedShops = new LinkedHashSet<>();
        int skippedExistingRows = 0;
        int failedRows = 0;

        for (ExcelBoxRow source : excelRows)
        {
            if (existingShipmentIds.contains(source.shipmentId))
            {
                skippedShipments.add(source.shipmentId);
                skippedExistingRows++;
                continue;
            }

            Integer sid = matchSid(source.shopName, shops);
            if (sid == null) sid = sidByShipment.get(source.shipmentId);
            if (sid == null)
            {
                unmatchedShops.add(source.shopName);
                failedRows++;
                continue;
            }

            AmzFbaShipmentBox row = new AmzFbaShipmentBox();
            row.setSid(sid);
            row.setShipmentId(source.shipmentId);
            row.setBoxType(normalizeBoxType(source.boxType));
            row.setBoxLength(source.boxLength);
            row.setBoxWidth(source.boxWidth);
            row.setBoxHeight(source.boxHeight);
            row.setBoxWeight(source.boxWeight);
            row.setBoxVolume(source.boxVolume);
            row.setBoxDimensionsUnit(defaultText(source.boxDimensionsUnit, "cm"));
            row.setBoxWeightUnit(defaultText(source.boxWeightUnit, "kg"));
            row.setBoxNum(source.boxNum);
            row.setMsku(source.msku);
            row.setSku(source.sku);
            row.setProductName(source.productName);
            row.setFulfillmentNetworkSku(source.fnsku);
            row.setQuantityInCase(source.quantityInCase);
            rows.add(row);
            importedShipments.add(source.shipmentId);
        }

        int inserted = 0;
        for (int i = 0; i < rows.size(); i += BATCH_SIZE)
        {
            inserted += boxMapper.batchInsert(rows.subList(i, Math.min(i + BATCH_SIZE, rows.size())));
        }
        int skuMapped = rows.isEmpty() ? 0 : boxMapper.updateSkuFromListing();

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("readRows", excelRows.size());
        result.put("insertedRows", inserted);
        result.put("importedShipments", importedShipments.size());
        result.put("skippedExistingRows", skippedExistingRows);
        result.put("skippedExistingShipments", skippedShipments.size());
        result.put("failedRows", failedRows);
        result.put("skuMapped", skuMapped);
        result.put("unmatchedShops", new ArrayList<>(unmatchedShops));
        return result;
    }

    private Sheet findBoxSheet(Workbook workbook)
    {
        Sheet sheet = workbook.getSheet("装箱明细");
        return sheet != null ? sheet : (workbook.getNumberOfSheets() > 0 ? workbook.getSheetAt(0) : null);
    }

    private List<ExcelBoxRow> parseSheet(Sheet sheet)
    {
        DataFormatter formatter = new DataFormatter(Locale.CHINA);
        Row header = sheet.getRow(sheet.getFirstRowNum());
        if (header == null) throw new IllegalArgumentException("装箱明细表头为空");
        Map<String, Integer> cols = readHeader(header, formatter);

        List<ExcelBoxRow> rows = new ArrayList<>();
        String currentShipmentId = null;
        String currentShopName = null;
        String currentBoxType = null;
        for (int i = sheet.getFirstRowNum() + 1; i <= sheet.getLastRowNum(); i++)
        {
            Row row = sheet.getRow(i);
            if (row == null) continue;

            String shipmentId = cell(row, cols, "货件单号", formatter);
            if (StringUtils.hasText(shipmentId)) currentShipmentId = shipmentId;
            String shopName = cell(row, cols, "店铺", formatter);
            if (StringUtils.hasText(shopName)) currentShopName = shopName;
            String boxType = cell(row, cols, "装箱方式", formatter);
            if (StringUtils.hasText(boxType)) currentBoxType = boxType;

            String msku = cell(row, cols, "MSKU", formatter);
            String sku = cell(row, cols, "SKU", formatter);
            String fnsku = cell(row, cols, "FNSKU", formatter);
            if (!StringUtils.hasText(msku) && !StringUtils.hasText(sku) && !StringUtils.hasText(fnsku)) continue;
            if (!StringUtils.hasText(currentShipmentId)) continue;

            ExcelBoxRow parsed = new ExcelBoxRow();
            parsed.shipmentId = currentShipmentId;
            parsed.shopName = currentShopName;
            parsed.boxType = currentBoxType;
            parsed.msku = msku;
            parsed.sku = sku;
            parsed.fnsku = fnsku;
            parsed.productName = cell(row, cols, "品名", formatter);
            parsed.quantityInCase = firstText(cell(row, cols, "单箱数量", formatter), cell(row, cols, "申报量", formatter));
            parsed.boxWeight = firstText(cell(row, cols, "箱子毛重", formatter), cell(row, cols, "总重量-箱子", formatter));
            parsed.boxLength = cell(row, cols, "箱子长度", formatter);
            parsed.boxWidth = cell(row, cols, "箱子宽度", formatter);
            parsed.boxHeight = cell(row, cols, "箱子高度", formatter);
            parsed.boxVolume = firstText(cell(row, cols, "总体积-箱子", formatter), cell(row, cols, "总体积", formatter));
            parsed.boxDimensionsUnit = firstText(cell(row, cols, "长度单位", formatter), cell(row, cols, "体积单位", formatter));
            parsed.boxWeightUnit = cell(row, cols, "重量单位", formatter);
            parsed.boxNum = firstInt(cell(row, cols, "箱数", formatter), "1");
            rows.add(parsed);
        }
        return rows;
    }

    private Map<String, Integer> readHeader(Row header, DataFormatter formatter)
    {
        Map<String, Integer> cols = new HashMap<>();
        for (Cell cell : header)
        {
            String text = formatter.formatCellValue(cell).trim();
            if (StringUtils.hasText(text)) cols.put(text, cell.getColumnIndex());
        }
        if (!cols.containsKey("货件单号") || !cols.containsKey("MSKU"))
            throw new IllegalArgumentException("装箱明细表头缺少货件单号或 MSKU");
        return cols;
    }

    private Map<String, Integer> loadSidByShipment(List<String> shipmentIds)
    {
        Map<String, Integer> result = new HashMap<>();
        for (Map<String, Object> row : boxMapper.selectSidByShipmentIds(shipmentIds))
        {
            String shipmentId = objectText(row.getOrDefault("shipment_id", row.get("SHIPMENT_ID")));
            Object sidValue = row.getOrDefault("sid", row.get("SID"));
            Integer sid = sidValue instanceof Number ? ((Number) sidValue).intValue() : firstInt(objectText(sidValue));
            if (StringUtils.hasText(shipmentId) && sid != null) result.put(shipmentId, sid);
        }
        return result;
    }

    private Integer matchSid(String shopName, List<ShopList> shops)
    {
        if (!StringUtils.hasText(shopName)) return null;
        String normalized = normalizeShop(shopName);
        ShopList fuzzy = null;
        for (ShopList shop : shops)
        {
            if (!StringUtils.hasText(shop.getStoreName()) || !StringUtils.hasText(shop.getSid())) continue;
            String candidate = normalizeShop(shop.getStoreName());
            if (candidate.equals(normalized)) return firstInt(shop.getSid());
            if (fuzzy == null && (candidate.contains(normalized) || normalized.contains(candidate))) fuzzy = shop;
        }
        return fuzzy != null ? firstInt(fuzzy.getSid()) : null;
    }

    private String cell(Row row, Map<String, Integer> cols, String name, DataFormatter formatter)
    {
        Integer index = cols.get(name);
        if (index == null) return null;
        Cell cell = row.getCell(index);
        if (cell == null) return null;
        String text = formatter.formatCellValue(cell).trim();
        return StringUtils.hasText(text) && !"-".equals(text) ? text : null;
    }

    private String normalizeBoxType(String value)
    {
        if (!StringUtils.hasText(value)) return null;
        if (value.contains("多款")) return "MULTIPLE";
        if (value.contains("一款") || value.contains("单款")) return "SINGLE";
        return value;
    }

    private String normalizeShop(String value)
    {
        return value == null ? "" : value.replaceAll("\\s+", "").toLowerCase(Locale.ROOT);
    }

    private String firstText(String... values)
    {
        for (String value : values) if (StringUtils.hasText(value)) return value.trim();
        return null;
    }

    private String defaultText(String value, String fallback)
    {
        return StringUtils.hasText(value) ? value : fallback;
    }

    private Integer firstInt(String... values)
    {
        for (String value : values)
        {
            if (!StringUtils.hasText(value)) continue;
            String text = value.trim();
            try { return (int) Double.parseDouble(text); }
            catch (NumberFormatException ignored) {}
            Matcher matcher = FIRST_NUMBER.matcher(text);
            if (matcher.find()) return Integer.valueOf(matcher.group());
        }
        return null;
    }

    private String objectText(Object value)
    {
        return value == null ? null : value.toString();
    }

    private static class ExcelBoxRow
    {
        String shipmentId;
        String shopName;
        String boxType;
        String boxLength;
        String boxWidth;
        String boxHeight;
        String boxWeight;
        String boxVolume;
        String boxDimensionsUnit;
        String boxWeightUnit;
        Integer boxNum;
        String msku;
        String sku;
        String fnsku;
        String productName;
        String quantityInCase;
    }
}
