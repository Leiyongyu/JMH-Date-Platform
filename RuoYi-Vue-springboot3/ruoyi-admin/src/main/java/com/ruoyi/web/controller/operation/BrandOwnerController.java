package com.ruoyi.web.controller.operation;

import java.util.List;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import com.ruoyi.common.core.controller.BaseController;
import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.common.core.page.TableDataInfo;
import com.ruoyi.system.domain.operation.external.BrandOwner;
import com.ruoyi.system.mapper.operation.external.BrandOwnerMapper;
import io.swagger.v3.oas.annotations.tags.Tag;

@Tag(name = "品牌负责人")
@RestController
@RequestMapping("/operations/brand-owner")
public class BrandOwnerController extends BaseController
{
    @Autowired
    private BrandOwnerMapper brandOwnerMapper;

    @PreAuthorize("@ss.hasPermi('operations:brandOwner:list')")
    @GetMapping("/list")
    public TableDataInfo list()
    {
        startPage();
        List<BrandOwner> list = brandOwnerMapper.selectAll();
        return getDataTable(list);
    }

    @PreAuthorize("@ss.hasPermi('operations:brandOwner:add')")
    @PostMapping
    public AjaxResult save(@RequestBody BrandOwner entity)
    {
        if (entity.getId() != null)
            return error("新增品牌负责人时 ID 必须为空");
        brandOwnerMapper.insert(entity);
        return success();
    }

    @PreAuthorize("@ss.hasPermi('operations:brandOwner:edit')")
    @PutMapping
    public AjaxResult update(@RequestBody BrandOwner entity)
    {
        if (entity.getId() == null)
            return error("ID不能为空");
        brandOwnerMapper.update(entity);
        return success();
    }

    @PreAuthorize("@ss.hasPermi('operations:brandOwner:remove')")
    @DeleteMapping("/{id}")
    public AjaxResult delete(@PathVariable Integer id)
    {
        brandOwnerMapper.deleteById(id);
        return success();
    }
}
