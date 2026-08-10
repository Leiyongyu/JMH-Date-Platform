package com.ruoyi.system.domain.operation.ebay;

import com.fasterxml.jackson.annotation.JsonIgnore;

/** eBay 人工审核候选商品。 */
public class EbayPriceAuditItem extends EbayItemDetail
{
    private Long id;
    private Long taskId;
    private Long auditOeId;
    private Integer rankNo;
    private String imageUrlsJson;
    private String selectedFlag;

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public Long getTaskId() { return taskId; }
    public void setTaskId(Long taskId) { this.taskId = taskId; }
    public Long getAuditOeId() { return auditOeId; }
    public void setAuditOeId(Long auditOeId) { this.auditOeId = auditOeId; }
    public Integer getRankNo() { return rankNo; }
    public void setRankNo(Integer rankNo) { this.rankNo = rankNo; }
    @JsonIgnore
    public String getImageUrlsJson() { return imageUrlsJson; }
    public void setImageUrlsJson(String imageUrlsJson) { this.imageUrlsJson = imageUrlsJson; }
    @JsonIgnore
    public String getSelectedFlag() { return selectedFlag; }
    public void setSelectedFlag(String selectedFlag) { this.selectedFlag = selectedFlag; }
    public boolean isSelected() { return "1".equals(selectedFlag); }
}
