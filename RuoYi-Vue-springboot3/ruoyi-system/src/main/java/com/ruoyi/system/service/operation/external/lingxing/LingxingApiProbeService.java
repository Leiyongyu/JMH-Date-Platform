package com.ruoyi.system.service.operation.external.lingxing;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.StandardOpenOption;
import java.util.LinkedHashMap;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

/**
 * 领星查询接口通用测试执行器。
 *
 * <p>调用只读查询接口并将完整原始响应格式化保存为 TXT。为避免测试入口误改领星数据，
 * 明确拒绝常见新增、修改、提交和删除类接口路径。</p>
 */
@Service
public class LingxingApiProbeService
{
    private static final Set<String> WRITE_PATH_WORDS = Set.of(
            "add", "create", "delete", "edit", "remove", "save", "set",
            "submit", "update", "upload", "write");

    private final LingxingGatewayService gateway;
    private final ObjectMapper objectMapper;

    public LingxingApiProbeService(LingxingGatewayService gateway, ObjectMapper objectMapper)
    {
        this.gateway = gateway;
        this.objectMapper = objectMapper;
    }

    public Map<String, Object> queryAndSave(
            String testName,
            String identifier,
            String apiPath,
            Map<String, Object> requestBody) throws Exception
    {
        String normalizedPath = normalizeAndValidatePath(apiPath);
        String safeTestName = safeFilePart(
                StringUtils.hasText(testName) ? testName.trim() : "api-query");
        String safeIdentifier = safeFilePart(
                StringUtils.hasText(identifier) ? identifier.trim() : "result");
        Map<String, Object> safeBody = requestBody == null
                ? new LinkedHashMap<>() : new LinkedHashMap<>(requestBody);

        Map<String, Object> response = gateway.post(normalizedPath, safeBody);
        Path outputFile = buildOutputFile(safeTestName, safeIdentifier);
        Files.createDirectories(outputFile.getParent());
        Files.writeString(
                outputFile,
                objectMapper.writerWithDefaultPrettyPrinter().writeValueAsString(response),
                StandardCharsets.UTF_8,
                StandardOpenOption.CREATE,
                StandardOpenOption.TRUNCATE_EXISTING,
                StandardOpenOption.WRITE);

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("testName", safeTestName);
        result.put("identifier", safeIdentifier);
        result.put("apiPath", normalizedPath);
        result.put("requestBody", safeBody);
        result.put("outputFile", outputFile.toAbsolutePath().normalize().toString());
        result.put("response", response);
        return result;
    }

    private String normalizeAndValidatePath(String apiPath)
    {
        if (!StringUtils.hasText(apiPath))
        {
            throw new IllegalArgumentException("领星 API Path 不能为空");
        }
        String normalized = apiPath.trim().replace('\\', '/');
        while (normalized.startsWith("/"))
        {
            normalized = normalized.substring(1);
        }
        if (normalized.contains("://") || normalized.contains("..")
                || !normalized.matches("[0-9A-Za-z_./-]+"))
        {
            throw new IllegalArgumentException("领星 API Path 格式不合法");
        }

        String lowerPath = normalized.toLowerCase(Locale.ROOT);
        for (String segment : lowerPath.split("[/_-]"))
        {
            if (WRITE_PATH_WORDS.contains(segment))
            {
                throw new IllegalArgumentException(
                        "通用测试模块仅允许查询接口，拒绝写入类路径: " + normalized);
            }
        }
        String methodName = lowerPath.substring(lowerPath.lastIndexOf('/') + 1);
        for (String word : WRITE_PATH_WORDS)
        {
            if (methodName.startsWith(word))
            {
                throw new IllegalArgumentException(
                        "通用测试模块仅允许查询接口，拒绝写入类路径: " + normalized);
            }
        }
        return normalized;
    }

    private Path buildOutputFile(String testName, String identifier)
    {
        return Paths.get(
                System.getProperty("user.dir"),
                "test-output",
                "lingxing",
                testName + "-" + identifier + ".txt");
    }

    private String safeFilePart(String value)
    {
        String safe = value.replaceAll("[^0-9A-Za-z_-]", "_");
        return StringUtils.hasText(safe) ? safe : "result";
    }
}
