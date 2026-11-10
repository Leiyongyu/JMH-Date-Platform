package com.ruoyi.system.service.operation.ebay;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.ruoyi.system.service.finance.PerformancePythonProperties;
import com.ruoyi.system.service.python.PythonHttpSupport;
import java.net.URLEncoder;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.Locale;
import java.util.Map;
import org.springframework.stereotype.Service;

/**
 * ERP 到 Python eBay价格分析服务的内部客户端。
 * 与补货2.0、库存明细共用 PerformancePythonProperties，
 * 内部 Token（X-Internal-Token）与请求 ID（X-Request-ID）由 PythonHttpSupport 统一带上。
 */
@Service
public class EbayPriceAnalysisPythonClient extends PythonHttpSupport
{
    public static final String EXCEL_CONTENT_TYPE =
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";

    /** 按设计契约第 4 节，价格分析的 router 挂在 /api/v1/ebay-price-analysis，不在 /finance 下。 */
    static final String PREFIX = "/api/v1/ebay-price-analysis";
    private static final String FINANCE_SUFFIX = "/api/v1/finance";
    private static final String SERVICE_NAME = "Python eBay价格分析服务";

    public EbayPriceAnalysisPythonClient(
            PerformancePythonProperties properties, ObjectMapper objectMapper)
    {
        super(properties, objectMapper);
    }

    /**
     * 复用 performance.python 的超时与内部 Token 配置，但它的 base-url 带着
     * /api/v1/finance 后缀，而价格分析的接口不在 /finance 下，所以这里把后缀摘掉，
     * 由 PREFIX 给出完整路径。配置成不带后缀的裸地址时原样使用。
     */
    @Override
    protected String baseUrl()
    {
        String value = super.baseUrl();
        return value.endsWith(FINANCE_SUFFIX)
                ? value.substring(0, value.length() - FINANCE_SUFFIX.length())
                : value;
    }

    /** 看板 KPI、店铺对比、散点、缺口 Top、待处理事项。 */
    public Map<String, Object> overview(Map<String, ?> params, String requestId)
    {
        try
        {
            return sendJson(baseRequest(PREFIX + "/overview" + queryString(params), requestId)
                    .GET().build());
        }
        catch (Exception e)
        {
            throw asRuntime(e);
        }
    }

    /** 明细表：按店铺明细或按 SKU 汇总，带分页与排序。 */
    public Map<String, Object> detail(Map<String, ?> params, String requestId)
    {
        try
        {
            return sendJson(baseRequest(PREFIX + "/detail" + queryString(params), requestId)
                    .GET().build());
        }
        catch (Exception e)
        {
            throw asRuntime(e);
        }
    }

    /** 导出 xlsx；允许导出的列由调用方按角色权限算好后放在 columns 参数里。 */
    public ExcelFile export(Map<String, ?> params, String requestId)
    {
        try
        {
            HttpRequest request = baseRequest(PREFIX + "/export" + queryString(params), requestId)
                    .setHeader("Accept", EXCEL_CONTENT_TYPE)
                    .GET().build();
            return sendExcel(request);
        }
        catch (Exception e)
        {
            throw asRuntime(e);
        }
    }

    private ExcelFile sendExcel(HttpRequest request) throws Exception
    {
        HttpResponse<byte[]> response = httpClient.send(
                request, HttpResponse.BodyHandlers.ofByteArray());
        String contentType = response.headers().firstValue("Content-Type").orElse("");
        if (response.statusCode() >= 400
                || contentType.toLowerCase(Locale.ROOT).contains("json"))
        {
            throw new IllegalStateException(errorMessage(
                    parseJson(new String(response.body(), StandardCharsets.UTF_8)),
                    response.statusCode(), SERVICE_NAME));
        }
        if (response.statusCode() != 200 || !contentType.startsWith(EXCEL_CONTENT_TYPE))
            throw new IllegalStateException(SERVICE_NAME + "未返回有效的Excel文件");

        String disposition = response.headers().firstValue("Content-Disposition").orElse("");
        if (!disposition.startsWith("attachment;")
                || disposition.contains("\r") || disposition.contains("\n"))
        {
            String filename = "eBay价格分析-" + LocalDateTime.now()
                    .format(DateTimeFormatter.ofPattern("yyyyMMddHHmmss")) + ".xlsx";
            disposition = "attachment; filename=ebay-price-analysis.xlsx; filename*=UTF-8''"
                    + URLEncoder.encode(filename, StandardCharsets.UTF_8).replace("+", "%20");
        }
        return new ExcelFile(response.body(), disposition);
    }

    private Map<String, Object> sendJson(HttpRequest request) throws Exception
    {
        HttpResponse<String> response = httpClient.send(
                request, HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
        Map<String, Object> body = parseJson(response.body());
        if (response.statusCode() >= 400 || integer(body.get("code"), -1) != 0)
            throw new IllegalStateException(errorMessage(
                    body, response.statusCode(), SERVICE_NAME));
        return body;
    }

    public record ExcelFile(byte[] content, String contentDisposition) {}
}
