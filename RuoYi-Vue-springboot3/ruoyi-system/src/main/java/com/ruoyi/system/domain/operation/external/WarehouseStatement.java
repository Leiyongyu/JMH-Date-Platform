package com.ruoyi.system.domain.operation.external;

import java.io.Serializable;
import java.util.Date;

/** 仓库库存流水 (领星) — 精简字段 */
public class WarehouseStatement implements Serializable
{
    private static final long serialVersionUID = 1L;
    private Long id;
    private Integer wid;
    private String wareHouseName;
    private String sku;
    private Date optTime;
    private Integer type;

    public Long getId() { return id; }
    public void setId(Long v) { this.id = v; }
    public Integer getWid() { return wid; }
    public void setWid(Integer v) { this.wid = v; }
    public String getWareHouseName() { return wareHouseName; }
    public void setWareHouseName(String v) { this.wareHouseName = v; }
    public String getSku() { return sku; }
    public void setSku(String v) { this.sku = v; }
    public Date getOptTime() { return optTime; }
    public void setOptTime(Date v) { this.optTime = v; }
    public Integer getType() { return type; }
    public void setType(Integer v) { this.type = v; }
}
