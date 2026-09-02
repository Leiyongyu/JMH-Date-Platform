package com.ruoyi.system.service.procurement;

import com.ruoyi.common.exception.ServiceException;
import com.ruoyi.system.domain.procurement.PendingPurchase;
import com.ruoyi.system.domain.procurement.PendingPurchaseSubmitRequest;
import com.ruoyi.system.mapper.procurement.PendingPurchaseMapper;
import jakarta.servlet.http.HttpServletResponse;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import org.apache.poi.ss.usermodel.CellStyle;
import org.apache.poi.ss.usermodel.FillPatternType;
import org.apache.poi.ss.usermodel.Font;
import org.apache.poi.ss.usermodel.HorizontalAlignment;
import org.apache.poi.ss.usermodel.IndexedColors;
import org.apache.poi.ss.usermodel.Row;
import org.apache.poi.ss.usermodel.Sheet;
import org.apache.poi.ss.usermodel.Workbook;
import org.apache.poi.xssf.usermodel.XSSFWorkbook;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.util.StringUtils;

@Service
public class PendingPurchaseService
{
    private static final String PENDING = "0";
    private static final DateTimeFormatter DATE_TIME_FORMATTER =
            DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss");
    private static final DateTimeFormatter FILE_TIME_FORMATTER =
            DateTimeFormatter.ofPattern("yyyyMMddHHmmss");

    private final PendingPurchaseMapper mapper;

    public PendingPurchaseService(PendingPurchaseMapper mapper)
    {
        this.mapper = mapper;
    }

    public List<PendingPurchase> list(String site, String sku, String status)
    {
        String normalizedStatus = normalizeStatus(status);
        return mapper.selectList(trimToNull(site), trimToNull(sku), normalizedStatus);
    }

    /** 在PageHelper分页上下文创建前校验状态，避免非法参数残留线程分页状态。 */
    public void validateStatusFilter(String status)
    {
        normalizeStatus(status);
    }

    @Transactional(rollbackFor = Exception.class)
    public void submit(PendingPurchaseSubmitRequest request, String operator)
    {
        String site = requiredText(request.getSite(), "站点不能为空");
        String sku = requiredText(request.getSku(), "SKU不能为空");
        Integer quantity = request.getPurchaseQuantity();
        if (quantity == null || quantity <= 0)
        {
            throw new ServiceException("最终采购量必须大于0");
        }
        mapper.upsertPending(site, sku, quantity, safeOperator(operator));
    }

    /**
     * 锁定选中待采购记录、生成Excel、更新状态并写出响应。
     * 同步写出异常会继续抛出，从而回滚状态更新。
     */
    @Transactional(rollbackFor = Exception.class)
    public void exportAndMarkPurchased(List<Long> rawIds,
                                       String operator,
                                       HttpServletResponse response) throws IOException
    {
        List<Long> ids = normalizeIds(rawIds);
        List<PendingPurchase> rows = mapper.selectPendingByIdsForUpdate(ids);
        if (rows.size() != ids.size())
        {
            throw new ServiceException("部分记录不存在或已被其他用户导出，请刷新后重新选择");
        }

        byte[] workbookBytes = buildWorkbook(rows);
        int updated = mapper.markPurchased(ids, safeOperator(operator));
        if (updated != ids.size())
        {
            throw new ServiceException("待采购状态更新失败，请刷新后重试");
        }

        String fileName = "待采购_" + LocalDateTime.now().format(FILE_TIME_FORMATTER) + ".xlsx";
        response.setContentType("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet");
        response.setCharacterEncoding(StandardCharsets.UTF_8.name());
        response.setContentLength(workbookBytes.length);
        response.setHeader("Content-Disposition", "attachment; filename*=UTF-8''"
                + URLEncoder.encode(fileName, StandardCharsets.UTF_8).replace("+", "%20"));
        response.getOutputStream().write(workbookBytes);
    }

    private byte[] buildWorkbook(List<PendingPurchase> rows) throws IOException
    {
        try (Workbook workbook = new XSSFWorkbook();
             ByteArrayOutputStream output = new ByteArrayOutputStream())
        {
            Sheet sheet = workbook.createSheet("待采购");
            CellStyle headerStyle = workbook.createCellStyle();
            Font headerFont = workbook.createFont();
            headerFont.setBold(true);
            headerFont.setColor(IndexedColors.WHITE.getIndex());
            headerStyle.setFont(headerFont);
            headerStyle.setFillForegroundColor(IndexedColors.DARK_BLUE.getIndex());
            headerStyle.setFillPattern(FillPatternType.SOLID_FOREGROUND);
            headerStyle.setAlignment(HorizontalAlignment.CENTER);

            String[] headers = {"站点", "SKU", "最终采购量", "采购时间", "状态"};
            Row header = sheet.createRow(0);
            for (int i = 0; i < headers.length; i++)
            {
                header.createCell(i).setCellValue(headers[i]);
                header.getCell(i).setCellStyle(headerStyle);
            }

            for (int i = 0; i < rows.size(); i++)
            {
                PendingPurchase item = rows.get(i);
                Row row = sheet.createRow(i + 1);
                row.createCell(0).setCellValue(item.getSite());
                row.createCell(1).setCellValue(item.getSku());
                row.createCell(2).setCellValue(item.getPurchaseQuantity());
                row.createCell(3).setCellValue(formatDateTime(item.getPurchaseTime()));
                row.createCell(4).setCellValue("已采购");
            }

            sheet.setColumnWidth(0, 18 * 256);
            sheet.setColumnWidth(1, 30 * 256);
            sheet.setColumnWidth(2, 16 * 256);
            sheet.setColumnWidth(3, 22 * 256);
            sheet.setColumnWidth(4, 14 * 256);
            sheet.createFreezePane(0, 1);
            workbook.write(output);
            return output.toByteArray();
        }
    }

    private List<Long> normalizeIds(List<Long> rawIds)
    {
        if (rawIds == null || rawIds.isEmpty())
        {
            throw new ServiceException("请选择需要导出的待采购记录");
        }
        Set<Long> unique = new LinkedHashSet<>();
        for (Long id : rawIds)
        {
            if (id == null || id <= 0)
            {
                throw new ServiceException("导出记录ID不正确");
            }
            unique.add(id);
        }
        if (unique.size() > 5000)
        {
            throw new ServiceException("单次最多导出5000条待采购记录");
        }
        return List.copyOf(unique);
    }

    private String normalizeStatus(String status)
    {
        String value = trimToNull(status);
        if (value == null) return null;
        if (!PENDING.equals(value) && !"1".equals(value))
        {
            throw new ServiceException("采购状态不正确");
        }
        return value;
    }

    private String formatDateTime(LocalDateTime value)
    {
        return value == null ? "" : value.format(DATE_TIME_FORMATTER);
    }

    private String requiredText(String value, String message)
    {
        String normalized = trimToNull(value);
        if (normalized == null) throw new ServiceException(message);
        return normalized;
    }

    private String safeOperator(String operator)
    {
        String normalized = trimToNull(operator);
        return normalized == null ? "SYSTEM" : normalized;
    }

    private String trimToNull(String value)
    {
        return StringUtils.hasText(value) ? value.trim() : null;
    }
}
