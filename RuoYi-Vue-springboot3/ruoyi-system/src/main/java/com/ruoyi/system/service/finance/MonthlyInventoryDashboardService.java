package com.ruoyi.system.service.finance;

import com.ruoyi.system.mapper.finance.MonthlyInventoryDashboardMapper;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.regex.Pattern;
import org.springframework.stereotype.Service;

/** 首页月度库存图表只读服务，不经过Python HTTP接口。 */
@Service
public class MonthlyInventoryDashboardService
{
    private static final Pattern YEAR = Pattern.compile("^20\\d{2}$");
    private static final Pattern MONTH = Pattern.compile("^(0[1-9]|1[0-2])$");

    private final MonthlyInventoryDashboardMapper mapper;

    public MonthlyInventoryDashboardService(
            MonthlyInventoryDashboardMapper mapper)
    {
        this.mapper = mapper;
    }

    public Map<String, Object> costTrend(String requestedYear, String requestedMonth)
    {
        String year = trim(requestedYear);
        String month = trim(requestedMonth);
        if (!year.isEmpty() && !YEAR.matcher(year).matches())
            throw new IllegalArgumentException("year必须是20开头的四位年份");
        if (!month.isEmpty() && !MONTH.matcher(month).matches())
            throw new IllegalArgumentException("month必须是01到12");

        List<Map<String, Object>> periods = mapper.selectAvailablePeriods();
        if (year.isEmpty() && !periods.isEmpty())
        {
            String latest = String.valueOf(periods.get(0).get("report_month"));
            year = latest.length() >= 4 ? latest.substring(0, 4) : "";
        }
        List<Map<String, Object>> items = year.isEmpty()
                ? List.of()
                : mapper.selectCostTrend(year, month.isEmpty() ? null : month);

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("year", year.isEmpty() ? null : year);
        result.put("month", month.isEmpty() ? null : month);
        result.put("periods", periods);
        result.put("items", items);
        return result;
    }

    private String trim(String value)
    {
        return value == null ? "" : value.trim();
    }
}
