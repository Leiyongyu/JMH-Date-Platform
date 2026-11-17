package com.ruoyi.web.config;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.boot.env.YamlPropertySourceLoader;
import org.springframework.core.env.MapPropertySource;
import org.springframework.core.env.PropertySource;
import org.springframework.core.env.StandardEnvironment;
import org.springframework.core.io.ClassPathResource;

/**
 * 各模块的 Python 调用配置都引用 jmh.python，确认只配一处即可全部生效，
 * 且模块级环境变量仍能单独覆盖。
 */
class PythonClientConfigTest
{
    private StandardEnvironment load(Map<String, Object> env) throws Exception
    {
        StandardEnvironment environment = new StandardEnvironment();
        environment.getPropertySources().remove(StandardEnvironment.SYSTEM_ENVIRONMENT_PROPERTY_SOURCE_NAME);
        environment.getPropertySources().remove(StandardEnvironment.SYSTEM_PROPERTIES_PROPERTY_SOURCE_NAME);
        environment.getPropertySources().addFirst(new MapPropertySource("env", env));
        List<PropertySource<?>> sources = new YamlPropertySourceLoader()
                .load("application", new ClassPathResource("application.yml"));
        sources.forEach(environment.getPropertySources()::addLast);
        return environment;
    }

    @Test
    void singleBaseUrlAndTokenReachEveryPythonClient() throws Exception
    {
        StandardEnvironment env = load(Map.of(
                "JMH_PYTHON_BASE_URL", "http://py:9000",
                "PYTHON_INTERNAL_API_TOKEN", "t0ken"));
        assertEquals("http://py:9000", env.getProperty("tax-refund.data-project.base-url"));
        assertEquals("http://py:9000", env.getProperty("ai-assistant.python.base-url"));
        assertEquals("http://py:9000/image-sop", env.getProperty("image-sop.python.base-url"));
        assertEquals("http://py:9000/script-tools/", env.getProperty("image-sop.python.workbench-url"));
        assertEquals("http://py:9000/customs-declaration", env.getProperty("customs-declaration.legacy.base-url"));
        assertEquals("http://py:9000/ebay-tool", env.getProperty("ebay-tool.python.base-url"));
        assertEquals("http://py:9000/api/v1/finance", env.getProperty("performance.python.base-url"));
        assertEquals("http://py:9000", env.getProperty("jmh.python-performance.base-url"));
        for (String prefix : List.of("tax-refund.data-project", "ai-assistant.python", "image-sop.python",
                "customs-declaration.legacy", "ebay-tool.python", "performance.python", "jmh.python-performance"))
        {
            assertEquals("t0ken", env.getProperty(prefix + ".internal-token"), prefix);
            assertEquals("5000", env.getProperty(prefix + ".connect-timeout"), prefix);
        }
    }

    @Test
    void timeoutTiersAndModuleOverrides() throws Exception
    {
        StandardEnvironment env = load(Map.of(
                "AI_ASSISTANT_PYTHON_BASE_URL", "http://ai:1",
                "JMH_PYTHON_TIMEOUT_LONG_MS", "1234"));
        assertEquals("http://ai:1", env.getProperty("ai-assistant.python.base-url"));
        assertEquals("http://127.0.0.1:8010", env.getProperty("tax-refund.data-project.base-url"));
        assertEquals("300000", env.getProperty("ai-assistant.python.read-timeout"));
        assertEquals("1234", env.getProperty("image-sop.python.read-timeout"));
        assertEquals("120000", env.getProperty("customs-declaration.legacy.read-timeout"));
        assertEquals("10800000", env.getProperty("jmh.python-performance.read-timeout"));
    }
}
