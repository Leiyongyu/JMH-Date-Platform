package com.ruoyi.system.domain.operation.external;

import java.io.Serializable;

public class AmzProductCategory implements Serializable
{
    private static final long serialVersionUID = 1L;
    private Long id;
    private Integer sid;
    private String sellerSku;
    private String category;

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public Integer getSid() { return sid; }
    public void setSid(Integer sid) { this.sid = sid; }
    public String getSellerSku() { return sellerSku; }
    public void setSellerSku(String sellerSku) { this.sellerSku = sellerSku; }
    public String getCategory() { return category; }
    public void setCategory(String category) { this.category = category; }
}
