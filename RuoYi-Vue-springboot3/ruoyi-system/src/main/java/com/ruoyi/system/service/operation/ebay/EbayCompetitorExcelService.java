package com.ruoyi.system.service.operation.ebay;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.math.BigDecimal;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import jakarta.servlet.http.HttpServletResponse;
import org.apache.poi.ss.usermodel.ClientAnchor;
import org.apache.poi.ss.usermodel.CreationHelper;
import org.apache.poi.ss.usermodel.Drawing;
import org.apache.poi.common.usermodel.HyperlinkType;
import org.apache.poi.ss.usermodel.BorderStyle;
import org.apache.poi.ss.usermodel.Cell;
import org.apache.poi.ss.usermodel.CellStyle;
import org.apache.poi.ss.usermodel.DataFormatter;
import org.apache.poi.ss.usermodel.FillPatternType;
import org.apache.poi.ss.usermodel.Font;
import org.apache.poi.ss.usermodel.FormulaEvaluator;
import org.apache.poi.ss.usermodel.HorizontalAlignment;
import org.apache.poi.ss.usermodel.IndexedColors;
import org.apache.poi.ss.usermodel.Row;
import org.apache.poi.ss.usermodel.Sheet;
import org.apache.poi.ss.usermodel.VerticalAlignment;
import org.apache.poi.ss.usermodel.Workbook;
import org.apache.poi.ss.usermodel.WorkbookFactory;
import org.apache.poi.xssf.usermodel.XSSFWorkbook;
import org.apache.poi.util.Units;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;
import com.ruoyi.common.exception.ServiceException;
import com.ruoyi.common.config.RuoYiConfig;
import com.ruoyi.common.constant.Constants;
import com.ruoyi.system.domain.operation.ebay.EbayCompetitorExportRequest;
import com.ruoyi.system.domain.operation.ebay.EbayCompetitorProduct;
import com.ruoyi.system.domain.operation.ebay.EbayCompetitorProductImage;
import com.ruoyi.system.mapper.operation.EbayCompetitorMapper;

/** eBay竞品链接Excel解析与商品库导出。 */
@Service
public class EbayCompetitorExcelService
{
    private static final String LINK_HEADER = "参考链接";
    private static final int MAX_LINKS = 500;
    private static final long MAX_FILE_BYTES = 5L * 1024 * 1024;
    private static final DateTimeFormatter FILE_TIME = DateTimeFormatter.ofPattern("yyyyMMddHHmmss");
    private static final String EXCEL_CONTENT_TYPE =
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
    private static final int IMAGE_START_COLUMN = 23;
    private static final int IMAGE_SIZE_PX = 88;
    private static final int MAX_IMAGE_BYTES = 10 * 1024 * 1024;

    private final EbayCompetitorMapper mapper;

    public EbayCompetitorExcelService(EbayCompetitorMapper mapper)
    {
        this.mapper = mapper;
    }

    /**
     * 只解析链接队列，不在请求线程中批量访问eBay。前端拿到队列后按顺序逐条调用现有查询接口，
     * 可让单条失败不影响后续链接，并持续展示进度。
     */
    public Map<String, Object> parseLinkFile(MultipartFile file)
    {
        checkFile(file);
        try (InputStream input = file.getInputStream(); Workbook workbook = WorkbookFactory.create(input))
        {
            if (workbook.getNumberOfSheets() == 0)
            {
                throw new ServiceException("Excel文件没有工作表");
            }
            Sheet sheet = workbook.getSheetAt(0);
            Row header = sheet.getRow(sheet.getFirstRowNum());
            if (header == null)
            {
                throw new ServiceException("Excel文件为空");
            }
            DataFormatter formatter = new DataFormatter(Locale.ROOT);
            FormulaEvaluator evaluator = workbook.getCreationHelper().createFormulaEvaluator();
            String actualHeader = cellText(header, 0, formatter, evaluator);
            if (!LINK_HEADER.equals(actualHeader.trim()))
            {
                throw new ServiceException("Excel A1表头应为“参考链接”，实际为“" + actualHeader + "”");
            }

            Set<String> unique = new LinkedHashSet<>();
            int totalRows = 0;
            int blankRows = 0;
            int duplicateLinks = 0;
            for (int rowIndex = header.getRowNum() + 1; rowIndex <= sheet.getLastRowNum(); rowIndex++)
            {
                totalRows++;
                String link = cellText(sheet.getRow(rowIndex), 0, formatter, evaluator).trim();
                if (link.isEmpty())
                {
                    blankRows++;
                    continue;
                }
                if (link.length() > 2048)
                {
                    throw new ServiceException("Excel第 " + (rowIndex + 1) + " 行链接超过2048个字符");
                }
                if (!unique.add(link))
                {
                    duplicateLinks++;
                }
                if (unique.size() > MAX_LINKS)
                {
                    throw new ServiceException("单次最多导入" + MAX_LINKS + "个商品链接，请拆分文件后重试");
                }
            }
            if (unique.isEmpty())
            {
                throw new ServiceException("Excel A列没有读取到商品链接");
            }

            Map<String, Object> result = new LinkedHashMap<>();
            result.put("fileName", file.getOriginalFilename());
            result.put("totalRows", totalRows);
            result.put("uniqueLinks", unique.size());
            result.put("blankRows", blankRows);
            result.put("duplicateLinks", duplicateLinks);
            result.put("links", new ArrayList<>(unique));
            return result;
        }
        catch (ServiceException e)
        {
            throw e;
        }
        catch (Exception e)
        {
            throw new ServiceException("竞品链接Excel解析失败：" + friendlyError(e));
        }
    }

    public void exportProducts(EbayCompetitorExportRequest request, HttpServletResponse response)
    {
        boolean exportAll = request != null && request.isExportAll();
        List<Long> ids = normalizeIds(request == null ? null : request.getIds());
        if (!exportAll && ids.isEmpty())
        {
            throw new ServiceException("请先选择需要导出的商品");
        }
        List<EbayCompetitorProduct> products = mapper.selectProductsForExport(exportAll ? null : ids);
        if (products.isEmpty())
        {
            throw new ServiceException("没有可导出的竞品商品");
        }
        Map<Long, List<EbayCompetitorProductImage>> images = loadProductImages(products);
        String fileName = "eBay竞品商品库_" + LocalDateTime.now().format(FILE_TIME) + ".xlsx";
        try
        {
            byte[] bytes = buildWorkbook(products, images);
            String encoded = URLEncoder.encode(fileName, StandardCharsets.UTF_8).replace("+", "%20");
            response.setContentType(EXCEL_CONTENT_TYPE);
            response.setCharacterEncoding(StandardCharsets.UTF_8.name());
            response.setHeader("Content-Disposition", "attachment; filename*=UTF-8''" + encoded);
            response.setContentLength(bytes.length);
            response.getOutputStream().write(bytes);
            response.flushBuffer();
        }
        catch (ServiceException e)
        {
            throw e;
        }
        catch (Exception e)
        {
            throw new ServiceException("竞品商品库导出失败：" + friendlyError(e));
        }
    }

    private byte[] buildWorkbook(List<EbayCompetitorProduct> products,
            Map<Long, List<EbayCompetitorProductImage>> productImages) throws Exception
    {
        try (Workbook workbook = new XSSFWorkbook(); ByteArrayOutputStream output = new ByteArrayOutputStream())
        {
            Sheet sheet = workbook.createSheet("竞品商品库");
            sheet.createFreezePane(0, 1);
            String[] fixedHeaders = {
                    "商品ID/编号", "站点", "Marketplace", "币种", "OE号", "SKU", "参考链接", "备注",
                    "实际卖价", "产品成本(¥)", "长(cm)", "宽(cm)", "高(cm)", "体积重(kg)", "实重(kg)",
                    "实时汇率", "海运底价", "铁路底价", "海运利润率", "铁路利润率", "目标利润率",
                    "目标产品成本(海运)", "目标产品成本(铁路)"
            };
            int[] fixedWidths = {
                    18, 10, 16, 10, 24, 22, 48, 30, 14, 14, 11, 11, 11, 14, 12,
                    12, 14, 14, 14, 14, 14, 20, 20
            };
            int maxImageCount = Math.max(1,
                    productImages.values().stream().mapToInt(List::size).max().orElse(0));
            List<String> headers = new ArrayList<>(List.of(fixedHeaders));
            for (int imageIndex = 1; imageIndex <= maxImageCount; imageIndex++)
            {
                headers.add(imageIndex == 1 ? "图片" : "图片" + imageIndex);
            }
            CellStyle headerStyle = headerStyle(workbook);
            CellStyle textStyle = textStyle(workbook);
            CellStyle wrapStyle = wrapStyle(workbook);
            CellStyle imageCellStyle = imageCellStyle(workbook);
            CellStyle decimalStyle = decimalStyle(workbook, "#,##0.00");
            CellStyle rateStyle = decimalStyle(workbook, "0.00%");
            CellStyle linkStyle = linkStyle(workbook);
            CreationHelper helper = workbook.getCreationHelper();
            Drawing<?> drawing = sheet.createDrawingPatriarch();

            Row header = sheet.createRow(0);
            header.setHeightInPoints(28);
            for (int column = 0; column < headers.size(); column++)
            {
                Cell cell = header.createCell(column);
                cell.setCellValue(headers.get(column));
                cell.setCellStyle(headerStyle);
                int width = column < fixedWidths.length ? fixedWidths[column] : 14;
                sheet.setColumnWidth(column, Math.min(width * 256, 255 * 256));
            }

            for (int index = 0; index < products.size(); index++)
            {
                EbayCompetitorProduct product = products.get(index);
                Row row = sheet.createRow(index + 1);
                row.setHeightInPoints(72);
                stringCell(row, 0, product.getEbayItemId(), textStyle);
                stringCell(row, 1, product.getSiteCode(), textStyle);
                stringCell(row, 2, product.getMarketplaceId(), textStyle);
                stringCell(row, 3, product.getCurrency(), textStyle);
                stringCell(row, 4, product.getOe(), wrapStyle);
                stringCell(row, 5, product.getSku(), wrapStyle);
                linkCell(workbook, row, 6, product.getReferenceUrl(), linkStyle);
                stringCell(row, 7, product.getRemark(), wrapStyle);
                decimalCell(row, 8, product.getSalePrice(), decimalStyle);
                decimalCell(row, 9, product.getProductCostCny(), decimalStyle);
                decimalCell(row, 10, product.getLengthCm(), decimalStyle);
                decimalCell(row, 11, product.getWidthCm(), decimalStyle);
                decimalCell(row, 12, product.getHeightCm(), decimalStyle);
                decimalCell(row, 13, product.getVolumetricWeightKg(), decimalStyle);
                decimalCell(row, 14, product.getActualWeightKg(), decimalStyle);
                decimalCell(row, 15, product.getExchangeRate(), decimalStyle);
                decimalCell(row, 16, product.getSeaFloorPrice(), decimalStyle);
                decimalCell(row, 17, product.getRailFloorPrice(), decimalStyle);
                decimalCell(row, 18, product.getSeaProfitRate(), rateStyle);
                decimalCell(row, 19, product.getRailProfitRate(), rateStyle);
                decimalCell(row, 20, product.getTargetProfitRate(), rateStyle);
                decimalCell(row, 21, product.getTargetProductCostSea(), decimalStyle);
                decimalCell(row, 22, product.getTargetProductCostRail(), decimalStyle);
                List<EbayCompetitorProductImage> images = productImages.getOrDefault(
                        product.getId(), List.of());
                for (int imageIndex = 0; imageIndex < maxImageCount; imageIndex++)
                {
                    int column = IMAGE_START_COLUMN + imageIndex;
                    Cell imageCell = row.createCell(column);
                    imageCell.setCellStyle(imageCellStyle);
                    if (imageIndex < images.size())
                    {
                        addLocalImage(workbook, drawing, helper, row, column,
                                images.get(imageIndex).getLocalImageUrl());
                    }
                }
            }
            sheet.setAutoFilter(new org.apache.poi.ss.util.CellRangeAddress(
                    0, products.size(), 0, headers.size() - 1));
            workbook.write(output);
            return output.toByteArray();
        }
    }

    private Map<Long, List<EbayCompetitorProductImage>> loadProductImages(
            List<EbayCompetitorProduct> products)
    {
        List<Long> productIds = products.stream().map(EbayCompetitorProduct::getId)
                .filter(java.util.Objects::nonNull).distinct().toList();
        Map<Long, List<EbayCompetitorProductImage>> grouped = new LinkedHashMap<>();
        if (productIds.isEmpty())
        {
            return grouped;
        }
        for (EbayCompetitorProductImage image : mapper.selectProductImagesByProductIds(productIds))
        {
            grouped.computeIfAbsent(image.getProductId(), ignored -> new ArrayList<>()).add(image);
        }
        // 兼容图片明细表创建前保存的旧商品：至少使用商品表中的主图地址。
        for (EbayCompetitorProduct product : products)
        {
            if (product.getId() == null || product.getLocalImageUrl() == null
                    || grouped.containsKey(product.getId()))
            {
                continue;
            }
            EbayCompetitorProductImage image = new EbayCompetitorProductImage();
            image.setProductId(product.getId());
            image.setSortNo(1);
            image.setLocalImageUrl(product.getLocalImageUrl());
            grouped.put(product.getId(), new ArrayList<>(List.of(image)));
        }
        return grouped;
    }

    private void addLocalImage(Workbook workbook, Drawing<?> drawing, CreationHelper helper,
            Row row, int column, String resourceUrl)
    {
        Cell cell = row.getCell(column);
        try
        {
            Path path = localImagePath(resourceUrl);
            if (!Files.isRegularFile(path))
            {
                cell.setCellValue("图片缺失");
                return;
            }
            long fileSize = Files.size(path);
            if (fileSize <= 0 || fileSize > MAX_IMAGE_BYTES)
            {
                cell.setCellValue(fileSize > MAX_IMAGE_BYTES ? "图片过大" : "图片缺失");
                return;
            }
            byte[] bytes = Files.readAllBytes(path);
            int pictureType = pictureType(path, bytes);
            if (pictureType < 0)
            {
                cell.setCellValue("图片格式不支持");
                return;
            }
            int pictureIndex = workbook.addPicture(bytes, pictureType);
            ClientAnchor anchor = helper.createClientAnchor();
            anchor.setCol1(column);
            anchor.setCol2(column);
            anchor.setRow1(row.getRowNum());
            anchor.setRow2(row.getRowNum());
            anchor.setDx1(Units.pixelToEMU(6));
            anchor.setDy1(Units.pixelToEMU(4));
            anchor.setDx2(Units.pixelToEMU(6 + IMAGE_SIZE_PX));
            anchor.setDy2(Units.pixelToEMU(4 + IMAGE_SIZE_PX));
            anchor.setAnchorType(ClientAnchor.AnchorType.MOVE_AND_RESIZE);
            drawing.createPicture(anchor, pictureIndex);
        }
        catch (Exception e)
        {
            cell.setCellValue("图片读取失败");
        }
    }

    private static Path localImagePath(String resourceUrl)
    {
        String prefix = Constants.RESOURCE_PREFIX + "/";
        if (resourceUrl == null || !resourceUrl.startsWith(prefix))
        {
            throw new IllegalArgumentException("本地图片地址不正确");
        }
        Path profile = Path.of(RuoYiConfig.getProfile()).toAbsolutePath().normalize();
        Path allowed = profile.resolve("ebay-competitor").normalize();
        Path target = profile.resolve(resourceUrl.substring(prefix.length())).normalize();
        if (!target.startsWith(allowed))
        {
            throw new IllegalArgumentException("本地图片地址不安全");
        }
        return target;
    }

    private static int pictureType(Path path, byte[] bytes)
    {
        String name = path.getFileName().toString().toLowerCase(Locale.ROOT);
        if (name.endsWith(".png")) return Workbook.PICTURE_TYPE_PNG;
        if (name.endsWith(".jpg") || name.endsWith(".jpeg")) return Workbook.PICTURE_TYPE_JPEG;
        if (name.endsWith(".bmp")) return Workbook.PICTURE_TYPE_DIB;
        if (bytes.length > 3 && bytes[0] == (byte) 0x89 && bytes[1] == 0x50) return Workbook.PICTURE_TYPE_PNG;
        if (bytes.length > 2 && bytes[0] == (byte) 0xFF && bytes[1] == (byte) 0xD8) return Workbook.PICTURE_TYPE_JPEG;
        return -1;
    }

    private static void checkFile(MultipartFile file)
    {
        if (file == null || file.isEmpty())
        {
            throw new ServiceException("请选择包含参考链接的Excel文件");
        }
        if (file.getSize() > MAX_FILE_BYTES)
        {
            throw new ServiceException("Excel文件不能超过5MB");
        }
        String name = file.getOriginalFilename() == null ? "" : file.getOriginalFilename().toLowerCase(Locale.ROOT);
        if (!name.endsWith(".xlsx") && !name.endsWith(".xlsm") && !name.endsWith(".xls"))
        {
            throw new ServiceException("仅支持 .xlsx、.xlsm 或 .xls 文件");
        }
    }

    private static List<Long> normalizeIds(List<Long> ids)
    {
        if (ids == null || ids.isEmpty())
        {
            return List.of();
        }
        return ids.stream().filter(id -> id != null && id > 0).distinct().toList();
    }

    private static String cellText(Row row, int column, DataFormatter formatter, FormulaEvaluator evaluator)
    {
        if (row == null)
        {
            return "";
        }
        Cell cell = row.getCell(column);
        return cell == null ? "" : formatter.formatCellValue(cell, evaluator).trim();
    }

    private static CellStyle headerStyle(Workbook workbook)
    {
        CellStyle style = baseStyle(workbook);
        style.setFillForegroundColor(IndexedColors.ROYAL_BLUE.getIndex());
        style.setFillPattern(FillPatternType.SOLID_FOREGROUND);
        style.setAlignment(HorizontalAlignment.CENTER);
        Font font = workbook.createFont();
        font.setBold(true);
        font.setColor(IndexedColors.WHITE.getIndex());
        style.setFont(font);
        return style;
    }

    private static CellStyle textStyle(Workbook workbook)
    {
        return baseStyle(workbook);
    }

    private static CellStyle wrapStyle(Workbook workbook)
    {
        CellStyle style = baseStyle(workbook);
        style.setWrapText(true);
        return style;
    }

    private static CellStyle decimalStyle(Workbook workbook, String format)
    {
        CellStyle style = baseStyle(workbook);
        style.setDataFormat(workbook.createDataFormat().getFormat(format));
        return style;
    }

    private static CellStyle linkStyle(Workbook workbook)
    {
        CellStyle style = wrapStyle(workbook);
        Font font = workbook.createFont();
        font.setColor(IndexedColors.BLUE.getIndex());
        font.setUnderline(Font.U_SINGLE);
        style.setFont(font);
        return style;
    }

    private static CellStyle baseStyle(Workbook workbook)
    {
        CellStyle style = workbook.createCellStyle();
        style.setVerticalAlignment(VerticalAlignment.CENTER);
        style.setBorderTop(BorderStyle.THIN);
        style.setBorderRight(BorderStyle.THIN);
        style.setBorderBottom(BorderStyle.THIN);
        style.setBorderLeft(BorderStyle.THIN);
        style.setTopBorderColor(IndexedColors.GREY_25_PERCENT.getIndex());
        style.setRightBorderColor(IndexedColors.GREY_25_PERCENT.getIndex());
        style.setBottomBorderColor(IndexedColors.GREY_25_PERCENT.getIndex());
        style.setLeftBorderColor(IndexedColors.GREY_25_PERCENT.getIndex());
        return style;
    }

    private static CellStyle imageCellStyle(Workbook workbook)
    {
        CellStyle style = baseStyle(workbook);
        style.setAlignment(HorizontalAlignment.CENTER);
        style.setVerticalAlignment(VerticalAlignment.CENTER);
        style.setWrapText(true);
        return style;
    }

    private static void stringCell(Row row, int column, String value, CellStyle style)
    {
        Cell cell = row.createCell(column);
        cell.setCellValue(value == null ? "" : value);
        cell.setCellStyle(style);
    }

    private static void decimalCell(Row row, int column, BigDecimal value, CellStyle style)
    {
        Cell cell = row.createCell(column);
        if (value != null)
        {
            cell.setCellValue(value.doubleValue());
        }
        cell.setCellStyle(style);
    }

    private static void linkCell(Workbook workbook, Row row, int column, String value, CellStyle style)
    {
        stringCell(row, column, value, style);
        if (value != null && !value.isBlank())
        {
            org.apache.poi.ss.usermodel.Hyperlink link =
                    workbook.getCreationHelper().createHyperlink(HyperlinkType.URL);
            link.setAddress(value);
            row.getCell(column).setHyperlink(link);
        }
    }

    private static String friendlyError(Throwable error)
    {
        Throwable current = error;
        while (current.getCause() != null && current.getCause() != current)
        {
            current = current.getCause();
        }
        String message = current.getMessage();
        if (message == null || message.isBlank())
        {
            message = current.getClass().getSimpleName();
        }
        return message.replaceAll("[\\r\\n]+", " ").trim();
    }
}
