package com.ruoyi.system.domain.operation.external;

import java.io.Serializable;

/**
 * 仓库表 (领星)
 */
public class Warehouse implements Serializable
{
    private static final long serialVersionUID = 1L;

    private Long id;
    private Integer wid;
    private String name;
    private Integer type;
    private Integer subType;
    private Integer isDelete;
    private String countryCode;
    private Integer wpId;
    private String wpName;
    private String tWarehouseName;
    private String tWarehouseCode;
    private String tCountryAreaName;
    private Integer tStatus;

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public Integer getWid() { return wid; }
    public void setWid(Integer wid) { this.wid = wid; }
    public String getName() { return name; }
    public void setName(String name) { this.name = name; }
    public Integer getType() { return type; }
    public void setType(Integer type) { this.type = type; }
    public Integer getSubType() { return subType; }
    public void setSubType(Integer subType) { this.subType = subType; }
    public Integer getIsDelete() { return isDelete; }
    public void setIsDelete(Integer isDelete) { this.isDelete = isDelete; }
    public String getCountryCode() { return countryCode; }
    public void setCountryCode(String countryCode) { this.countryCode = countryCode; }
    public Integer getWpId() { return wpId; }
    public void setWpId(Integer wpId) { this.wpId = wpId; }
    public String getWpName() { return wpName; }
    public void setWpName(String wpName) { this.wpName = wpName; }
    public String gettWarehouseName() { return tWarehouseName; }
    public void settWarehouseName(String tWarehouseName) { this.tWarehouseName = tWarehouseName; }
    public String gettWarehouseCode() { return tWarehouseCode; }
    public void settWarehouseCode(String tWarehouseCode) { this.tWarehouseCode = tWarehouseCode; }
    public String gettCountryAreaName() { return tCountryAreaName; }
    public void settCountryAreaName(String tCountryAreaName) { this.tCountryAreaName = tCountryAreaName; }
    public Integer gettStatus() { return tStatus; }
    public void settStatus(Integer tStatus) { this.tStatus = tStatus; }
}
