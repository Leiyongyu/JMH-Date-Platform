package com.ruoyi.system.domain.sop;

import com.ruoyi.common.core.domain.BaseEntity;

/** ERP用户的紫鸟主图上传非敏感配置（不含密码）。 */
public class AmazonImageUploadUserConfig extends BaseEntity
{
    private static final long serialVersionUID = 1L;

    private Long userId;
    private String companyName;
    private String accountName;
    private String clientPath;

    public Long getUserId()
    {
        return userId;
    }

    public void setUserId(Long userId)
    {
        this.userId = userId;
    }

    public String getCompanyName()
    {
        return companyName;
    }

    public void setCompanyName(String companyName)
    {
        this.companyName = companyName;
    }

    public String getAccountName()
    {
        return accountName;
    }

    public void setAccountName(String accountName)
    {
        this.accountName = accountName;
    }

    public String getClientPath()
    {
        return clientPath;
    }

    public void setClientPath(String clientPath)
    {
        this.clientPath = clientPath;
    }
}
