package com.ruoyi.system.domain.operation.ebay;

import java.util.ArrayList;
import java.util.List;

/** 单个 OE 的人工审核提交参数。 */
public class EbayPriceAuditReviewRequest
{
    private List<Long> selectedItemIds = new ArrayList<>();
    private String decision = "REVIEWED";

    public List<Long> getSelectedItemIds() { return selectedItemIds; }
    public void setSelectedItemIds(List<Long> selectedItemIds)
    {
        this.selectedItemIds = selectedItemIds == null ? new ArrayList<>() : selectedItemIds;
    }
    public String getDecision() { return decision; }
    public void setDecision(String decision) { this.decision = decision; }
}
