package com.ruoyi.system.domain.operation.customs;

import java.io.Serializable;
import java.util.ArrayList;
import java.util.List;

public class CustomsDeclarationRequest implements Serializable
{
    private static final long serialVersionUID = 1L;

    private CustomsDeclarationHeader header = new CustomsDeclarationHeader();
    private List<CustomsDeclarationItem> items = new ArrayList<>();

    public CustomsDeclarationHeader getHeader() { return header; }
    public void setHeader(CustomsDeclarationHeader header) { this.header = header; }
    public List<CustomsDeclarationItem> getItems() { return items; }
    public void setItems(List<CustomsDeclarationItem> items) { this.items = items; }
}
