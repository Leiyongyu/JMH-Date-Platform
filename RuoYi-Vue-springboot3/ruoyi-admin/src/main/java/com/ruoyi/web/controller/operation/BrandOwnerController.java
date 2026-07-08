package com.ruoyi.web.controller.operation;

import java.util.List;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.util.StringUtils;
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
    public TableDataInfo list(BrandOwner query)
    {
        startPage();
        normalize(query);
        List<BrandOwner> list = brandOwnerMapper.selectList(query);
        return getDataTable(list);
    }

    @PreAuthorize("@ss.hasPermi('operations:brandOwner:add')")
    @PostMapping
    public AjaxResult save(@RequestBody BrandOwner entity)
    {
        if (entity.getId() != null)
            return error("新增品牌负责人时 ID 必须为空");
        normalize(entity);
        AjaxResult validation = validate(entity, null);
        if (validation != null)
            return validation;
        brandOwnerMapper.insert(entity);
        return success();
    }

    @PreAuthorize("@ss.hasPermi('operations:brandOwner:edit')")
    @PutMapping
    public AjaxResult update(@RequestBody BrandOwner entity)
    {
        if (entity.getId() == null)
            return error("ID不能为空");
        normalize(entity);
        AjaxResult validation = validate(entity, entity.getId());
        if (validation != null)
            return validation;
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

    private AjaxResult validate(BrandOwner entity, Integer excludeId)
    {
        if (!StringUtils.hasText(entity.getBrandCode()))
            return error("品牌代码不能为空");
        if (!StringUtils.hasText(entity.getOwnerName()))
            return error("负责人不能为空");
        if (brandOwnerMapper.countByBrandCode(entity.getBrandCode(), excludeId) > 0)
            return error("品牌代码已存在");
        return null;
    }

    private void normalize(BrandOwner entity)
    {
        if (entity == null)
            return;
        entity.setBrandCode(trimUpper(entity.getBrandCode()));
        entity.setOwnerName(trim(entity.getOwnerName()));
    }

    private String trimUpper(String value)
    {
        String text = trim(value);
        return text == null ? null : text.toUpperCase();
    }

    private String trim(String value)
    {
        return StringUtils.hasText(value) ? value.trim() : null;
    }
}
