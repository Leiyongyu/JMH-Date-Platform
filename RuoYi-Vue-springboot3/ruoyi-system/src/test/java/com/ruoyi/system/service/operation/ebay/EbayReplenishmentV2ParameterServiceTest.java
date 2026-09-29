package com.ruoyi.system.service.operation.ebay;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.ruoyi.common.exception.ServiceException;
import com.ruoyi.system.domain.operation.ebay.EbayReplenishmentV2Parameter;
import com.ruoyi.system.mapper.operation.ebay.EbayReplenishmentV2ParameterMapper;
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ClassPathResource;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

class EbayReplenishmentV2ParameterServiceTest
{
    private EbayReplenishmentV2ParameterMapper mapper;
    private EbayReplenishmentV2ParameterService service;
    private List<EbayReplenishmentV2Parameter> stored;

    @BeforeEach
    void setup() throws Exception
    {
        mapper = mock(EbayReplenishmentV2ParameterMapper.class);
        stored = new ArrayList<>();
        try (var input = new ClassPathResource("ebay/replenishment-v2-parameters.json").getInputStream())
        {
            List<EbayReplenishmentV2ParameterService.Module> modules = new ObjectMapper().readValue(input, new TypeReference<>() {});
            for (var module : modules) for (var row : module.rows()) for (var field : row.fields())
            {
                var value = new EbayReplenishmentV2Parameter();
                value.setParameterKey(field.key());
                if (field.type().equals("grade")) value.setTextValue(field.defaultValue());
                else value.setNumericValue(new BigDecimal(field.defaultValue()));
                stored.add(value);
            }
        }
        when(mapper.selectAll(anyBoolean())).thenReturn(stored);
        when(mapper.updateValue(any(), anyString())).thenReturn(1);
        service = new EbayReplenishmentV2ParameterService(mapper);
    }

    @Test
    void defaultsMatchWorkbookAndRoundTripWithoutSpuriousWrites()
    {
        var snapshot = service.get();
        assertEquals(4, snapshot.modules().size());
        assertEquals(62, snapshot.values().size());
        assertEquals("30", snapshot.values().get("prior_days"));
        assertEquals("5", snapshot.values().get("beta_prior_quantity"));
        assertEquals("D", snapshot.values().get("negative_margin_grade"));
        assertEquals("0.02", snapshot.values().get("prior_demand_rate"));
        var saved = service.save(new EbayReplenishmentV2ParameterService.SaveRequest(snapshot.revision(), snapshot.values()), "tester");
        assertEquals(snapshot.revision(), saved.revision());
        verify(mapper, never()).updateValue(any(), anyString());
    }

    @Test
    void savesEveryModuleAndKeepsExplicitZeroAndOptionalNull()
    {
        var snapshot = service.get();
        var values = new LinkedHashMap<>(snapshot.values());
        values.put("prior_days", "0");
        values.put("prior_demand_rate", null);
        values.put("pattern_smooth_w7", "0.6");
        values.put("pattern_smooth_w15", "0.2");
        values.put("grade_S", "90");
        values.put("dimension_turnover_enabled", "1");
        values.put("negative_margin_grade", "C");
        var saved = service.save(new EbayReplenishmentV2ParameterService.SaveRequest(snapshot.revision(), values), "tester");
        assertNotEquals(snapshot.revision(), saved.revision());
        assertEquals(values, service.get().values());
        verify(mapper, times(7)).updateValue(any(), eq("tester"));
    }

    @Test
    void rejectsStaleEditorAfterAnotherSave()
    {
        var snapshot = service.get();
        var values = new LinkedHashMap<>(snapshot.values());
        values.put("prior_days", "45");
        service.save(new EbayReplenishmentV2ParameterService.SaveRequest(snapshot.revision(), values), "first");
        assertThrows(ServiceException.class, () -> service.save(
                new EbayReplenishmentV2ParameterService.SaveRequest(snapshot.revision(), snapshot.values()), "second"));
        verify(mapper, times(1)).updateValue(any(), anyString());
    }

    @Test
    void rejectsInvalidNumbersMissingAndUnknownKeysBeforeWriting()
    {
        for (String invalid : List.of("NaN", "Infinity", "-1", "1.5", "1000000000", ""))
            rejects("training_days", invalid);
        rejects("stock_factor", "1.1234567");
        rejects("return_ban", "1.1");
        rejects("dimension_margin_enabled", "2");
        rejects("negative_margin_grade", "X");
        var snapshot = service.get();
        var values = new LinkedHashMap<>(snapshot.values());
        values.remove("prior_days");
        assertThrows(ServiceException.class, () -> service.save(new EbayReplenishmentV2ParameterService.SaveRequest(snapshot.revision(), values), "tester"));
        values.put("unknown", "1");
        assertThrows(ServiceException.class, () -> service.save(new EbayReplenishmentV2ParameterService.SaveRequest(snapshot.revision(), values), "tester"));
        verify(mapper, never()).updateValue(any(), anyString());
    }

    @Test
    void rejectsInconsistentThresholdsAndWeightTotalsBeforeWriting()
    {
        rejects("return_watch", "0.4");
        rejects("margin_lower", "0.4");
        rejects("adi_lower", "92");
        rejects("quality_full_rate", "0.3");
        rejects("grade_A", "90");
        rejects("pattern_smooth_w7", "0.1");
        rejects("dimension_margin_weight", "0.5");
        verify(mapper, never()).updateValue(any(), anyString());
    }

    @Test
    void missingMigrationRowsAreNotTreatedAsSuccessfulDefaults()
    {
        stored.remove(0);
        assertTrue(assertThrows(ServiceException.class, service::get).getMessage().contains("20260928_ebay_replenishment_v2_parameters.sql"));
    }

    private void rejects(String key, String value)
    {
        var snapshot = service.get();
        var values = new LinkedHashMap<>(snapshot.values());
        values.put(key, value);
        assertThrows(ServiceException.class, () -> service.save(new EbayReplenishmentV2ParameterService.SaveRequest(snapshot.revision(), values), "tester"));
    }
}
