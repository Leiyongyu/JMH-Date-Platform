package com.ruoyi.system.service.operation.ebay;

import java.io.ByteArrayOutputStream;
import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.concurrent.CompletableFuture;
import jakarta.servlet.http.HttpServletResponse;
import org.apache.poi.common.usermodel.HyperlinkType;
import org.apache.poi.ss.usermodel.Cell;
import org.apache.poi.ss.usermodel.CellStyle;
import org.apache.poi.ss.usermodel.ClientAnchor;
import org.apache.poi.ss.usermodel.CreationHelper;
import org.apache.poi.ss.usermodel.Drawing;
import org.apache.poi.ss.usermodel.FillPatternType;
import org.apache.poi.ss.usermodel.Font;
import org.apache.poi.ss.usermodel.HorizontalAlignment;
import org.apache.poi.ss.usermodel.Hyperlink;
import org.apache.poi.ss.usermodel.IndexedColors;
import org.apache.poi.ss.usermodel.Row;
import org.apache.poi.ss.usermodel.Sheet;
import org.apache.poi.ss.usermodel.VerticalAlignment;
import org.apache.poi.ss.usermodel.Workbook;
import org.apache.poi.util.Units;
import org.apache.poi.xssf.usermodel.XSSFWorkbook;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.stereotype.Service;
import com.ruoyi.common.exception.ServiceException;
import com.ruoyi.system.domain.operation.ebay.EbayItemDetail;

/**
 * eBay 查询结果导出。
 *
 * 导出单个 Excel，商品图片直接嵌入最后一列。
 */
@Service
public class EbayPriceExportService
{
    private static final Logger LOG = LoggerFactory.getLogger(EbayPriceExportService.class);
    private static final String EXCEL_CONTENT_TYPE =
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
    private static final int MAX_IMAGE_BYTES = 8 * 1024 * 1024;
    private static final DateTimeFormatter FILE_TIME = DateTimeFormatter.ofPattern("yyyyMMddHHmmss");

    private final HttpClient imageClient = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(5))
            .followRedirects(HttpClient.Redirect.NEVER)
            .build();
    private final ThreadPoolTaskExecutor detailExecutor;

    public EbayPriceExportService(
            @Qualifier("ebayDetailExecutor") ThreadPoolTaskExecutor detailExecutor)
    {
        this.detailExecutor = detailExecutor;
    }

    public void export(List<EbayItemDetail> items, HttpServletResponse response, String requestId)
    {
        if (items == null || items.isEmpty())
        {
            throw new ServiceException("没有可导出的商品");
        }
        if (items.size() > 1000)
        {
            throw new ServiceException("单次最多导出 1000 件商品");
        }

        String fileName = "查询结果" + LocalDateTime.now().format(FILE_TIME) + ".xlsx";
        try
        {
            byte[] excelBytes = buildExcel(items);
            String downloadName = URLEncoder.encode(fileName, StandardCharsets.UTF_8)
                    .replace("+", "%20");
            response.setContentType(EXCEL_CONTENT_TYPE);
            response.setCharacterEncoding(StandardCharsets.UTF_8.name());
            response.setHeader("Content-Disposition", "attachment; filename*=UTF-8''" + downloadName);
            response.setHeader("X-Request-ID", requestId);
            response.setContentLength(excelBytes.length);
            response.getOutputStream().write(excelBytes);
            response.flushBuffer();
            LOG.info("eBay图片Excel导出完成 requestId={}, itemCount={}, fileName={}",
                    requestId, items.size(), fileName);
        }
        catch (ServiceException e)
        {
            throw e;
        }
        catch (Exception e)
        {
            throw new ServiceException("eBay 查询结果导出失败: " + e.getMessage());
        }
    }

    private byte[] buildExcel(List<EbayItemDetail> items) throws Exception
    {
        try (Workbook workbook = new XSSFWorkbook(); ByteArrayOutputStream output = new ByteArrayOutputStream())
        {
            Sheet sheet = workbook.createSheet("eBay Results");
            sheet.createFreezePane(0, 1);
            String[] headers = { "OE", "商品ID", "价格", "预计已售", "商品标题",
                    "卖家", "好评率", "运费", "商品链接", "商品图片" };
            int[] widths = { 18, 18, 16, 14, 60, 20, 12, 16, 48, 76 };
            CellStyle headerStyle = headerStyle(workbook);
            CellStyle wrapStyle = wrapStyle(workbook);
            CellStyle linkStyle = linkStyle(workbook);
            Row header = sheet.createRow(0);
            header.setHeightInPoints(28);
            for (int column = 0; column < headers.length; column++)
            {
                Cell cell = header.createCell(column);
                cell.setCellValue(headers[column]);
                cell.setCellStyle(headerStyle);
                sheet.setColumnWidth(column, Math.min(widths[column] * 256, 255 * 256));
            }

            CreationHelper helper = workbook.getCreationHelper();
            Drawing<?> drawing = sheet.createDrawingPatriarch();
            for (int index = 0; index < items.size(); index++)
            {
                EbayItemDetail item = items.get(index);
                Row row = sheet.createRow(index + 1);
                row.setHeightInPoints(46);
                stringCell(row, 0, item.getOe(), wrapStyle);
                stringCell(row, 1, folderId(item, index), wrapStyle);
                stringCell(row, 2, item.getPrice(), wrapStyle);
                if (item.getEstimatedSoldQuantity() != null)
                {
                    row.createCell(3).setCellValue(item.getEstimatedSoldQuantity());
                }
                stringCell(row, 4, item.getTitle(), wrapStyle);
                stringCell(row, 5, item.getSeller(), wrapStyle);
                stringCell(row, 6, rate(item.getSellerFeedback()), wrapStyle);
                stringCell(row, 7, item.getShipping(), wrapStyle);
                addLink(row, 8, item.getLink(), linkStyle, helper);
                addImagesToCell(workbook, drawing, helper, row, 9, item, wrapStyle);
            }
            workbook.write(output);
            return output.toByteArray();
        }
    }

    private void addImagesToCell(Workbook workbook, Drawing<?> drawing, CreationHelper helper,
            Row row, int column, EbayItemDetail item, CellStyle style)
    {
        List<ImageDownload> images = downloadImages(item);
        Cell cell = row.createCell(column);
        cell.setCellStyle(style);
        if (images.isEmpty())
        {
            cell.setCellValue(item.getImages() == null || item.getImages().isEmpty()
                    ? "无图片" : "图片下载失败");
            return;
        }

        final int imagesPerRow = 5;
        final int thumbnailPixels = 82;
        final int gapPixels = 6;
        int imageRows = (images.size() + imagesPerRow - 1) / imagesPerRow;
        row.setHeightInPoints(Math.max(46F,
                (imageRows * (thumbnailPixels + gapPixels) + gapPixels) * 0.75F));
        for (int index = 0; index < images.size(); index++)
        {
            ImageDownload image = images.get(index);
            int pictureIndex = workbook.addPicture(image.bytes(), image.pictureType());
            int imageColumn = index % imagesPerRow;
            int imageRow = index / imagesPerRow;
            int left = gapPixels + imageColumn * (thumbnailPixels + gapPixels);
            int top = gapPixels + imageRow * (thumbnailPixels + gapPixels);
            ClientAnchor anchor = helper.createClientAnchor();
            anchor.setCol1(column);
            anchor.setCol2(column);
            anchor.setRow1(row.getRowNum());
            anchor.setRow2(row.getRowNum());
            anchor.setDx1(Units.pixelToEMU(left));
            anchor.setDy1(Units.pixelToEMU(top));
            anchor.setDx2(Units.pixelToEMU(left + thumbnailPixels));
            anchor.setDy2(Units.pixelToEMU(top + thumbnailPixels));
            anchor.setAnchorType(ClientAnchor.AnchorType.MOVE_AND_RESIZE);
            drawing.createPicture(anchor, pictureIndex);
        }
    }

    private List<ImageDownload> downloadImages(EbayItemDetail item)
    {
        List<String> imageUrls = uniqueImages(item == null ? null : item.getImages());
        List<CompletableFuture<ImageDownload>> futures = new ArrayList<>();
        for (int index = 0; index < imageUrls.size(); index++)
        {
            int currentIndex = index;
            String imageUrl = thumbnailUrl(imageUrls.get(index));
            futures.add(CompletableFuture.supplyAsync(
                    () -> downloadImage(imageUrl, currentIndex), detailExecutor));
        }
        List<ImageDownload> images = new ArrayList<>();
        for (CompletableFuture<ImageDownload> future : futures)
        {
            ImageDownload image = future.join();
            if (image != null)
            {
                images.add(image);
            }
        }
        images.sort((left, right) -> Integer.compare(left.index(), right.index()));
        return images;
    }

    private ImageDownload downloadImage(String imageUrl, int index)
    {
        try
        {
            URI uri = URI.create(imageUrl);
            if (!allowedImageUri(uri))
            {
                return null;
            }
            HttpRequest request = HttpRequest.newBuilder(uri)
                    .timeout(Duration.ofSeconds(15))
                    .header("Accept", "image/jpeg,image/png")
                    .GET()
                    .build();
            HttpResponse<byte[]> response = imageClient.send(request, HttpResponse.BodyHandlers.ofByteArray());
            byte[] bytes = response.body();
            if (response.statusCode() < 200 || response.statusCode() >= 300
                    || bytes == null || bytes.length == 0 || bytes.length > MAX_IMAGE_BYTES)
            {
                return null;
            }
            Integer pictureType = imagePictureType(
                    response.headers().firstValue("Content-Type").orElse(""), bytes);
            return pictureType == null ? null : new ImageDownload(index, pictureType, bytes);
        }
        catch (Exception ignored)
        {
            return null;
        }
    }

    private static List<String> uniqueImages(List<String> images)
    {
        if (images == null || images.isEmpty())
        {
            return List.of();
        }
        LinkedHashSet<String> unique = new LinkedHashSet<>();
        for (String image : images)
        {
            if (image != null && !image.isBlank())
            {
                unique.add(image.trim());
            }
        }
        return new ArrayList<>(unique);
    }

    private static String thumbnailUrl(String imageUrl)
    {
        return imageUrl == null ? "" : imageUrl.replaceAll("(?i)s-l\\d+", "s-l200");
    }

    private static String folderId(EbayItemDetail item, int index)
    {
        String value = item == null ? "" : item.getProductId();
        if (value == null || value.isBlank())
        {
            value = extractProductId(item == null ? null : item.getItemId());
        }
        String safe = value == null ? "" : value.trim().replaceAll("[\\\\/:*?\"<>|]", "_");
        safe = safe.replaceAll("[. ]+$", "");
        if (safe.isBlank() || ".".equals(safe) || "..".equals(safe))
        {
            safe = "UNKNOWN_" + String.format(Locale.ROOT, "%03d", index + 1);
        }
        return safe.length() <= 120 ? safe : safe.substring(0, 120);
    }

    private static String extractProductId(String itemId)
    {
        if (itemId == null || itemId.isBlank())
        {
            return "";
        }
        String[] parts = itemId.split("\\|", -1);
        return parts.length >= 2 && !parts[1].isBlank() ? parts[1] : itemId;
    }

    private static boolean allowedImageUri(URI uri)
    {
        if (uri == null || !"https".equalsIgnoreCase(uri.getScheme()) || uri.getHost() == null)
        {
            return false;
        }
        String host = uri.getHost().toLowerCase(Locale.ROOT);
        return "ebayimg.com".equals(host) || host.endsWith(".ebayimg.com");
    }

    private static Integer imagePictureType(String contentType, byte[] bytes)
    {
        String type = contentType.toLowerCase(Locale.ROOT);
        if (type.contains("png") || isPng(bytes))
        {
            return Workbook.PICTURE_TYPE_PNG;
        }
        if (type.contains("jpeg") || type.contains("jpg") || isJpeg(bytes))
        {
            return Workbook.PICTURE_TYPE_JPEG;
        }
        return null;
    }

    private static boolean isPng(byte[] bytes)
    {
        return bytes.length > 8 && bytes[0] == (byte) 0x89 && bytes[1] == 0x50
                && bytes[2] == 0x4E && bytes[3] == 0x47;
    }

    private static boolean isJpeg(byte[] bytes)
    {
        return bytes.length > 3 && bytes[0] == (byte) 0xFF && bytes[1] == (byte) 0xD8;
    }

    private static void stringCell(Row row, int column, String value, CellStyle style)
    {
        Cell cell = row.createCell(column);
        cell.setCellValue(value == null ? "" : value);
        cell.setCellStyle(style);
    }

    private static void addLink(Row row, int column, String link, CellStyle style, CreationHelper helper)
    {
        Cell cell = row.createCell(column);
        if (link == null || link.isBlank())
        {
            return;
        }
        cell.setCellValue(link);
        Hyperlink hyperlink = helper.createHyperlink(HyperlinkType.URL);
        hyperlink.setAddress(link);
        cell.setHyperlink(hyperlink);
        cell.setCellStyle(style);
    }

    private static String rate(String value)
    {
        if (value == null || value.isBlank())
        {
            return "";
        }
        return value.endsWith("%") ? value : value + "%";
    }

    private static CellStyle headerStyle(Workbook workbook)
    {
        CellStyle style = workbook.createCellStyle();
        style.setFillForegroundColor(IndexedColors.ROYAL_BLUE.getIndex());
        style.setFillPattern(FillPatternType.SOLID_FOREGROUND);
        style.setAlignment(HorizontalAlignment.CENTER);
        style.setVerticalAlignment(VerticalAlignment.CENTER);
        Font font = workbook.createFont();
        font.setBold(true);
        font.setColor(IndexedColors.WHITE.getIndex());
        style.setFont(font);
        return style;
    }

    private static CellStyle wrapStyle(Workbook workbook)
    {
        CellStyle style = workbook.createCellStyle();
        style.setWrapText(true);
        style.setVerticalAlignment(VerticalAlignment.CENTER);
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

    private record ImageDownload(int index, int pictureType, byte[] bytes) {}
}
