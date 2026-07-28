package com.ruoyi.system.domain.operation.external;

/** Amazon 月度绩效负责人匹配规则。 */
public class AmzPerformanceOwnerRule
{
    private Long id;
    private String statMonth;
    private String groupCode;
    private String ruleType;
    private String matchKey;
    private String principalName;
    private String sourceFileName;
    private String sourceSheet;
    private Integer sourceRow;
    private String importedBy;

    public Long getId()
    {
        return id;
    }

    public void setId(Long id)
    {
        this.id = id;
    }

    public String getStatMonth()
    {
        return statMonth;
    }

    public void setStatMonth(String statMonth)
    {
        this.statMonth = statMonth;
    }

    public String getGroupCode()
    {
        return groupCode;
    }

    public void setGroupCode(String groupCode)
    {
        this.groupCode = groupCode;
    }

    public String getRuleType()
    {
        return ruleType;
    }

    public void setRuleType(String ruleType)
    {
        this.ruleType = ruleType;
    }

    public String getMatchKey()
    {
        return matchKey;
    }

    public void setMatchKey(String matchKey)
    {
        this.matchKey = matchKey;
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
