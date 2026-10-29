package com.ruoyi.system.service.operation.scope;

import java.util.List;

/** Server-resolved business owners. Empty is deny-all; never a client filter. */
public final class BusinessDataScope
{
    private final boolean all;
    private final List<String> owners;

    public BusinessDataScope(boolean all, List<String> owners)
    {
        this.all = all;
        this.owners = List.copyOf(owners);
    }

    public boolean isAll() { return all; }
    public List<String> getOwners() { return owners; }
    public boolean allows(String owner) { return all || owner != null && owners.contains(owner.trim()); }
}
