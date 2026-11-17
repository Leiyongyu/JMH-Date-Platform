package com.ruoyi.system.mapper;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.fail;

import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Stream;
import org.apache.ibatis.builder.xml.XMLMapperBuilder;
import org.apache.ibatis.session.Configuration;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

/**
 * 逐个用 MyBatis 自己的解析器加载全部 mapper XML。
 *
 * <p>存在的理由：XML 格式合法不等于 MyBatis 能解析。曾经有一次改动在 XML 注释里
 * 写了两个连续短横线，文件本身是合法 XML、Maven 编译也通过，直到应用启动时
 * SqlSessionFactory 构建失败才暴露，表现为整个服务起不来。这个测试把那类问题
 * 提前到构建阶段，同时也覆盖 sql/include/foreach 等动态标签的 id 引用错误。
 */
class MapperXmlParseTest
{
    private static final Path MAPPER_ROOT =
            Paths.get("src", "main", "resources", "mapper");

    /** 覆盖 application.yml 里 com.ruoyi.**.domain 通配所指向的实际包 */
    private static final String[] ALIAS_PACKAGES = {
        "com.ruoyi.common.core.domain",
        "com.ruoyi.common.core.domain.entity",
        "com.ruoyi.system.domain",
    };

    @Test
    @DisplayName("全部 mapper XML 都能被 MyBatis 解析")
    void allMapperXmlFilesParse() throws IOException
    {
        List<Path> files = new ArrayList<>();
        try (Stream<Path> walk = Files.walk(MAPPER_ROOT))
        {
            walk.filter(Files::isRegularFile)
                .filter(p -> p.toString().endsWith(".xml"))
                .forEach(files::add);
        }
        assertFalse(files.isEmpty(), "没有找到任何 mapper XML，路径可能不对：" + MAPPER_ROOT.toAbsolutePath());

        List<String> failures = new ArrayList<>();
        for (Path file : files)
        {
            // 每个文件用独立 Configuration，避免同名 namespace 互相干扰，
            // 也保证一个文件的失败不会掩盖后面的文件。
            Configuration configuration = new Configuration();
            // 与 application.yml 的 mybatis.typeAliasesPackage=com.ruoyi.**.domain 对齐。
            // 不注册别名的话，写 type="SysConfig" 这类短名的 mapper 会报
            // ClassNotFoundException，那是测试环境缺配置，不是 mapper 本身的问题。
            for (String pkg : ALIAS_PACKAGES)
            {
                try { configuration.getTypeAliasRegistry().registerAliases(pkg); }
                catch (Exception ignored) { /* 本模块不含该包时跳过 */ }
            }
            try (InputStream in = Files.newInputStream(file))
            {
                new XMLMapperBuilder(in, configuration,
                        file.toString(), configuration.getSqlFragments()).parse();
            }
            catch (Exception ex)
            {
                Throwable root = ex;
                while (root.getCause() != null) root = root.getCause();
                failures.add(file + " -> " + root.getClass().getSimpleName() + ": " + root.getMessage());
            }
        }
        if (!failures.isEmpty())
        {
            fail("以下 mapper XML 无法被 MyBatis 解析，应用启动时会导致 SqlSessionFactory 构建失败：\n"
                    + String.join("\n", failures));
        }
    }
}
