package com.ruoyi.system.domain.operation;

import java.util.List;

/**
 * eBay补货列表搜索请求 —— 兼容旧项目列头筛选体验，所有筛选下推到 SQL。
 */
public class EbayReplenishmentSearchRequest
{
    /** 多字段筛选条件 */
    private List<FilterItem> filters;

    /** 排序字段（白名单内的列名） */
    private String sortField;

    /** 排序方向：ascending / descending */
    private String sortOrder;

    /** 页码 */
    private Integer pageNum;

    /** 每页大小 */
    private Integer pageSize;

    public List<FilterItem> getFilters() { return filters; }
    public void setFilters(List<FilterItem> filters) { this.filters = filters; }
    public String getSortField() { return sortField; }
    public void setSortField(String sortField) { this.sortField = sortField; }
    public String getSortOrder() { return sortOrder; }
    public void setSortOrder(String sortOrder) { this.sortOrder = sortOrder; }
    public Integer getPageNum() { return pageNum; }
    public void setPageNum(Integer pageNum) { this.pageNum = pageNum; }
    public Integer getPageSize() { return pageSize; }
    public void setPageSize(Integer pageSize) { this.pageSize = pageSize; }

    /**
     * 单个筛选条件。
     * 字段名 field 在后端映射到白名单列名，不允许前端传原始 SQL。
     */
    public static class FilterItem
    {
        private String field;
        private String value;

        public FilterItem() {}
        public FilterItem(String field, String value) { this.field = field; this.value = value; }

        public String getField() { return field; }
        public void setField(String field) { this.field = field; }
        public String getValue() { return value; }
        public void setValue(String value) { this.value = value; }
    }
}
