package com.ruoyi.system.service.operation.external.lingxing;

import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.anyList;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.ruoyi.system.mapper.operation.external.ShopListMapper;
import com.ruoyi.system.mapper.operation.external.ShopListMapper.ShopListKey;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;

class LingxingShopPresenceTest
{
    private static List<ShopListKey> keys(String platform, int count)
    {
        List<ShopListKey> keys = new ArrayList<>();
        for (int i = 0; i < count; i++) keys.add(new ShopListKey(platform, "s" + i));
        return keys;
    }

    @Test
    void marksPresenceWhenReturnedCountIsPlausible()
    {
        ShopListMapper mapper = mock(ShopListMapper.class);
        when(mapper.countPresentByPlatform("10001")).thenReturn(141, 130);
        when(mapper.countPresentByPlatform("10003")).thenReturn(41, 41);
        LingxingShopSyncService service = new LingxingShopSyncService(
                mock(LingxingGatewayService.class), mapper, new ObjectMapper());
        Map<String, List<ShopListKey>> seen = new LinkedHashMap<>();
        seen.put("10001", keys("10001", 130));
        seen.put("10003", keys("10003", 41));

        String note = service.markPresence(seen);

        verify(mapper).markLingxingPresence(eq("10001"), eq(seen.get("10001")));
        verify(mapper).markLingxingPresence(eq("10003"), eq(seen.get("10003")));
        assertTrue(note.contains("平台10001领星返回130家，标记存在130家"), note);
    }

    @Test
    void skipsPlatformWhenLingxingReturnsTooFewOrNone()
    {
        ShopListMapper mapper = mock(ShopListMapper.class);
        when(mapper.countPresentByPlatform("10001")).thenReturn(141);
        when(mapper.countPresentByPlatform("10003")).thenReturn(41);
        LingxingShopSyncService service = new LingxingShopSyncService(
                mock(LingxingGatewayService.class), mapper, new ObjectMapper());
        Map<String, List<ShopListKey>> seen = new LinkedHashMap<>();
        seen.put("10001", keys("10001", 20)); // 远少于 141 的一半，视为接口异常

        String note = service.markPresence(seen);

        verify(mapper, never()).markLingxingPresence(eq("10001"), anyList());
        verify(mapper, never()).markLingxingPresence(eq("10003"), anyList());
        assertTrue(note.contains("平台10001返回20家（当前141家），跳过存在标记"), note);
        assertTrue(note.contains("平台10003返回0家"), note);
    }
}
