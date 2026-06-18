package com.ruoyi.system.domain.operation;

import java.util.List;

/**
 * 统一导出请求 —— 三页面通用。
 * scope: FILTERED(筛选结果) / SELECTED(选中行) / ALL(全部)
 */
public class ExportRequest
{
    private String scope;
    private List<String> rowKeys;
    private List<EbayReplenishmentSearchRequest.FilterItem> filters;
    private String sortField;
    private String sortOrder;
    private List<ColumnDef> columns;

    public String getScope() { return scope; }
    public void setScope(String scope) { this.scope = scope; }
    public List<String> getRowKeys() { return rowKeys; }
    public void setRowKeys(List<String> rowKeys) { this.rowKeys = rowKeys; }
    public List<EbayReplenishmentSearchRequest.FilterItem> getFilters() { return filters; }
    public void setFilters(List<EbayReplenishmentSearchRequest.FilterItem> filters) { this.filters = filters; }
    public String getSortField() { return sortField; }
    public void setSortField(String sortField) { this.sortField = sortField; }
    public String getSortOrder() { return sortOrder; }
    public void setSortOrder(String sortOrder) { this.sortOrder = sortOrder; }
    public List<ColumnDef> getColumns() { return columns; }
    public void setColumns(List<ColumnDef> columns) { this.columns = columns; }

    public static class ColumnDef
    {
        private String key;
        private String title;
        public String getKey() { return key; }
        public void setKey(String key) { this.key = key; }
        public String getTitle() { return title; }
        public void setTitle(String title) { this.title = title; }
    }
}
