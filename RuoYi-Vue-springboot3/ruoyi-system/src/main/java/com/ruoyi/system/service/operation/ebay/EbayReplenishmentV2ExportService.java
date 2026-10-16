package com.ruoyi.system.service.operation.ebay;

import com.ruoyi.common.constant.Constants;
import com.ruoyi.common.exception.ServiceException;
import jakarta.servlet.http.HttpServletResponse;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.math.BigDecimal;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.EnumMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.apache.poi.ss.SpreadsheetVersion;
import org.apache.poi.ss.usermodel.Cell;
import org.apache.poi.ss.usermodel.CellStyle;
import org.apache.poi.ss.usermodel.FillPatternType;
import org.apache.poi.ss.usermodel.Font;
import org.apache.poi.ss.usermodel.IndexedColors;
import org.apache.poi.ss.usermodel.Row;
import org.apache.poi.ss.usermodel.Sheet;
import org.apache.poi.ss.usermodel.VerticalAlignment;
import org.apache.poi.ss.usermodel.Workbook;
import org.apache.poi.ss.util.CellRangeAddress;
import org.apache.poi.xssf.streaming.SXSSFWorkbook;
import org.springframework.stereotype.Service;

/** 只序列化列表已计算的数值，不复制任何补货、分级或预估公式。 */
@Service
public class EbayReplenishmentV2ExportService
{
    public static final String COLUMN_PERMISSION_PREFIX = "operations:ebayReplenishmentV2:exportColumn:";

    private enum Format
    {
        TEXT("@"), INTEGER("#,##0"), DECIMAL("#,##0.00"),
        MONEY("\"¥\"#,##0.00"), PERCENT("0.00%"), DAYS("0\" 天\"");

        final String pattern;
        Format(String pattern) { this.pattern = pattern; }
    }

    private record Column(String title, String key, Format format, int width) {}

    // 与页面保持相同顺序；页面隐藏列不影响导出，但角色字段权限必须在后端过滤。
    private static final List<Column> COLUMNS = List.of(
            new Column("站点", "site", Format.TEXT, 12),
            new Column("SKU", "sku", Format.TEXT, 27),
            new Column("产品名称", "product_name", Format.TEXT, 46),
            new Column("近7天销量", "sales_qty_7d", Format.INTEGER, 16),
            new Column("近15天销量", "sales_qty_15d", Format.INTEGER, 16),
            new Column("近30天销量", "sales_qty_30d", Format.INTEGER, 16),
            new Column("销量", "sales_qty", Format.INTEGER, 14),
            new Column("毛利", "gross_profit_amount", Format.MONEY, 18),
            new Column("利润率", "profit_rate", Format.PERCENT, 14),
            new Column("退货量", "return_qty", Format.INTEGER, 14),
            new Column("退货率", "return_rate", Format.PERCENT, 14),
            new Column("退货金额", "return_amount", Format.MONEY, 18),
            new Column("仓租费用", "warehouse_rent_amount_cny", Format.MONEY, 18),
            new Column("预估销量", "forecast_sales_quantity", Format.DECIMAL, 16),
            new Column("海外仓库龄", "overseas_inventory_age_days", Format.INTEGER, 16),
            new Column("预估销量2", "forecast_sales_quantity_2", Format.DECIMAL, 16),
            new Column("预估毛利", "forecast_gross_profit_amount", Format.MONEY, 18),
            new Column("预估退货", "forecast_return_quantity", Format.DECIMAL, 16),
            new Column("预估退货金额", "forecast_return_amount", Format.MONEY, 18),
            new Column("动销比", "sell_through_ratio", Format.PERCENT, 14),
            new Column("产品等级", "product_level", Format.TEXT, 14),
            new Column("产品性质", "product_nature", Format.TEXT, 14),
            new Column("销售类型", "sales_type", Format.TEXT, 14),
            new Column("成都在途", "chengdu_in_transit_quantity", Format.INTEGER, 16),
            new Column("成都可售", "chengdu_sellable_quantity", Format.INTEGER, 16),
            new Column("海外在途", "overseas_in_transit_quantity", Format.INTEGER, 16),
            new Column("海外可售", "overseas_sellable_quantity", Format.INTEGER, 16),
            new Column("成都仓到仓时间", "chengdu_warehouse_to_warehouse_days", Format.DAYS, 22),
            new Column("成都质检出仓时间", "chengdu_qc_outbound_days", Format.DAYS, 24),
            new Column("海外在途到上架时间", "overseas_transit_to_listing_days", Format.DAYS, 26),
            new Column("安全库存", "safety_stock_quantity", Format.INTEGER, 16),
            new Column("建议补货量", "suggested_replenishment_quantity", Format.INTEGER, 16),
            new Column("安全库存2", "safety_stock_quantity_2", Format.INTEGER, 16),
            new Column("建议补货量2", "suggested_replenishment_quantity_2", Format.INTEGER, 18),
            new Column("运营", "operations_note", Format.TEXT, 36),
            new Column("开发", "development_note", Format.TEXT, 36),
            new Column("运营确认", "operations_confirmed", Format.TEXT, 16));

    private static final List<Column> MONTH_COLUMNS = List.of(
            COLUMNS.get(0), COLUMNS.get(1),
            new Column("日期区间", "month", Format.TEXT, 30),
            COLUMNS.get(6), COLUMNS.get(7), COLUMNS.get(9),
            new Column("产品质量问题退货量", "quality_return_qty", Format.INTEGER, 26),
            new Column("产品质量问题退货率", "quality_return_rate", Format.PERCENT, 26),
            COLUMNS.get(11),
            new Column("未分类退货量", "unclassified_return_qty", Format.INTEGER, 20));

    public void export(Object data, Map<String, ?> filters, Set<String> permissions,
            HttpServletResponse response)
    {
        try
        {
            // 先完成整个文件，再发送响应，解析/校验失败不会下载半个Excel。
            byte[] bytes = buildExcel(data, filters, permissions);
            String filename = "eBay补货2.0-" + LocalDateTime.now().format(
                    DateTimeFormatter.ofPattern("yyyyMMddHHmmss")) + ".xlsx";
            response.setContentType("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet");
            response.setCharacterEncoding(StandardCharsets.UTF_8.name());
            response.setHeader("Content-Disposition", "attachment; filename*=UTF-8''"
                    + URLEncoder.encode(filename, StandardCharsets.UTF_8).replace("+", "%20"));
            response.setContentLength(bytes.length);
            response.getOutputStream().write(bytes);
        }
        catch (IOException e)
        {
            throw new ServiceException("eBay补货2.0导出失败，请稍后重试");
        }
    }

    /** 只接受登录会话的有效权限；没有列权限时明确拒绝，不回退为全部字段。 */
    public void checkExportPermission(Set<String> permissions)
    {
        if (permittedColumns(COLUMNS, permissions).isEmpty()
                && permittedColumns(MONTH_COLUMNS, permissions).isEmpty())
            throw new ServiceException("未配置eBay补货2.0导出字段权限，请联系管理员在角色管理中勾选导出字段", 403);
    }

    private static List<Column> permittedColumns(List<Column> columns, Set<String> permissions)
    {
        if (permissions == null || permissions.isEmpty()) return List.of();
        return columns.stream().filter(column -> permissions.contains(Constants.ALL_PERMISSION)
                || permissions.contains(COLUMN_PERMISSION_PREFIX + column.key())).toList();
    }

    byte[] buildExcel(Object data, Map<String, ?> filters, Set<String> permissions) throws IOException
    {
        checkExportPermission(permissions);
        List<Column> mainColumns = permittedColumns(COLUMNS, permissions);
        List<Column> monthColumns = permittedColumns(MONTH_COLUMNS, permissions);
        // 仅允许站点/SKU时，不额外生成重复三遍、没有任何指标或日期的明细Sheet。
        if (monthColumns.stream().allMatch(column -> Set.of("site", "sku").contains(column.key())))
            monthColumns = List.of();
        if (!(data instanceof Map<?, ?> payload))
            throw new ServiceException("导出数据结构异常，请检查Python服务版本");
        List<Map<?, ?>> items = maps(payload.get("items"));
        if (items.isEmpty()) throw new ServiceException("当前筛选条件下没有可导出的数据");
        if (!(payload.get("pagination") instanceof Map<?, ?> pagination)
                || pagination.get("total") == null
                || new BigDecimal(String.valueOf(pagination.get("total"))).compareTo(
                        BigDecimal.valueOf(items.size())) != 0)
            throw new ServiceException("导出数据不完整：记录数与总数不一致，已拒绝导出当前分页");

        SXSSFWorkbook workbook = new SXSSFWorkbook(100);
        workbook.setCompressTempFiles(true);
        try (workbook; ByteArrayOutputStream output = new ByteArrayOutputStream())
        {
            Map<Format, CellStyle> styles = styles(workbook);
            CellStyle header = headerStyle(workbook);
            Sheet main = mainColumns.isEmpty() ? null : sheet(workbook, "补货2.0", mainColumns, header);
            Sheet monthly = monthColumns.isEmpty() ? null : sheet(workbook, "90天分段明细", monthColumns, header);
            int rowIndex = 1;
            int monthIndex = 1;
            for (Map<?, ?> item : items)
            {
                if (main != null) writeRow(main, rowIndex++, mainColumns, item, styles);
                if (monthly == null) continue;
                for (Map<?, ?> metric : maps(item.get("monthly_metrics")))
                {
                    Map<Object, Object> detail = new LinkedHashMap<>(metric);
                    detail.put("site", item.get("site"));
                    detail.put("sku", item.get("sku"));
                    writeRow(monthly, monthIndex++, monthColumns, detail, styles);
                }
            }
            if (main != null) main.setAutoFilter(new CellRangeAddress(0, rowIndex - 1, 0, mainColumns.size() - 1));
            if (monthly != null) monthly.setAutoFilter(new CellRangeAddress(0, monthIndex - 1, 0, monthColumns.size() - 1));
            writeNotes(workbook, payload, filters, items.size(), mainColumns, monthColumns, header, styles);
            workbook.write(output);
            return output.toByteArray();
        }
        finally
        {
            workbook.dispose();
        }
    }

    private static List<Map<?, ?>> maps(Object value)
    {
        if (!(value instanceof List<?> values))
            throw new ServiceException("导出记录或月度明细格式异常");
        List<Map<?, ?>> result = new ArrayList<>(values.size());
        for (Object row : values)
        {
            if (!(row instanceof Map<?, ?> map)) throw new ServiceException("导出包含无效记录");
            result.add(map);
        }
        return result;
    }

    private static Sheet sheet(Workbook workbook, String name, List<Column> columns, CellStyle header)
    {
        Sheet sheet = workbook.createSheet(name);
        int frozenColumns = 0;
        for (Column column : columns)
        {
            if (!Set.of("site", "sku").contains(column.key())) break;
            frozenColumns++;
        }
        sheet.createFreezePane(frozenColumns, 1);
        sheet.setRepeatingRows(new CellRangeAddress(0, 0, -1, -1));
        Row row = sheet.createRow(0);
        row.setHeightInPoints(32);
        for (int index = 0; index < columns.size(); index++)
        {
            Cell cell = row.createCell(index);
            cell.setCellValue(columns.get(index).title());
            cell.setCellStyle(header);
            sheet.setColumnWidth(index, columns.get(index).width() * 256);
        }
        return sheet;
    }

    private static void writeRow(Sheet sheet, int index, List<Column> columns,
            Map<?, ?> values, Map<Format, CellStyle> styles)
    {
        if (index >= SpreadsheetVersion.EXCEL2007.getMaxRows())
            throw new ServiceException("数据超过Excel单页行数上限，请缩小筛选范围后导出");
        Row row = sheet.createRow(index);
        for (int i = 0; i < columns.size(); i++)
        {
            Column column = columns.get(i);
            Cell cell = row.createCell(i);
            cell.setCellStyle(styles.get(column.format()));
            Object value = values.get(column.key());
            if (value == null || String.valueOf(value).isBlank())
            {
                cell.setCellValue("--");
            }
            else if (column.format() == Format.TEXT)
            {
                String text = String.valueOf(value);
                if ("sales_type".equals(column.key()))
                    text = "NORMAL".equals(text) ? "正常" : "BRUSH".equals(text) ? "刷单" : text;
                if ("operations_confirmed".equals(column.key()))
                    text = Boolean.TRUE.equals(value) || "1".equals(text) ? "已确认" : "待确认";
                // 显式字符串：SKU保留前导零；以=、+、-、@开头的外部文本也不会变成Excel公式。
                cell.setCellValue(text);
            }
            else
            {
                BigDecimal number;
                try { number = new BigDecimal(String.valueOf(value)); }
                catch (NumberFormatException e) { throw new ServiceException(column.title() + "包含无效数值，已拒绝导出"); }
                if (("quality_return_qty".equals(column.key()) || "quality_return_rate".equals(column.key()))
                        && number.signum() <= 0)
                    cell.setCellValue("--");
                else
                {
                    double numeric = number.doubleValue();
                    if (!Double.isFinite(numeric)) throw new ServiceException(column.title() + "数值超出Excel范围");
                    cell.setCellValue(numeric);
                }
            }
        }
    }

    private static Map<Format, CellStyle> styles(Workbook workbook)
    {
        Map<Format, CellStyle> result = new EnumMap<>(Format.class);
        Font font = workbook.createFont();
        font.setFontName("微软雅黑");
        font.setFontHeightInPoints((short) 10);
        for (Format format : Format.values())
        {
            CellStyle style = workbook.createCellStyle();
            style.setFont(font);
            style.setVerticalAlignment(VerticalAlignment.CENTER);
            style.setDataFormat(workbook.createDataFormat().getFormat(format.pattern));
            result.put(format, style);
        }
        return result;
    }

    private static CellStyle headerStyle(Workbook workbook)
    {
        CellStyle style = workbook.createCellStyle();
        style.setFillForegroundColor(IndexedColors.DARK_BLUE.getIndex());
        style.setFillPattern(FillPatternType.SOLID_FOREGROUND);
        style.setWrapText(true);
        style.setVerticalAlignment(VerticalAlignment.CENTER);
        Font font = workbook.createFont();
        font.setFontName("微软雅黑");
        font.setBold(true);
        font.setColor(IndexedColors.WHITE.getIndex());
        style.setFont(font);
        return style;
    }

    private static void writeNotes(Workbook workbook, Map<?, ?> payload, Map<String, ?> filters,
            int count, List<Column> mainColumns, List<Column> monthColumns,
            CellStyle header, Map<Format, CellStyle> styles)
    {
        List<Column> columns = List.of(new Column("项目", "name", Format.TEXT, 25),
                new Column("说明", "value", Format.TEXT, 110));
        Sheet notes = sheet(workbook, "导出说明", columns, header);
        notes.createFreezePane(0, 1);
        Map<String, Object> entries = new LinkedHashMap<>();
        entries.put("生成时间", LocalDateTime.now().format(DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss")));
        entries.put("产品记录数", count);
        entries.put("主表导出字段", mainColumns.stream().map(Column::title).toList());
        entries.put("分段明细导出字段", monthColumns.stream().map(Column::title).toList());
        entries.put("主表销量等日期区间", payload.get("latest_complete_month"));
        entries.put("90天分段区间", payload.get("months"));
        entries.put("滚动统计基准日", payload.get("reference_date"));
        entries.put("站点筛选", selected(filters.get("site")));
        entries.put("SKU包含筛选", selected(filters.get("sku")));
        entries.put("滚动统计口径", "北京时间当天之前连续90天，不含今天；分为连续三个30天区间。近7/15/30天同样截至昨天。预估销量=90天销量/3。");
        entries.put("运营确认筛选", filters.get("operations_confirmed") == null ? "全部" : Boolean.TRUE.equals(filters.get("operations_confirmed")) ? "已确认" : "待确认");
        entries.put("订单产品汇总口径", "按站点+产品SKU汇总；排除AMZ和数字PC开头；末尾-YXR/-RXY归并原SKU，各站点独立");
        entries.put("产品等级筛选", selected(filters.get("product_level")));
        entries.put("产品性质筛选", selected(filters.get("product_nature")));
        entries.put("销售类型筛选", selected(filters.get("sales_type")));
        entries.put("排序字段", filters.get("sort_field") == null ? "sales_qty_30d" : filters.get("sort_field"));
        entries.put("排序方向", filters.get("sort_order") == null ? "desc" : filters.get("sort_order"));
        entries.put("数据范围", "当前筛选下全部记录，不受分页或页面隐藏列影响；仅导出当前账号各角色授权字段的并集，页面展示不受导出字段权限影响。");
        entries.put("金额与比率", "金额为人民币，显示2位小数；比例存数值、显示百分数；数量和天数按页面格式显示。");
        entries.put("空值", "缺失值显示--，真实0保留；质量问题退货量/率为0时按页面显示--。");
        entries.put("数据生成方式", "导出时重新查询现有数据库并复用列表公式，不调用任何外部拉取任务；数据更新后可能与先前打开的页面不同。");
        entries.put("销售类型可用", Boolean.FALSE.equals(payload.get("sales_type_available")) ? "销售类型表尚未部署，显示--" : "可用");
        int index = 1;
        for (Map.Entry<String, Object> entry : entries.entrySet())
        {
            Map<String, Object> row = new LinkedHashMap<>();
            row.put("name", entry.getKey());
            row.put("value", entry.getValue());
            writeRow(notes, index++, columns, row, styles);
        }
    }

    private static String selected(Object value)
    {
        return value == null || String.valueOf(value).isBlank() ? "全部" : String.valueOf(value);
    }
}
