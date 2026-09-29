package com.ruoyi.system.domain.operation.ebay;

import java.math.BigDecimal;

/** 独立参数值，键名与参数目录一致，数值保持十进制定点精度。 */
public class EbayReplenishmentV2Parameter
{
    private String parameterKey;
    private BigDecimal numericValue;
    private String textValue;
    private long revision;

    public String getParameterKey() { return parameterKey; }
    public void setParameterKey(String value) { parameterKey = value; }
    public BigDecimal getNumericValue() { return numericValue; }
    public void setNumericValue(BigDecimal value) { numericValue = value; }
    public String getTextValue() { return textValue; }
    public void setTextValue(String value) { textValue = value; }
    public long getRevision() { return revision; }
    public void setRevision(long value) { revision = value; }
}
