package com.ruoyi.system.domain.operation.ebay;

import java.time.LocalDateTime;

/** eBay 批量任务中的单个 OE 查询与审核状态。 */
public class EbayPriceAuditOe
{
    private Long id;
    private Long taskId;
    private Integer sortNo;
    private String oe;
    private String queryStatus;
    private String reviewStatus;
    private Integer resultCount;
    private Integer selectedCount;
    private Integer queryAttempts;
    private String errorMessage;
    private LocalDateTime queryStartTime;
    private LocalDateTime queryEndTime;
    private String reviewBy;
    private LocalDateTime reviewTime;

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public Long getTaskId() { return taskId; }
    public void setTaskId(Long taskId) { this.taskId = taskId; }
    public Integer getSortNo() { return sortNo; }
    public void setSortNo(Integer sortNo) { this.sortNo = sortNo; }
    public String getOe() { return oe; }
    public void setOe(String oe) { this.oe = oe; }
    public String getQueryStatus() { return queryStatus; }
    public void setQueryStatus(String queryStatus) { this.queryStatus = queryStatus; }
    public String getReviewStatus() { return reviewStatus; }
    public void setReviewStatus(String reviewStatus) { this.reviewStatus = reviewStatus; }
    public Integer getResultCount() { return resultCount; }
    public void setResultCount(Integer resultCount) { this.resultCount = resultCount; }
    public Integer getSelectedCount() { return selectedCount; }
    public void setSelectedCount(Integer selectedCount) { this.selectedCount = selectedCount; }
    public Integer getQueryAttempts() { return queryAttempts; }
    public void setQueryAttempts(Integer queryAttempts) { this.queryAttempts = queryAttempts; }
    public String getErrorMessage() { return errorMessage; }
    public void setErrorMessage(String errorMessage) { this.errorMessage = errorMessage; }
    public LocalDateTime getQueryStartTime() { return queryStartTime; }
    public void setQueryStartTime(LocalDateTime queryStartTime) { this.queryStartTime = queryStartTime; }
    public LocalDateTime getQueryEndTime() { return queryEndTime; }
    public void setQueryEndTime(LocalDateTime queryEndTime) { this.queryEndTime = queryEndTime; }
    public String getReviewBy() { return reviewBy; }
    public void setReviewBy(String reviewBy) { this.reviewBy = reviewBy; }
    public LocalDateTime getReviewTime() { return reviewTime; }
    public void setReviewTime(LocalDateTime reviewTime) { this.reviewTime = reviewTime; }
}
