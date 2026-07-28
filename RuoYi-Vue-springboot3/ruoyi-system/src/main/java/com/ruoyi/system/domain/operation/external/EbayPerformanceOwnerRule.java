package com.ruoyi.system.domain.operation.external;

/** eBay 月度绩效品牌负责人规则。 */
public class EbayPerformanceOwnerRule
{
    private String statMonth;
    private String brandCode;
    private String principalName;
    private String sourceFileName;
    private String sourceSheet;
    private Integer sourceRow;
    private String importedBy;

    public String getStatMonth()
    {
        return statMonth;
    }

    public void setStatMonth(String statMonth)
    {
        this.statMonth = statMonth;
    }

    public String getBrandCode()
    {
        return brandCode;
    }

    public void setBrandCode(String brandCode)
    {
        this.brandCode = brandCode;
    }

    public String getPrincipalName()
    {
        return principalName;
    }

    public void setPrincipalName(String principalName)
    {
        this.principalName = principalName;
    }

    public String getSourceFileName()
    {
        return sourceFileName;
    }

    public void setSourceFileName(String sourceFileName)
    {
        this.sourceFileName = sourceFileName;
    }

    public String getSourceSheet()
    {
        return sourceSheet;
    }

    public void setSourceSheet(String sourceSheet)
    {
        this.sourceSheet = sourceSheet;
    }

    public Integer getSourceRow()
    {
        return sourceRow;
    }

    public void setSourceRow(Integer sourceRow)
    {
        this.sourceRow = sourceRow;
    }

    public String getImportedBy()
    {
        return importedBy;
    }

    public void setImportedBy(String importedBy)
    {
        this.importedBy = importedBy;
    }
}
