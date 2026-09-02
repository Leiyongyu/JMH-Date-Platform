package com.ruoyi.system.domain.operation.ebay;

import java.math.BigDecimal;

/** eBay补货2.0按站点和完整SKU汇总的仓租费用。 */
public class EbayWarehouseRentAggregate
{
    private Long id;
    private String site;
    private String sku;
    private String warehouseCodes;
    private Integer sourceRowCount;
    private BigDecimal warehouseRentAmountCny;
    private String importBatchId;
    private String sourceFileName;
    private String importedBy;

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public String getSite() { return site; }
    public void setSite(String site) { this.site = site; }
    public String getSku() { return sku; }
    public void setSku(String sku) { this.sku = sku; }
    public String getWarehouseCodes() { return warehouseCodes; }
    public void setWarehouseCodes(String warehouseCodes) { this.warehouseCodes = warehouseCodes; }
    public Integer getSourceRowCount() { return sourceRowCount; }
    public void setSourceRowCount(Integer sourceRowCount) { this.sourceRowCount = sourceRowCount; }
    public BigDecimal getWarehouseRentAmountCny() { return warehouseRentAmountCny; }
    public void setWarehouseRentAmountCny(BigDecimal value) { this.warehouseRentAmountCny = value; }
    public String getImportBatchId() { return importBatchId; }
    public void setImportBatchId(String importBatchId) { this.importBatchId = importBatchId; }
    public String getSourceFileName() { return sourceFileName; }
    public void setSourceFileName(String sourceFileName) { this.sourceFileName = sourceFileName; }
    public String getImportedBy() { return importedBy; }
    public void setImportedBy(String importedBy) { this.importedBy = importedBy; }
}
