package com.ruoyi.system.service.operation.external.lingxing;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Arrays;
import java.util.Base64;
import java.util.Collection;
import java.util.Map;
import javax.crypto.Cipher;
import javax.crypto.spec.SecretKeySpec;

public final class LingxingSignUtils
{
    private static final String AES_ECB_MODE = "AES/ECB/PKCS5Padding";
    private static final ObjectMapper OM = new ObjectMapper();

    private LingxingSignUtils() {}

    public static String sign(Map<String, Object> params, String appSecret)
    {
        String[] keys = params.keySet().toArray(new String[0]);
        Arrays.sort(keys);
        StringBuilder builder = new StringBuilder();
        for (String key : keys)
        {
            Object value = params.get(key);
            builder.append(key).append("=").append(toStringValue(value)).append("&");
        }
        if (builder.length() > 0) builder.setLength(builder.length() - 1);
        return encryptEcb(md5Upper(builder.toString()), appSecret);
    }

    /** 将参数值转为签名字符串：集合类型转紧凑 JSON，与旧项目 fastjson2 行为一致 */
    private static String toStringValue(Object value)
    {
        if (value == null) return "";
        if (value instanceof Collection || value instanceof Object[])
        {
            try { return OM.writeValueAsString(value); } catch (Exception e) { return String.valueOf(value); }
        }
        return String.valueOf(value).trim();
    }

    private static String md5Upper(String text)
    {
        try
        {
            MessageDigest digest = MessageDigest.getInstance("MD5");
            byte[] bytes = digest.digest(text.getBytes(StandardCharsets.UTF_8));
            StringBuilder hex = new StringBuilder(bytes.length * 2);
            for (byte b : bytes)
            {
                hex.append(String.format("%02X", b));
            }
            return hex.toString();
        }
        catch (Exception e)
        {
            throw new IllegalStateException("Lingxing sign MD5 failed", e);
        }
    }

    private static String encryptEcb(String text, String appSecret)
    {
        try
        {
            SecretKeySpec spec = new SecretKeySpec(appSecret.getBytes(StandardCharsets.UTF_8), "AES");
            Cipher cipher = Cipher.getInstance(AES_ECB_MODE);
            cipher.init(Cipher.ENCRYPT_MODE, spec);
            return Base64.getEncoder().encodeToString(cipher.doFinal(text.getBytes(StandardCharsets.UTF_8)));
        }
        catch (Exception e)
        {
            throw new IllegalStateException("Lingxing sign AES encrypt failed", e);
        }
    }
}
