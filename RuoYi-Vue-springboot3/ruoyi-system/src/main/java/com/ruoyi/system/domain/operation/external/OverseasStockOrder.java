package com.ruoyi.system.domain.operation.external;

import java.io.Serializable;
import java.util.Date;

/** 领星备货单号 */
public class OverseasStockOrder implements Serializable
{
    private static final long serialVersionUID = 1L;

    private Long id;
    private String overseasOrderNo;
    private String inboundOrderNo;
    private Date createTime;

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public String getOverseasOrderNo() { return overseasOrderNo; }
    public void setOverseasOrderNo(String overseasOrderNo) { this.overseasOrderNo = overseasOrderNo; }
    public String getInboundOrderNo() { return inboundOrderNo; }
    public void setInboundOrderNo(String inboundOrderNo) { this.inboundOrderNo = inboundOrderNo; }
    public Date getCreateTime() { return createTime; }
    public void setCreateTime(Date createTime) { this.createTime = createTime; }
}
