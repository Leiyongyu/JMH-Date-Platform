package com.ruoyi.web.controller.operation;

import java.util.List;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.system.mapper.operation.external.AmzFbaShipmentMapper;

import com.ruoyi.common.core.controller.BaseController;
import com.ruoyi.common.core.page.TableDataInfo;
import com.ruoyi.system.domain.operation.EbayReplenishmentSearchRequest;
import com.ruoyi.system.domain.operation.external.AmzFbaShipment;
import com.ruoyi.system.service.operation.IAmzFbaShipmentService;
import com.github.pagehelper.PageHelper;
import io.swagger.v3.oas.annotations.tags.Tag;

@Tag(name = "AMZ FBA货件")
@RestController
@RequestMapping("/operations/amz/fba-shipment")
public class AmzFbaShipmentController extends BaseController
{
    @Autowired
    private IAmzFbaShipmentService fbaShipmentService;

    @Autowired
    private AmzFbaShipmentMapper fbaShipmentMapper;

    @PreAuthorize("@ss.hasPermi('operations:amzReplenishment:list')")
    @GetMapping("/store-names")
    public AjaxResult storeNames()
    {
        return AjaxResult.success(fbaShipmentMapper.selectDistinctStoreNames());
    }

    @PreAuthorize("@ss.hasPermi('operations:amzReplenishment:list')")
    @PostMapping("/search")
    public TableDataInfo search(@RequestBody EbayReplenishmentSearchRequest req)
    {
        PageHelper.startPage(req.getPageNum() != null ? req.getPageNum() : 1,
                             req.getPageSize() != null ? req.getPageSize() : 20,
                             false);
        List<AmzFbaShipment> list = fbaShipmentService.search(req);
        TableDataInfo rspData = new TableDataInfo();
        rspData.setCode(com.ruoyi.common.constant.HttpStatus.SUCCESS);
        rspData.setMsg("查询成功");
        rspData.setRows(list);
        rspData.setTotal(fbaShipmentService.count(req));
        return rspData;
    }
}
