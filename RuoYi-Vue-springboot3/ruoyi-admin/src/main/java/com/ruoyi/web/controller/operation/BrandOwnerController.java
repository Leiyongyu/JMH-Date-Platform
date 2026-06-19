package com.ruoyi.web.controller.operation;

import java.util.List;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.*;

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

    @GetMapping("/list")
    public TableDataInfo list()
    {
        startPage();
        List<BrandOwner> list = brandOwnerMapper.selectAll();
        return getDataTable(list);
    }

    @PostMapping
    public AjaxResult save(@RequestBody BrandOwner entity)
    {
        if (entity.getId() != null)
            return success();
        brandOwnerMapper.insert(entity);
        return success();
    }

    @PutMapping
    public AjaxResult update(@RequestBody BrandOwner entity)
    {
        if (entity.getId() == null)
            return error("ID不能为空");
        brandOwnerMapper.update(entity);
        return success();
    }

    @DeleteMapping("/{id}")
    public AjaxResult delete(@PathVariable Integer id)
    {
        brandOwnerMapper.deleteById(id);
        return success();
    }
}
