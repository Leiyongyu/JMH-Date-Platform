package com.ruoyi.system.service.operation.ebay;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.time.Duration;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.Locale;
import java.util.UUID;
import com.ruoyi.common.config.RuoYiConfig;
import com.ruoyi.common.constant.Constants;
import com.ruoyi.common.exception.ServiceException;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;

/** 下载并保存eBay竞品主图，只允许eBay图片域名。 */
@Component
public class EbayCompetitorImageStore
{
    private static final long MAX_IMAGE_BYTES = 10L * 1024L * 1024L;
    private static final DateTimeFormatter MONTH = DateTimeFormatter.ofPattern("yyyyMM");
    private final HttpClient httpClient = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(10))
            .followRedirects(HttpClient.Redirect.NORMAL)
            .build();

    public StoredImage download(String imageUrl, String siteCode, String itemId, int sortNo)
    {
        URI uri = validateUrl(imageUrl);
        HttpRequest request = HttpRequest.newBuilder(uri)
                .timeout(Duration.ofSeconds(30))
                .header("Accept", "image/*")
                .GET()
                .build();
        try
        {
            HttpResponse<byte[]> response = httpClient.send(request, HttpResponse.BodyHandlers.ofByteArray());
            if (response.statusCode() < 200 || response.statusCode() >= 300)
            {
                throw new ServiceException("商品图片下载失败[HTTP " + response.statusCode() + "]");
            }
            byte[] bytes = response.body();
            if (bytes == null || bytes.length == 0)
            {
                throw new ServiceException("eBay商品没有可保存的图片");
            }
            if (bytes.length > MAX_IMAGE_BYTES)
            {
                throw new ServiceException("商品图片超过10MB，无法保存");
            }
            String contentType = response.headers().firstValue("Content-Type").orElse("")
                    .toLowerCase(Locale.ROOT);
            if (!contentType.startsWith("image/"))
            {
                throw new ServiceException("eBay商品图片响应格式不正确");
            }

            String extension = extension(contentType);
            String safeSite = safeSegment(siteCode == null ? "unknown" : siteCode.toLowerCase(Locale.ROOT));
            String safeItem = safeSegment(itemId);
            String month = MONTH.format(LocalDate.now());
            Path profile = Path.of(RuoYiConfig.getProfile()).toAbsolutePath().normalize();
            Path directory = profile.resolve("ebay-competitor").resolve(safeSite).resolve(month).normalize();
            if (!directory.startsWith(profile))
            {
                throw new ServiceException("商品图片保存路径不安全");
            }
            Files.createDirectories(directory);
            String filename = safeItem + "-" + Math.max(sortNo, 1) + "-"
                    + UUID.randomUUID().toString().replace("-", "") + extension;
            Path target = directory.resolve(filename).normalize();
            Path temporary = directory.resolve(filename + ".tmp").normalize();
            Files.write(temporary, bytes);
            try
            {
                Files.move(temporary, target, StandardCopyOption.ATOMIC_MOVE);
            }
            catch (AtomicMoveNotSupportedException e)
            {
                Files.move(temporary, target);
            }
            String resourceUrl = Constants.RESOURCE_PREFIX + "/ebay-competitor/" + safeSite
                    + "/" + month + "/" + filename;
            return new StoredImage(resourceUrl, target);
        }
        catch (InterruptedException e)
        {
            Thread.currentThread().interrupt();
            throw new ServiceException("商品图片下载已中断");
        }
        catch (IOException e)
        {
            throw new ServiceException("商品图片保存失败: " + e.getMessage());
        }
    }

    public void deleteQuietly(StoredImage image)
    {
        if (image == null || image.path() == null)
        {
            return;
        }
        try
        {
            Files.deleteIfExists(image.path());
        }
        catch (IOException ignored)
        {
            // 数据库保存失败时尽力清理临时落盘图片，不覆盖原始异常。
        }
    }

    public void deleteByResourceUrlQuietly(String resourceUrl)
    {
        String prefix = Constants.RESOURCE_PREFIX + "/";
        if (!StringUtils.hasText(resourceUrl) || !resourceUrl.startsWith(prefix))
        {
            return;
        }
        try
        {
            Path profile = Path.of(RuoYiConfig.getProfile()).toAbsolutePath().normalize();
            Path allowed = profile.resolve("ebay-competitor").normalize();
            Path target = profile.resolve(resourceUrl.substring(prefix.length())).normalize();
            if (target.startsWith(allowed))
            {
                Files.deleteIfExists(target);
            }
        }
        catch (IOException | RuntimeException ignored)
        {
            // 删除商品后尽力清理本地图片，文件已不存在时无需影响数据库结果。
        }
    }

    private static URI validateUrl(String imageUrl)
    {
        if (!StringUtils.hasText(imageUrl))
        {
            throw new ServiceException("eBay商品没有返回主图，无法保存");
        }
        try
        {
            URI uri = URI.create(imageUrl.trim());
            String host = uri.getHost();
            if (!("https".equalsIgnoreCase(uri.getScheme()) || "http".equalsIgnoreCase(uri.getScheme()))
                    || host == null)
            {
                throw new ServiceException("商品图片地址不正确");
            }
            String normalized = host.toLowerCase(Locale.ROOT);
            if (!(normalized.equals("ebayimg.com") || normalized.endsWith(".ebayimg.com")))
            {
                throw new ServiceException("只允许保存eBay官方图片");
            }
            return uri;
        }
        catch (IllegalArgumentException e)
        {
            throw new ServiceException("商品图片地址不正确");
        }
    }

    private static String safeSegment(String value)
    {
        if (!StringUtils.hasText(value))
        {
            return "unknown";
        }
        return value.replaceAll("[^A-Za-z0-9_-]", "_");
    }

    private static String extension(String contentType)
    {
        if (contentType.contains("png")) return ".png";
        if (contentType.contains("webp")) return ".webp";
        if (contentType.contains("gif")) return ".gif";
        return ".jpg";
    }

    public record StoredImage(String resourceUrl, Path path) {}
}
