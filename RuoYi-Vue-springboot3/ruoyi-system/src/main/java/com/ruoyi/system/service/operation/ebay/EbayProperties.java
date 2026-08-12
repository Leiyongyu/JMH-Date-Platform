package com.ruoyi.system.service.operation.ebay;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

/**
 * eBay 官方 Browse API 配置。密钥只允许从服务端配置注入。
 */
@Component
@ConfigurationProperties(prefix = "ebay")
public class EbayProperties
{
    private String baseUrl = "https://api.ebay.com";
    private String clientId = "";
    private String clientSecret = "";
    private String endUserContext = "";
    private Duration connectTimeout = Duration.ofSeconds(10);
    private Duration requestTimeout = Duration.ofSeconds(30);
    private int searchLimit = 30;
    private int searchTopN = 10;
    private int searchMaxKeywords = 50;
    private int searchMaxWorkers = 8;
    private int detailMaxWorkers = 8;
    private int detailMaxRetries = 3;
    private int auditMaxOes = 2000;
    private int auditMaxConcurrentTasks = 3;

    public String getBaseUrl() { return baseUrl; }
    public void setBaseUrl(String baseUrl) { this.baseUrl = baseUrl; }
    public String getClientId() { return clientId; }
    public void setClientId(String clientId) { this.clientId = clientId; }
    public String getClientSecret() { return clientSecret; }
    public void setClientSecret(String clientSecret) { this.clientSecret = clientSecret; }
    public String getEndUserContext() { return endUserContext; }
    public void setEndUserContext(String endUserContext) { this.endUserContext = endUserContext; }
    public Duration getConnectTimeout() { return connectTimeout; }
    public void setConnectTimeout(Duration connectTimeout) { this.connectTimeout = connectTimeout; }
    public Duration getRequestTimeout() { return requestTimeout; }
    public void setRequestTimeout(Duration requestTimeout) { this.requestTimeout = requestTimeout; }
    public int getSearchLimit() { return searchLimit; }
    public void setSearchLimit(int searchLimit) { this.searchLimit = searchLimit; }
    public int getSearchTopN() { return searchTopN; }
    public void setSearchTopN(int searchTopN) { this.searchTopN = searchTopN; }
    public int getSearchMaxKeywords() { return searchMaxKeywords; }
    public void setSearchMaxKeywords(int searchMaxKeywords) { this.searchMaxKeywords = searchMaxKeywords; }
    public int getSearchMaxWorkers() { return searchMaxWorkers; }
    public void setSearchMaxWorkers(int searchMaxWorkers) { this.searchMaxWorkers = searchMaxWorkers; }
    public int getDetailMaxWorkers() { return detailMaxWorkers; }
    public void setDetailMaxWorkers(int detailMaxWorkers) { this.detailMaxWorkers = detailMaxWorkers; }
    public int getDetailMaxRetries() { return detailMaxRetries; }
    public void setDetailMaxRetries(int detailMaxRetries) { this.detailMaxRetries = detailMaxRetries; }
    public int getAuditMaxOes() { return auditMaxOes; }
    public void setAuditMaxOes(int auditMaxOes) { this.auditMaxOes = auditMaxOes; }
    public int getAuditMaxConcurrentTasks() { return auditMaxConcurrentTasks; }
    public void setAuditMaxConcurrentTasks(int auditMaxConcurrentTasks) { this.auditMaxConcurrentTasks = auditMaxConcurrentTasks; }
}
