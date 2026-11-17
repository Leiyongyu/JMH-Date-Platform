package com.ruoyi.system.domain.operation;

/** 混销查询：完整仓库SKU，库存与销量按店铺/MSKU匹配。 */
public class AmzMixedSalesQuery
{
    private String sku;
    private String productName;
    private Integer sid;
    private int pageNum = 1;
    private int pageSize = 50;
    private String sortField;
    private String sortOrder;
    private String calculationVersion;
    private String statMonth;
    private Integer ageBucket;

    public Integer getAgeBucket() { return ageBucket; }
    public void setAgeBucket(Integer ageBucket) { this.ageBucket = ageBucket; }

    public String getStatMonth() { return statMonth; }
    public void setStatMonth(String statMonth) { this.statMonth = statMonth; }

    public String getCalculationVersion() { return calculationVersion; }
    public void setCalculationVersion(String calculationVersion) { this.calculationVersion = calculationVersion; }

    public String getSku() { return sku; }
    public void setSku(String sku) { this.sku = sku; }
    public String getProductName() { return productName; }
    public void setProductName(String productName) { this.productName = productName; }
    public Integer getSid() { return sid; }
    public void setSid(Integer sid) { this.sid = sid; }
    public int getPageNum() { return pageNum; }
    public void setPageNum(int pageNum) { this.pageNum = pageNum; }
    public int getPageSize() { return pageSize; }
    public void setPageSize(int pageSize) { this.pageSize = pageSize; }
    public String getSortField() { return sortField; }
    public void setSortField(String sortField) { this.sortField = sortField; }
    public String getSortOrder() { return sortOrder; }
    public void setSortOrder(String sortOrder) { this.sortOrder = sortOrder; }
    public long getOffset() { return ((long) pageNum - 1) * pageSize; }
}
