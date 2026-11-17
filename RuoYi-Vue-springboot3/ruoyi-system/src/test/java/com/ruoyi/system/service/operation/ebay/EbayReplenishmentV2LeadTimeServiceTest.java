package com.ruoyi.system.service.operation.ebay;

import com.ruoyi.system.domain.operation.ebay.EbayReplenishmentV2LeadTime;
import com.ruoyi.system.domain.operation.ebay.EbayReplenishmentV2LeadTimeSaveRequest;
import com.ruoyi.system.mapper.operation.ebay.EbayReplenishmentV2LeadTimeMapper;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class EbayReplenishmentV2LeadTimeServiceTest
{
    @Test
    void listAndExportUseDefaultsWithoutOverwritingManualValuesOrWritingData()
    {
        var mapper = mock(EbayReplenishmentV2LeadTimeMapper.class);
        var manual = config("德国", "manual", 85);
        var zero = config("美国", "zero", 0);
        var empty = config("英国", "empty", null);
        when(mapper.selectByKeys(anyList())).thenReturn(List.of(manual, zero, empty));
        var service = new EbayReplenishmentV2LeadTimeService(mapper);
        var rows = List.of(row("德国", "new"), row("英国", "new"), row("美国", "new"),
                row("德国", "manual"), row("美国", "zero"), row("英国", "empty"),
                row("法国", "other"), row(null, "invalid"));
        service.enrich(Map.of("items", rows));
        Integer[] expected = {67, 72, 60, 85, 0, 72, null, null};
        for (int i = 0; i < rows.size(); i++)
            assertEquals(expected[i], rows.get(i).get("overseas_transit_to_listing_days"));
        verify(mapper).selectByKeys(anyList());
        verifyNoMoreInteractions(mapper);
    }

    @Test
    void manualSaveKeepsZeroAndClearingReturnsDefaultWithoutPersistingDefault()
    {
        var mapper = mock(EbayReplenishmentV2LeadTimeMapper.class);
        var service = new EbayReplenishmentV2LeadTimeService(mapper);
        var request = new EbayReplenishmentV2LeadTimeSaveRequest();
        request.setSite(" 德国 "); request.setSku("BMW-1-2");
        request.setField(EbayReplenishmentV2LeadTimeService.FIELD_OVERSEAS_LISTING);
        request.setDays(0);
        assertEquals(0, service.save(request, "actual-user"));
        request.setDays(88);
        assertEquals(88, service.save(request, "actual-user"));
        request.setDays(null);
        assertEquals(67, service.save(request, "actual-user"));
        verify(mapper).upsertField("德国", "BMW-1-2", request.getField(), 0, "actual-user");
        verify(mapper).upsertField("德国", "BMW-1-2", request.getField(), 88, "actual-user");
        verify(mapper).upsertField("德国", "BMW-1-2", request.getField(), null, "actual-user");
        request.setField(EbayReplenishmentV2LeadTimeService.FIELD_CHENGDU_QC_OUTBOUND);
        assertNull(service.save(request, "actual-user"));
    }

    private static Map<String, Object> row(String site, String sku)
    {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("site", site); result.put("sku", sku);
        return result;
    }

    private static EbayReplenishmentV2LeadTime config(String site, String sku, Integer days)
    {
        var result = new EbayReplenishmentV2LeadTime();
        result.setSite(site); result.setSku(sku); result.setOverseasTransitToListingDays(days);
        return result;
    }
}
