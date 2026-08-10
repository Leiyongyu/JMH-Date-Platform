package com.ruoyi.system.domain.operation.ebay;

import java.time.LocalDateTime;

/** eBay 价格批量审核任务。 */
public class EbayPriceAuditTask
{
    private Long id;
    private String taskName;
    private String sourceFileName;
    private String site;
    private String status;
    private Integer totalRows;
    private Integer totalOe;
    private Integer duplicateOe;
    private Integer blankRows;
    private Integer processedOe;
    private Integer successOe;
    private Integer emptyOe;
    private Integer failedOe;
    private Integer reviewedOe;
    private Integer selectedCount;
    private Long userId;
    private String createBy;
    private LocalDateTime createTime;
    private LocalDateTime updateTime;
    private LocalDateTime queryEndTime;

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public String getTaskName() { return taskName; }
    public void setTaskName(String taskName) { this.taskName = taskName; }
    public String getSourceFileName() { return sourceFileName; }
    public void setSourceFileName(String sourceFileName) { this.sourceFileName = sourceFileName; }
    public String getSite() { return site; }
    public void setSite(String site) { this.site = site; }
    public String getStatus() { return status; }
    public void setStatus(String status) { this.status = status; }
    public Integer getTotalRows() { return totalRows; }
    public void setTotalRows(Integer totalRows) { this.totalRows = totalRows; }
    public Integer getTotalOe() { return totalOe; }
    public void setTotalOe(Integer totalOe) { this.totalOe = totalOe; }
    public Integer getDuplicateOe() { return duplicateOe; }
    public void setDuplicateOe(Integer duplicateOe) { this.duplicateOe = duplicateOe; }
    public Integer getBlankRows() { return blankRows; }
    public void setBlankRows(Integer blankRows) { this.blankRows = blankRows; }
    public Integer getProcessedOe() { return processedOe; }
    public void setProcessedOe(Integer processedOe) { this.processedOe = processedOe; }
    public Integer getSuccessOe() { return successOe; }
    public void setSuccessOe(Integer successOe) { this.successOe = successOe; }
    public Integer getEmptyOe() { return emptyOe; }
    public void setEmptyOe(Integer emptyOe) { this.emptyOe = emptyOe; }
    public Integer getFailedOe() { return failedOe; }
    public void setFailedOe(Integer failedOe) { this.failedOe = failedOe; }
    public Integer getReviewedOe() { return reviewedOe; }
    public void setReviewedOe(Integer reviewedOe) { this.reviewedOe = reviewedOe; }
    public Integer getSelectedCount() { return selectedCount; }
    public void setSelectedCount(Integer selectedCount) { this.selectedCount = selectedCount; }
    public Long getUserId() { return userId; }
    public void setUserId(Long userId) { this.userId = userId; }
    public String getCreateBy() { return createBy; }
    public void setCreateBy(String createBy) { this.createBy = createBy; }
    public LocalDateTime getCreateTime() { return createTime; }
    public void setCreateTime(LocalDateTime createTime) { this.createTime = createTime; }
    public LocalDateTime getUpdateTime() { return updateTime; }
    public void setUpdateTime(LocalDateTime updateTime) { this.updateTime = updateTime; }
    public LocalDateTime getQueryEndTime() { return queryEndTime; }
    public void setQueryEndTime(LocalDateTime queryEndTime) { this.queryEndTime = queryEndTime; }
}
