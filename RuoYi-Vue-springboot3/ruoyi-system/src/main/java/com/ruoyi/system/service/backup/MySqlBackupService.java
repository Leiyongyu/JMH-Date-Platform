package com.ruoyi.system.service.backup;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.BufferedInputStream;
import java.io.BufferedOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.FileVisitResult;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.StandardCopyOption;
import java.nio.file.StandardOpenOption;
import java.nio.file.attribute.BasicFileAttributes;
import java.security.MessageDigest;
import java.time.Duration;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.zip.ZipEntry;
import java.util.zip.ZipFile;
import java.util.zip.ZipOutputStream;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

/** 使用mysqldump生成可恢复SQL，并安全发布到NAS。 */
@Service
public class MySqlBackupService
{
    private static final Logger log = LoggerFactory.getLogger(MySqlBackupService.class);
    private static final DateTimeFormatter RUN_TIME =
            DateTimeFormatter.ofPattern("yyyyMMdd_HHmmss");
    private static final DateTimeFormatter DIRECTORY_DATE =
            DateTimeFormatter.ISO_LOCAL_DATE;
    private static final Pattern DATABASE_NAME =
            Pattern.compile("[A-Za-z0-9_$-]+");
    private static final Pattern BACKUP_DIRECTORY =
            Pattern.compile("^(\\d{4}-\\d{2}-\\d{2})(?:_\\d{6})?$");

    private final MySqlBackupProperties properties;
    private final ObjectMapper objectMapper;
    private final AtomicBoolean running = new AtomicBoolean(false);

    public MySqlBackupService(
            MySqlBackupProperties properties,
            ObjectMapper objectMapper)
    {
        this.properties = properties;
        this.objectMapper = objectMapper;
    }

    public BackupResult backup()
    {
        if (!properties.isEnabled())
            throw new IllegalStateException("MySQL备份功能未启用");
        if (!running.compareAndSet(false, true))
            throw new IllegalStateException("MySQL备份任务正在执行，请勿重复运行");

        long started = System.currentTimeMillis();
        Path stagingDirectory = null;
        boolean published = false;
        try
        {
            validateConfiguration();
            LocalDateTime now = LocalDateTime.now();
            String runId = now.format(RUN_TIME);
            Path localRoot = absolutePath(properties.getLocalTempDir());
            Path targetRoot = absolutePath(properties.getTargetDir());
            Files.createDirectories(localRoot);
            Files.createDirectories(targetRoot);

            stagingDirectory = localRoot.resolve(
                    ".mysql-backup-" + runId + "-"
                    + UUID.randomUUID().toString().replace("-", ""))
                    .normalize();
            requireDirectChild(localRoot, stagingDirectory);
            Files.createDirectory(stagingDirectory);

            Path backupLog = stagingDirectory.resolve("backup.log");
            appendLog(backupLog, "备份开始：" + now);
            appendLog(backupLog, "数据库："
                    + String.join(", ", properties.getDatabases()));

            List<BackupArtifact> artifacts = new ArrayList<>();
            long totalBytes = 0L;
            for (String database : properties.getDatabases())
            {
                BackupArtifact artifact = backupDatabase(
                        database, runId, stagingDirectory, backupLog);
                artifacts.add(artifact);
                totalBytes += artifact.compressedBytes();
            }

            writeChecksumFile(stagingDirectory, artifacts);
            writeRestoreGuide(stagingDirectory, artifacts);
            writeManifest(stagingDirectory, now, artifacts, totalBytes);
            appendLog(backupLog, "本地备份、压缩与校验完成");

            Path publishedDirectory = publish(
                    stagingDirectory, targetRoot, now.toLocalDate(), runId,
                    artifacts);
            published = true;
            int deletedDirectories = cleanupExpiredBackups(
                    targetRoot, now.toLocalDate());
            long duration = System.currentTimeMillis() - started;
            log.info("MySQL备份完成：目录={}，数据库={}，压缩后={}字节，清理目录={}，耗时={}ms",
                    publishedDirectory, artifacts.size(), totalBytes,
                    deletedDirectories, duration);
            return new BackupResult(
                    publishedDirectory.toString(), artifacts.size(),
                    totalBytes, deletedDirectories, duration);
        }
        catch (Exception e)
        {
            log.error("MySQL备份失败，本地诊断目录={}：{}",
                    stagingDirectory, e.getMessage(), e);
            throw e instanceof RuntimeException
                    ? (RuntimeException) e
                    : new IllegalStateException("MySQL备份失败：" + e.getMessage(), e);
        }
        finally
        {
            if (published && stagingDirectory != null)
            {
                try { deleteTree(stagingDirectory, stagingDirectory.getParent()); }
                catch (Exception e) { log.warn("本地备份临时目录清理失败：{}", stagingDirectory, e); }
            }
            running.set(false);
        }
    }

    private BackupArtifact backupDatabase(
            String database,
            String runId,
            Path stagingDirectory,
            Path backupLog) throws Exception
    {
        String safeName = database.toLowerCase(Locale.ROOT)
                .replaceAll("[^a-z0-9_-]", "_");
        String baseName = safeName + "_" + runId;
        Path sqlFile = stagingDirectory.resolve(baseName + ".sql");
        Path zipFile = stagingDirectory.resolve(baseName + ".sql.zip");
        appendLog(backupLog, "开始导出数据库：" + database);

        List<String> command = List.of(
                absolutePath(properties.getMysqldumpPath()).toString(),
                "--login-path=" + properties.getLoginPath(),
                "--protocol=tcp",
                "--single-transaction",
                "--quick",
                "--routines",
                "--events",
                "--triggers",
                "--hex-blob",
                "--no-tablespaces",
                "--set-gtid-purged=OFF",
                "--default-character-set=utf8mb4",
                "--databases", database,
                "--result-file=" + sqlFile.toAbsolutePath());

        ProcessBuilder builder = new ProcessBuilder(command);
        builder.redirectErrorStream(true);
        builder.redirectOutput(ProcessBuilder.Redirect.appendTo(backupLog.toFile()));
        Process process = builder.start();
        boolean finished = process.waitFor(
                properties.getTimeoutMinutes(), TimeUnit.MINUTES);
        if (!finished)
        {
            process.destroyForcibly();
            process.waitFor(10, TimeUnit.SECONDS);
            throw new IllegalStateException(
                    database + "备份超过"
                    + properties.getTimeoutMinutes() + "分钟，已终止");
        }
        if (process.exitValue() != 0)
            throw new IllegalStateException(
                    database + "的mysqldump执行失败，退出码="
                    + process.exitValue() + "，详情见backup.log");
        if (!Files.isRegularFile(sqlFile)
                || Files.size(sqlFile) < properties.getMinimumDumpBytes())
            throw new IllegalStateException(
                    database + "导出文件不存在或小于最低有效大小");

        long originalBytes = Files.size(sqlFile);
        zipSql(sqlFile, zipFile);
        verifyZip(zipFile, sqlFile.getFileName().toString(), originalBytes);
        Files.delete(sqlFile);
        String sha256 = sha256(zipFile);
        long compressedBytes = Files.size(zipFile);
        appendLog(backupLog, "数据库导出完成：" + database
                + "，SQL=" + originalBytes + "字节，ZIP="
                + compressedBytes + "字节，SHA-256=" + sha256);
        return new BackupArtifact(
                database, zipFile.getFileName().toString(),
                sqlFile.getFileName().toString(), originalBytes,
                compressedBytes, sha256);
    }

    private void validateConfiguration()
    {
        Path mysqldump = absolutePath(properties.getMysqldumpPath());
        if (!Files.isRegularFile(mysqldump, LinkOption.NOFOLLOW_LINKS))
            throw new IllegalStateException("mysqldump不存在：" + mysqldump);
        if (!StringUtils.hasText(properties.getLoginPath()))
            throw new IllegalStateException("mysql-login-path不能为空");
        if (properties.getDatabases() == null || properties.getDatabases().isEmpty())
            throw new IllegalStateException("至少配置一个待备份数据库");
        for (String database : properties.getDatabases())
            if (!StringUtils.hasText(database)
                    || !DATABASE_NAME.matcher(database).matches())
                throw new IllegalStateException("非法数据库名称：" + database);
        if (properties.getRetentionDays() < 1)
            throw new IllegalStateException("retention-days必须大于0");
        if (properties.getTimeoutMinutes() < 1)
            throw new IllegalStateException("timeout-minutes必须大于0");
        if (properties.getMinimumDumpBytes() < 1)
            throw new IllegalStateException("minimum-dump-bytes必须大于0");
    }

    private Path publish(
            Path stagingDirectory,
            Path targetRoot,
            LocalDate backupDate,
            String runId,
            List<BackupArtifact> artifacts) throws Exception
    {
        String dateName = backupDate.format(DIRECTORY_DATE);
        Path finalDirectory = targetRoot.resolve(dateName).normalize();
        if (Files.exists(finalDirectory, LinkOption.NOFOLLOW_LINKS))
            finalDirectory = targetRoot.resolve(
                    dateName + "_" + runId.substring(9)).normalize();
        requireDirectChild(targetRoot, finalDirectory);

        Path partialDirectory = targetRoot.resolve(
                ".partial-" + runId + "-"
                + UUID.randomUUID().toString().replace("-", ""))
                .normalize();
        requireDirectChild(targetRoot, partialDirectory);
        try
        {
            copyDirectory(stagingDirectory, partialDirectory);
            for (BackupArtifact artifact : artifacts)
            {
                Path copied = partialDirectory.resolve(artifact.fileName());
                if (!artifact.sha256().equalsIgnoreCase(sha256(copied)))
                    throw new IllegalStateException(
                            artifact.database() + "复制到NAS后校验失败");
            }
            try
            {
                Files.move(partialDirectory, finalDirectory,
                        StandardCopyOption.ATOMIC_MOVE);
            }
            catch (AtomicMoveNotSupportedException ignored)
            {
                Files.move(partialDirectory, finalDirectory);
            }
            return finalDirectory;
        }
        catch (Exception e)
        {
            if (Files.exists(partialDirectory, LinkOption.NOFOLLOW_LINKS))
                deleteTree(partialDirectory, targetRoot);
            throw e;
        }
    }

    private int cleanupExpiredBackups(Path targetRoot, LocalDate today)
            throws IOException
    {
        LocalDate oldestRetainedDate = today.minusDays(
                properties.getRetentionDays() - 1L);
        int deleted = 0;
        try (var paths = Files.list(targetRoot))
        {
            for (Path path : paths.toList())
            {
                if (!Files.isDirectory(path, LinkOption.NOFOLLOW_LINKS)
                        || Files.isSymbolicLink(path))
                    continue;
                Matcher matcher = BACKUP_DIRECTORY.matcher(
                        path.getFileName().toString());
                if (!matcher.matches()) continue;
                LocalDate directoryDate;
                try { directoryDate = LocalDate.parse(matcher.group(1)); }
                catch (Exception ignored) { continue; }
                if (directoryDate.isBefore(oldestRetainedDate))
                {
                    deleteTree(path, targetRoot);
                    deleted++;
                }
            }
        }
        return deleted;
    }

    private void writeManifest(
            Path directory,
            LocalDateTime backupTime,
            List<BackupArtifact> artifacts,
            long totalBytes) throws IOException
    {
        List<Map<String, Object>> files = artifacts.stream().map(item -> {
            Map<String, Object> value = new LinkedHashMap<>();
            value.put("database", item.database());
            value.put("archive", item.fileName());
            value.put("sql_entry", item.sqlEntryName());
            value.put("sql_bytes", item.originalBytes());
            value.put("archive_bytes", item.compressedBytes());
            value.put("sha256", item.sha256());
            return value;
        }).toList();
        Map<String, Object> manifest = new LinkedHashMap<>();
        manifest.put("status", "completed");
        manifest.put("backup_time", backupTime.toString());
        manifest.put("backup_type", "mysql_logical_full");
        manifest.put("mysqldump", absolutePath(properties.getMysqldumpPath()).toString());
        manifest.put("login_path", properties.getLoginPath());
        manifest.put("retention_days", properties.getRetentionDays());
        manifest.put("total_archive_bytes", totalBytes);
        manifest.put("files", files);
        objectMapper.writerWithDefaultPrettyPrinter().writeValue(
                directory.resolve("manifest.json").toFile(), manifest);
    }

    private void writeChecksumFile(
            Path directory, List<BackupArtifact> artifacts) throws IOException
    {
        StringBuilder content = new StringBuilder();
        for (BackupArtifact artifact : artifacts)
            content.append(artifact.sha256()).append("  ")
                    .append(artifact.fileName()).append(System.lineSeparator());
        Files.writeString(directory.resolve("SHA256SUMS.txt"), content,
                StandardCharsets.UTF_8, StandardOpenOption.CREATE_NEW);
    }

    private void writeRestoreGuide(
            Path directory, List<BackupArtifact> artifacts) throws IOException
    {
        StringBuilder guide = new StringBuilder();
        guide.append("MySQL备份恢复说明").append(System.lineSeparator())
                .append("1. 使用Windows“解压缩全部”或Expand-Archive解压目标ZIP。")
                .append(System.lineSeparator())
                .append("2. 使用具备恢复权限的MySQL账号进入mysql客户端。")
                .append(System.lineSeparator())
                .append("3. 在mysql客户端执行SOURCE命令，路径请使用正斜杠。")
                .append(System.lineSeparator()).append(System.lineSeparator());
        for (BackupArtifact artifact : artifacts)
            guide.append(artifact.database()).append(": SOURCE D:/restore/")
                    .append(artifact.sqlEntryName()).append(";")
                    .append(System.lineSeparator());
        guide.append(System.lineSeparator())
                .append("恢复前请先核对SHA256SUMS.txt，并优先恢复到临时实例演练。")
                .append(System.lineSeparator());
        Files.writeString(directory.resolve("RESTORE.txt"), guide,
                StandardCharsets.UTF_8, StandardOpenOption.CREATE_NEW);
    }

    private void zipSql(Path sqlFile, Path zipFile) throws IOException
    {
        try (OutputStream fileOutput = Files.newOutputStream(
                    zipFile, StandardOpenOption.CREATE_NEW);
             ZipOutputStream zip = new ZipOutputStream(
                    new BufferedOutputStream(fileOutput));
             InputStream input = new BufferedInputStream(
                    Files.newInputStream(sqlFile)))
        {
            zip.putNextEntry(new ZipEntry(sqlFile.getFileName().toString()));
            input.transferTo(zip);
            zip.closeEntry();
        }
    }

    private void verifyZip(
            Path zipFile, String expectedEntry, long expectedBytes)
            throws IOException
    {
        try (ZipFile zip = new ZipFile(zipFile.toFile()))
        {
            ZipEntry entry = zip.getEntry(expectedEntry);
            if (entry == null || entry.isDirectory())
                throw new IOException("ZIP中缺少SQL文件：" + expectedEntry);
            long bytes;
            try (InputStream input = zip.getInputStream(entry))
            {
                bytes = input.transferTo(OutputStream.nullOutputStream());
            }
            if (bytes != expectedBytes)
                throw new IOException("ZIP解压校验大小不一致：" + expectedEntry);
        }
    }

    private String sha256(Path path) throws Exception
    {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        try (InputStream input = new BufferedInputStream(
                Files.newInputStream(path)))
        {
            byte[] buffer = new byte[64 * 1024];
            int read;
            while ((read = input.read(buffer)) >= 0)
                if (read > 0) digest.update(buffer, 0, read);
        }
        return HexFormat.of().formatHex(digest.digest());
    }

    private void copyDirectory(Path source, Path target) throws IOException
    {
        Files.walkFileTree(source, new SimpleFileVisitor<>()
        {
            @Override
            public FileVisitResult preVisitDirectory(
                    Path dir, BasicFileAttributes attrs) throws IOException
            {
                if (Files.isSymbolicLink(dir))
                    throw new IOException("备份目录不允许符号链接：" + dir);
                Path relative = source.relativize(dir);
                Files.createDirectories(target.resolve(relative));
                return FileVisitResult.CONTINUE;
            }

            @Override
            public FileVisitResult visitFile(
                    Path file, BasicFileAttributes attrs) throws IOException
            {
                if (Files.isSymbolicLink(file))
                    throw new IOException("备份文件不允许符号链接：" + file);
                Files.copy(file, target.resolve(source.relativize(file)));
                return FileVisitResult.CONTINUE;
            }
        });
    }

    private void deleteTree(Path target, Path allowedParent) throws IOException
    {
        Path normalizedTarget = target.toAbsolutePath().normalize();
        requireDirectChild(allowedParent.toAbsolutePath().normalize(), normalizedTarget);
        Files.walkFileTree(normalizedTarget, new SimpleFileVisitor<>()
        {
            @Override
            public FileVisitResult visitFile(
                    Path file, BasicFileAttributes attrs) throws IOException
            {
                Files.delete(file);
                return FileVisitResult.CONTINUE;
            }

            @Override
            public FileVisitResult postVisitDirectory(
                    Path dir, IOException exc) throws IOException
            {
                if (exc != null) throw exc;
                Files.delete(dir);
                return FileVisitResult.CONTINUE;
            }
        });
    }

    private void requireDirectChild(Path parent, Path child)
    {
        Path normalizedParent = parent.toAbsolutePath().normalize();
        Path normalizedChild = child.toAbsolutePath().normalize();
        if (normalizedChild.equals(normalizedParent)
                || !normalizedChild.startsWith(normalizedParent)
                || !normalizedParent.equals(normalizedChild.getParent()))
            throw new IllegalStateException("拒绝操作非目标目录的路径：" + child);
    }

    private Path absolutePath(String value)
    {
        if (!StringUtils.hasText(value))
            throw new IllegalStateException("备份路径配置不能为空");
        return Paths.get(value).toAbsolutePath().normalize();
    }

    private void appendLog(Path logFile, String message) throws IOException
    {
        String line = LocalDateTime.now() + " " + message + System.lineSeparator();
        Files.writeString(logFile, line, StandardCharsets.UTF_8,
                StandardOpenOption.CREATE, StandardOpenOption.APPEND);
    }

    private record BackupArtifact(
            String database,
            String fileName,
            String sqlEntryName,
            long originalBytes,
            long compressedBytes,
            String sha256)
    {
    }

    public record BackupResult(
            String directory,
            int databaseCount,
            long totalBytes,
            int deletedDirectories,
            long durationMillis)
    {
        public String summary()
        {
            return "目录=" + directory
                    + "，数据库=" + databaseCount
                    + "，压缩后=" + totalBytes + "字节"
                    + "，清理目录=" + deletedDirectories
                    + "，耗时=" + Duration.ofMillis(durationMillis).toSeconds()
                    + "秒";
        }
    }
}
