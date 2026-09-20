package com.ruoyi.system.service.backup;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.*;
import java.security.MessageDigest;
import java.time.LocalDate;
import java.util.HexFormat;
import java.util.List;
import java.util.zip.ZipEntry;
import java.util.zip.ZipOutputStream;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

class MySqlBackupServiceTest
{
    @TempDir Path temp;

    private MySqlBackupService service() throws Exception
    {
        var properties = new MySqlBackupProperties();
        properties.setMysqldumpPath(Files.writeString(temp.resolve("fake-dump.exe"), "never executed").toString());
        properties.setLocalTempDir(temp.resolve("staging").toString());
        properties.setTargetDir(temp.resolve("nas-fixture").toString());
        properties.setDatabases(List.of("db_one", "db_two"));
        var service = spy(new MySqlBackupService(properties, new ObjectMapper()));
        // No real deletions or processes in these tests. Only JUnit temporary fixtures are used.
        doNothing().when(service).deleteTree(any(), any());
        return service;
    }

    @Test void brokenOldDirectoryDoesNotPreventCleaningOtherExpiredDirectories() throws Exception
    {
        var service = service();
        Path root = Files.createDirectory(temp.resolve("old-backups"));
        Path broken = Files.createDirectory(root.resolve("2026-08-06"));
        Path another = Files.createDirectory(root.resolve("2026-08-07_200000"));
        Path retained = Files.createDirectory(root.resolve("2026-08-21"));
        Path current = Files.createDirectory(root.resolve("2026-09-19"));
        Path other = Files.createDirectory(root.resolve("other"));
        Path invalidDate = Files.createDirectory(root.resolve("2026-02-30"));
        Path partial = Files.createDirectory(root.resolve(".partial-test"));
        Path ordinaryFile = Files.writeString(root.resolve("2026-08-05"), "not a directory");
        doThrow(new FileSystemException(broken.resolve("backup.log").toString(), null, "目录名称无效"))
                .when(service).deleteTree(broken, root);

        var result = service.cleanupExpiredBackups(root, LocalDate.of(2026, 9, 19));

        assertEquals(1, result.deletedDirectories());
        assertEquals(1, result.failures().size());
        assertEquals(broken.toString(), result.failures().get(0).path());
        assertTrue(result.failures().get(0).reason().contains("backup.log"));
        verify(service).deleteTree(another, root);
        for (Path untouched : List.of(retained, current, other, invalidDate, partial, ordinaryFile))
            verify(service, never()).deleteTree(eq(untouched), any());
    }

    @Test void deletionAndMetadataErrorsAreIsolatedBeforeNextDirectory() throws Exception
    {
        var service = service();
        Path root = temp.resolve("root");
        Path broken = root.resolve("2026-08-06");
        Path unreadable = root.resolve("2026-08-07");
        Path good = root.resolve("2026-08-08");
        var attrs = mock(java.nio.file.attribute.BasicFileAttributes.class);
        when(attrs.isDirectory()).thenReturn(true);
        doThrow(new IOException("delete failed")).when(service).deleteTree(broken, root);
        try (var files = mockStatic(Files.class))
        {
            files.when(() -> Files.list(root)).thenReturn(java.util.stream.Stream.of(broken, unreadable, good));
            for (Path path : List.of(broken, good))
                files.when(() -> Files.readAttributes(path, java.nio.file.attribute.BasicFileAttributes.class,
                        LinkOption.NOFOLLOW_LINKS)).thenReturn(attrs);
            files.when(() -> Files.readAttributes(unreadable, java.nio.file.attribute.BasicFileAttributes.class,
                    LinkOption.NOFOLLOW_LINKS)).thenThrow(new AccessDeniedException(unreadable.toString()));
            var result = service.cleanupExpiredBackups(root, LocalDate.of(2026, 9, 19));
            assertEquals(1, result.deletedDirectories());
            assertEquals(List.of(broken.toString(), unreadable.toString()),
                    result.failures().stream().map(MySqlBackupService.CleanupFailure::path).toList());
            var order = inOrder(service);
            order.verify(service).deleteTree(broken, root);
            order.verify(service).deleteTree(good, root);
            verify(service, never()).deleteTree(unreadable, root);
        }
    }

    @Test void unreadableRootIsReportedAsCleanupWarning() throws Exception
    {
        var service = service();
        Path missing = temp.resolve("missing");
        var result = service.cleanupExpiredBackups(missing, LocalDate.now());
        assertEquals(0, result.deletedDirectories());
        assertEquals(missing.toString(), result.failures().get(0).path());
        verify(service, never()).deleteTree(any(), any());
    }

    @Test void lazyDirectoryIterationFailureIsAlsoAWarning() throws Exception
    {
        var service = service();
        Path root = temp.resolve("unreadable-listing");
        try (var files = mockStatic(Files.class))
        {
            files.when(() -> Files.list(root)).thenReturn(java.util.stream.Stream.<Path>generate(() -> {
                throw new UncheckedIOException(new IOException("SMB iteration failure"));
            }));
            var result = service.cleanupExpiredBackups(root, LocalDate.now());
            assertEquals(1, result.failures().size());
            assertTrue(result.failures().get(0).reason().contains("SMB iteration failure"));
        }
    }

    @Test void symlinkDirectoryIsNeverDeleted() throws Exception
    {
        var service = service();
        Path root = temp.resolve("root");
        Path path = root.resolve("2026-08-06");
        var attrs = mock(java.nio.file.attribute.BasicFileAttributes.class);
        when(attrs.isDirectory()).thenReturn(true);
        when(attrs.isSymbolicLink()).thenReturn(true);
        try (var files = mockStatic(Files.class))
        {
            files.when(() -> Files.list(root)).thenReturn(java.util.stream.Stream.of(path));
            files.when(() -> Files.readAttributes(path, java.nio.file.attribute.BasicFileAttributes.class,
                    LinkOption.NOFOLLOW_LINKS)).thenReturn(attrs);
            assertTrue(service.cleanupExpiredBackups(root, LocalDate.now()).failures().isEmpty());
            verify(service, never()).deleteTree(any(), any());
        }
    }

    private void stubDump(MySqlBackupService service, boolean badHash) throws Exception
    {
        doAnswer(call -> {
            String database = call.getArgument(0);
            Path directory = call.getArgument(2);
            Path zipFile = directory.resolve(database + ".sql.zip");
            byte[] data = "synthetic test data, not a database dump".getBytes(java.nio.charset.StandardCharsets.UTF_8);
            try (var zip = new ZipOutputStream(Files.newOutputStream(zipFile)))
            {
                zip.putNextEntry(new ZipEntry(database + ".sql"));
                zip.write(data);
                zip.closeEntry();
            }
            String hash = HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(Files.readAllBytes(zipFile)));
            return new MySqlBackupService.BackupArtifact(database, zipFile.getFileName().toString(),
                    database + ".sql", data.length, Files.size(zipFile), badHash ? "bad-hash" : hash);
        }).when(service).backupDatabase(anyString(), anyString(), any(), any());
    }

    @Test void publishedBackupRemainsSuccessfulWhenRetentionFails() throws Exception
    {
        var service = service();
        stubDump(service, false);
        Path root = Files.createDirectory(temp.resolve("nas-fixture"));
        Path old = Files.createDirectory(root.resolve("2020-01-01"));
        doThrow(new IOException("broken old NAS object")).when(service).deleteTree(old, root);

        var result = service.backup();

        assertEquals(2, result.databaseCount());
        assertTrue(result.hasCleanupWarnings());
        assertTrue(result.summary().startsWith("备份成功，过期清理异常"));
        assertTrue(Files.exists(Path.of(result.directory()).resolve("db_one.sql.zip")));
        assertTrue(Files.exists(Path.of(result.directory()).resolve("db_two.sql.zip")));
        assertTrue(Files.exists(Path.of(result.directory()).resolve("SHA256SUMS.txt")));
    }

    @Test void healthyBackupHasNoCleanupWarning() throws Exception
    {
        var service = service();
        stubDump(service, false);
        var result = service.backup();
        assertFalse(result.hasCleanupWarnings());
        assertEquals("", result.cleanupWarning());
    }

    @Test void dumpFailureStillFailsAndDoesNotCleanOldBackups() throws Exception
    {
        var service = service();
        doThrow(new IOException("dump failed")).when(service).backupDatabase(anyString(), anyString(), any(), any());
        assertThrows(IllegalStateException.class, service::backup);
        verify(service, never()).cleanupExpiredBackups(any(), any());
        verify(service, never()).deleteTree(any(), any());
    }

    @Test void publicationHashMismatchStillFailsAndDoesNotRunRetention() throws Exception
    {
        var service = service();
        stubDump(service, true);
        var error = assertThrows(IllegalStateException.class, service::backup);
        assertTrue(error.getMessage().contains("复制到NAS后校验失败"));
        verify(service, never()).cleanupExpiredBackups(any(), any());
    }

    @Test void deletionGuardStillRejectsRootAndPathsOutsideParent() throws Exception
    {
        var service = service();
        doCallRealMethod().when(service).deleteTree(any(), any());
        assertThrows(IllegalStateException.class, () -> service.deleteTree(temp, temp));
        assertThrows(IllegalStateException.class, () -> service.deleteTree(temp.resolveSibling("outside"), temp));
    }
}
