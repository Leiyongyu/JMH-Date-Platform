package com.ruoyi.system.domain.operation.external;

import java.io.Serializable;

/**
 * 谷仓仓库信息(物理仓级别)
 */
public class GoodcangWarehouse implements Serializable
{
    private static final long serialVersionUID = 1L;

    private Long id;
    private String warehouseCode;
    private Integer wid;
    private String warehouseName;
    private String countryCode;
    private String wpCode;
    private String wpName;
    private String state;
    private String city;
    private String postcode;
    private String contacter;
    private String phone;
    private String streetAddress1;
    private String streetAddress2;
    private String streetNumber;

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public String getWarehouseCode() { return warehouseCode; }
    public void setWarehouseCode(String warehouseCode) { this.warehouseCode = warehouseCode; }
    public Integer getWid() { return wid; }
    public void setWid(Integer wid) { this.wid = wid; }
    public String getWarehouseName() { return warehouseName; }
    public void setWarehouseName(String warehouseName) { this.warehouseName = warehouseName; }
    public String getCountryCode() { return countryCode; }
    public void setCountryCode(String countryCode) { this.countryCode = countryCode; }
    public String getWpCode() { return wpCode; }
    public void setWpCode(String wpCode) { this.wpCode = wpCode; }
    public String getWpName() { return wpName; }
    public void setWpName(String wpName) { this.wpName = wpName; }
    public String getState() { return state; }
    public void setState(String state) { this.state = state; }
    public String getCity() { return city; }
    public void setCity(String city) { this.city = city; }
    public String getPostcode() { return postcode; }
    public void setPostcode(String postcode) { this.postcode = postcode; }
    public String getContacter() { return contacter; }
    public void setContacter(String contacter) { this.contacter = contacter; }
    public String getPhone() { return phone; }
    public void setPhone(String phone) { this.phone = phone; }
    public String getStreetAddress1() { return streetAddress1; }
    public void setStreetAddress1(String streetAddress1) { this.streetAddress1 = streetAddress1; }
    public String getStreetAddress2() { return streetAddress2; }
    public void setStreetAddress2(String streetAddress2) { this.streetAddress2 = streetAddress2; }
    public String getStreetNumber() { return streetNumber; }
    public void setStreetNumber(String streetNumber) { this.streetNumber = streetNumber; }
}
