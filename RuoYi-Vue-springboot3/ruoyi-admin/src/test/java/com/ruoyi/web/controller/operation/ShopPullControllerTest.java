package com.ruoyi.web.controller.operation;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

import com.ruoyi.system.domain.operation.external.ShopList;
import java.time.LocalDate;
import java.util.HashMap;
import java.util.Map;
import org.junit.jupiter.api.Test;

class ShopPullControllerTest
{
    @Test
    void stoppingRequiresReasonAndDate()
    {
        ShopList stop = ShopPullController.buildUpdate(7L,
                Map.of("pullEnabled", 0, "pullStopReason", " 封店 ", "pullStopDate", "2026-11-01"), "admin");
        assertEquals(0, stop.getPullEnabled());
        assertEquals("封店", stop.getPullStopReason());
        assertEquals(LocalDate.of(2026, 11, 1), stop.getPullStopDate());
        assertEquals("admin", stop.getPullUpdatedBy());

        assertThrows(IllegalArgumentException.class, () -> ShopPullController.buildUpdate(7L,
                Map.of("pullEnabled", 0, "pullStopDate", "2026-11-01"), "admin"));
        assertThrows(IllegalArgumentException.class, () -> ShopPullController.buildUpdate(7L,
                Map.of("pullEnabled", 0, "pullStopReason", "封店"), "admin"));
        assertThrows(IllegalArgumentException.class, () -> ShopPullController.buildUpdate(7L,
                Map.of("pullEnabled", 2), "admin"));
    }

    @Test
    void resumingClearsReasonAndDate()
    {
        Map<String, Object> body = new HashMap<>();
        body.put("pullEnabled", 1);
        body.put("pullStopReason", "ignored");
        ShopList resume = ShopPullController.buildUpdate(7L, body, "admin");
        assertEquals(1, resume.getPullEnabled());
        assertNull(resume.getPullStopReason());
        assertNull(resume.getPullStopDate());
    }
}
