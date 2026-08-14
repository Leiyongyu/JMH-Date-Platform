package com.ruoyi.system.service.operation.ebay;

import java.io.InputStream;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ConcurrentHashMap;
import org.apache.poi.ss.usermodel.Cell;
import org.apache.poi.ss.usermodel.DataFormatter;
import org.apache.poi.ss.usermodel.FormulaEvaluator;
import org.apache.poi.ss.usermodel.Row;
import org.apache.poi.ss.usermodel.Sheet;
import org.apache.poi.ss.usermodel.Workbook;
import org.apache.poi.ss.usermodel.WorkbookFactory;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import org.springframework.web.multipart.MultipartFile;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.ruoyi.common.exception.ServiceException;
import com.ruoyi.system.domain.operation.ebay.EbayItemDetail;
import com.ruoyi.system.domain.operation.ebay.EbayPriceAuditItem;
import com.ruoyi.system.domain.operation.ebay.EbayPriceAuditOe;
import com.ruoyi.system.domain.operation.ebay.EbayPriceAuditReviewRequest;
import com.ruoyi.system.domain.operation.ebay.EbayPriceAuditTask;
import com.ruoyi.system.domain.operation.ebay.EbayPriceSearchRequest;
import com.ruoyi.system.mapper.operation.EbayPriceAuditMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/** eBay Excel 批量查询、持久化和逐 OE 人工审核服务。 */
@Service
public class EbayPriceAuditService
{
    private static final Logger LOG = LoggerFactory.getLogger(EbayPriceAuditService.class);
    private static final Set<String> SUPPORTED_SITES = Set.of("de", "uk", "us");
    private static final Set<String> SKU_HEADERS = Set.of("sku", "skuno", "sku号", "sku编号");
    private static final Set<String> OE_HEADERS = Set.of("oe", "oe号", "oe号码", "oenumber");
    private static final DateTimeFormatter TASK_TIME = DateTimeFormatter.ofPattern("yyyyMMdd-HHmmss");
    private static final TypeReference<List<String>> STRING_LIST = new TypeReference<>() {};

    private final EbayPriceAuditMapper mapper;
    private final EbayPriceService priceService;
    private final EbayProperties properties;
    private final ObjectMapper objectMapper;
    private final ThreadPoolTaskExecutor searchExecutor;
    private final ThreadPoolTaskExecutor auditExecutor;
    private final Set<Long> runningTaskIds = ConcurrentHashMap.newKeySet();

    public EbayPriceAuditService(EbayPriceAuditMapper mapper,
            EbayPriceService priceService, EbayProperties properties, ObjectMapper objectMapper,
            @Qualifier("ebaySearchExecutor") ThreadPoolTaskExecutor searchExecutor,
            @Qualifier("ebayAuditExecutor") ThreadPoolTaskExecutor auditExecutor)
    {
        this.mapper = mapper;
        this.priceService = priceService;
        this.properties = properties;
        this.objectMapper = objectMapper;
        this.searchExecutor = searchExecutor;
        this.auditExecutor = auditExecutor;
    }

    /** Java 重启后自动接续未完成的批量查询；未执行建表脚本时不阻断系统启动。 */
    @EventListener(ApplicationReadyEvent.class)
    public void resumeInterruptedTasks()
    {
        try
        {
            for (EbayPriceAuditTask task : mapper.selectQueryingTasks())
            {
                submitTask(task.getId(), task.getSite());
            }
        }
        catch (Exception e)
        {
            LOG.warn("eBay审核任务恢复检查跳过，请确认审核表建表脚本已执行: {}", e.getMessage());
        }
    }

    @Transactional(rollbackFor = Exception.class)
    public synchronized Map<String, Object> createTask(MultipartFile file, String site,
            Long userId, String username)
    {
        String normalizedSite = normalizeSite(site);
        ParsedOeFile parsed = parse(file);
        int maxInputs = Math.max(1, properties.getAuditMaxOes());
        int effectiveRows = parsed.totalRows() - parsed.blankRows();
        if (effectiveRows > maxInputs)
        {
            throw new ServiceException("单个文件最多允许 " + maxInputs + " 个非空SKU或OE输入，"
                    + "本次读取到 " + effectiveRows + " 行，请拆分文件后重试");
        }
        String sourceFileName = safeFileName(file.getOriginalFilename());
        return persistTask(parsed.oes(), parsed.totalRows(), parsed.duplicateOe(),
                parsed.blankRows(), sourceFileName, normalizedSite, userId, username);
    }

    @Transactional(rollbackFor = Exception.class)
    public synchronized Map<String, Object> createManualTask(EbayPriceSearchRequest request,
            Long userId, String username)
    {
        if (request == null)
        {
            throw new ServiceException("手工查询参数不能为空");
        }
        String normalizedSite = normalizeSite(request.getSite());
        String inputType = request.getInputType() == null
                ? "" : request.getInputType().trim().toLowerCase(Locale.ROOT);
        if (!Set.of("sku", "oe").contains(inputType))
        {
            throw new ServiceException("请选择手工输入类型：SKU 或 OE号");
        }
        List<String> inputs = EbayPriceService.normalizeKeywords(request.getKeywords());
        if (inputs.isEmpty())
        {
            throw new ServiceException("请输入至少一个SKU或OE号，多个值使用分号、逗号或换行分隔");
        }
        int maxOes = Math.max(1, properties.getAuditMaxOes());
        if (inputs.size() > maxOes)
        {
            throw new ServiceException("单个任务最多允许 " + maxOes + " 个不同的SKU或OE号，本次输入 "
                    + inputs.size() + " 个，请拆分后重试");
        }

        List<String> oes = new ArrayList<>();
        if ("oe".equals(inputType))
        {
            for (String oe : inputs)
            {
                validateOe(oe, "手工输入");
                oes.add(oe);
            }
        }
        else
        {
            for (String sku : inputs)
            {
                if (sku.length() > 255)
                {
                    throw new ServiceException("SKU超过255个字符：" + sku);
                }
            }
            Map<String, String> randomOeBySku = priceService.loadRandomOeBySku(inputs);
            List<String> missing = new ArrayList<>();
            for (String sku : inputs)
            {
                String oe = randomOeBySku.get(normalizedKey(sku));
                if (oe == null || oe.isBlank())
                {
                    missing.add(sku);
                }
                else
                {
                    validateOe(oe, "SKU“" + sku + "”映射");
                    oes.add(oe);
                }
            }
            if (!missing.isEmpty())
            {
                String preview = String.join("、", missing.subList(0, Math.min(10, missing.size())));
                String suffix = missing.size() > 10 ? "等共" + missing.size() + "个" : "";
                throw new ServiceException("以下SKU未在SKU-OE映射表中找到对应OE：" + preview + suffix
                        + "。请先导入SKU-OE对照表，或改为选择OE号后直接输入");
            }
        }

        List<String> uniqueOes = uniqueOes(oes);
        return persistTask(uniqueOes, inputs.size(), inputs.size() - uniqueOes.size(), 0,
                "手工输入-" + inputType.toUpperCase(Locale.ROOT), normalizedSite, userId, username);
    }

    private Map<String, Object> persistTask(List<String> oes, int totalRows,
            int duplicateOe, int blankRows, String sourceFileName,
            String normalizedSite, Long userId, String username)
    {
        int maxOes = Math.max(1, properties.getAuditMaxOes());
        if (oes.size() > maxOes)
        {
            throw new ServiceException("单个任务最多允许 " + maxOes + " 个不同的查询OE，本次解析到 "
                    + oes.size() + " 个，请拆分后重试");
        }
        int maxTasks = Math.max(1, properties.getAuditMaxConcurrentTasks());
        if (mapper.countQueryingTasks() >= maxTasks)
        {
            throw new ServiceException("当前已有 " + maxTasks + " 个批量查询任务在运行，请稍后再上传");
        }

        EbayPriceAuditTask task = new EbayPriceAuditTask();
        task.setTaskName(stripExtension(sourceFileName) + "-" + LocalDateTime.now().format(TASK_TIME));
        task.setSourceFileName(sourceFileName);
        task.setSite(normalizedSite);
        task.setStatus("QUERYING");
        task.setTotalRows(totalRows);
        task.setTotalOe(oes.size());
        task.setDuplicateOe(duplicateOe);
        task.setBlankRows(blankRows);
        task.setUserId(userId);
        task.setCreateBy(username);
        mapper.insertTask(task);

        List<EbayPriceAuditOe> rows = new ArrayList<>();
        for (int index = 0; index < oes.size(); index++)
        {
            EbayPriceAuditOe row = new EbayPriceAuditOe();
            row.setTaskId(task.getId());
            row.setSortNo(index + 1);
            row.setOe(oes.get(index));
            rows.add(row);
        }
        mapper.batchInsertOes(rows);
        submitAfterCommit(task.getId(), normalizedSite);
        return taskView(task.getId(), userId, false);
    }

    public Map<String, Object> latestTask(Long userId)
    {
        EbayPriceAuditTask task = mapper.selectLatestTask(userId);
        return task == null ? null : taskView(task.getId(), userId, true);
    }

    public List<EbayPriceAuditTask> recentTasks(Long userId)
    {
        return mapper.selectRecentTasks(userId);
    }

    @Transactional(rollbackFor = Exception.class)
    public void deleteTask(Long taskId, Long userId)
    {
        EbayPriceAuditTask task = requireTask(taskId, userId);
        if ("QUERYING".equals(task.getStatus()) || runningTaskIds.contains(taskId))
        {
            throw new ServiceException("该批次仍在后台查询中，完成查询后才能删除");
        }
        mapper.deleteItemsByTask(taskId);
        mapper.deleteOesByTask(taskId);
        if (mapper.deleteTask(taskId, userId) != 1)
        {
            throw new ServiceException("历史任务删除失败，请刷新后重试");
        }
    }

    public Map<String, Object> taskView(Long taskId, Long userId)
    {
        return taskView(taskId, userId, true);
    }

    public Map<String, Object> oeView(Long taskId, Long oeId, Long userId)
    {
        requireTask(taskId, userId);
        EbayPriceAuditOe oe = requireOe(taskId, oeId);
        List<EbayPriceAuditItem> items = mapper.selectItems(taskId, oeId);
        hydrateImages(items);
        LinkedHashMap<String, Object> result = new LinkedHashMap<>();
        result.put("oe", oe);
        result.put("items", items);
        return result;
    }

    @Transactional(rollbackFor = Exception.class)
    public Map<String, Object> review(Long taskId, Long oeId,
            EbayPriceAuditReviewRequest request, Long userId, String username)
    {
        requireTask(taskId, userId);
        EbayPriceAuditOe oe = requireOe(taskId, oeId);
        String decision = request == null || request.getDecision() == null
                ? "REVIEWED" : request.getDecision().trim().toUpperCase(Locale.ROOT);
        if (!Set.of("REVIEWED", "SKIPPED").contains(decision))
        {
            throw new ServiceException("审核决定仅支持 REVIEWED 或 SKIPPED");
        }
        if ("PENDING".equals(oe.getQueryStatus()) || "QUERYING".equals(oe.getQueryStatus()))
        {
            throw new ServiceException("该OE仍在查询中，请等待查询完成后再审核");
        }
        if ("FAILED".equals(oe.getQueryStatus()) && !"SKIPPED".equals(decision))
        {
            throw new ServiceException("该OE查询失败，请先重试，或选择“跳过并继续”");
        }

        LinkedHashSet<Long> selectedIds = new LinkedHashSet<>();
        if (request != null && "REVIEWED".equals(decision))
        {
            for (Long id : request.getSelectedItemIds())
            {
                if (id != null && id > 0)
                {
                    selectedIds.add(id);
                }
            }
        }
        mapper.clearSelectedItems(oeId);
        int updated = selectedIds.isEmpty() ? 0
                : mapper.selectReviewedItems(oeId, new ArrayList<>(selectedIds));
        if (updated != selectedIds.size())
        {
            throw new ServiceException("选中的商品包含不属于当前OE的数据，请刷新页面后重新审核");
        }
        mapper.markOeReviewed(oeId, decision, updated, username);
        mapper.refreshTaskStats(taskId);
        return taskView(taskId, userId, false);
    }

    @Transactional(rollbackFor = Exception.class)
    public Map<String, Object> retry(Long taskId, Long oeId, Long userId)
    {
        EbayPriceAuditTask task = requireTask(taskId, userId);
        EbayPriceAuditOe oe = requireOe(taskId, oeId);
        if (!Set.of("FAILED", "EMPTY").contains(oe.getQueryStatus()))
        {
            throw new ServiceException("只有查询失败或无结果的OE可以重试");
        }
        mapper.markOeQuerying(oeId);
        mapper.deleteItemsByOe(oeId);
        mapper.refreshTaskStats(taskId);
        submitRetryAfterCommit(taskId, oe, task.getSite());
        return taskView(taskId, userId, false);
    }

    public List<EbayItemDetail> selectedItemsForExport(Long taskId, Long userId)
    {
        EbayPriceAuditTask task = requireTask(taskId, userId);
        if (!"COMPLETED".equals(task.getStatus()))
        {
            throw new ServiceException("请先完成全部OE审核；失败项可以重试或选择跳过");
        }
        List<EbayPriceAuditItem> items = mapper.selectSelectedItems(taskId);
        hydrateImages(items);
        if (items.isEmpty())
        {
            throw new ServiceException("本批次没有选中任何商品，无法导出");
        }
        return new ArrayList<>(items);
    }

    private Map<String, Object> taskView(Long taskId, Long userId, boolean resumeIfNeeded)
    {
        EbayPriceAuditTask task = requireTask(taskId, userId);
        if (resumeIfNeeded && "QUERYING".equals(task.getStatus()) && !runningTaskIds.contains(taskId))
        {
            submitTask(taskId, task.getSite());
        }
        List<EbayPriceAuditOe> oes = mapper.selectOes(taskId);
        LinkedHashMap<String, Object> result = new LinkedHashMap<>();
        result.put("task", task);
        result.put("oes", oes);
        return result;
    }

    private EbayPriceAuditTask requireTask(Long taskId, Long userId)
    {
        if (taskId == null || userId == null)
        {
            throw new ServiceException("审核任务参数不完整");
        }
        EbayPriceAuditTask task = mapper.selectTask(taskId, userId);
        if (task == null)
        {
            throw new ServiceException("审核任务不存在，或不属于当前用户");
        }
        return task;
    }

    private EbayPriceAuditOe requireOe(Long taskId, Long oeId)
    {
        EbayPriceAuditOe oe = mapper.selectOe(taskId, oeId);
        if (oe == null)
        {
            throw new ServiceException("未找到当前任务中的OE明细");
        }
        return oe;
    }

    private void submitAfterCommit(Long taskId, String site)
    {
        if (TransactionSynchronizationManager.isSynchronizationActive())
        {
            TransactionSynchronizationManager.registerSynchronization(new TransactionSynchronization()
            {
                @Override
                public void afterCommit()
                {
                    submitTask(taskId, site);
                }
            });
        }
        else
        {
            submitTask(taskId, site);
        }
    }

    private void submitRetryAfterCommit(Long taskId, EbayPriceAuditOe oe, String site)
    {
        Runnable query = () -> auditExecutor.execute(() -> executeQuery(taskId, oe, site));
        if (TransactionSynchronizationManager.isSynchronizationActive())
        {
            TransactionSynchronizationManager.registerSynchronization(new TransactionSynchronization()
            {
                @Override
                public void afterCommit()
                {
                    query.run();
                }
            });
        }
        else
        {
            query.run();
        }
    }

    private void submitTask(Long taskId, String site)
    {
        if (!runningTaskIds.add(taskId))
        {
            return;
        }
        auditExecutor.execute(() -> {
            try
            {
                List<EbayPriceAuditOe> pending = mapper.selectOes(taskId).stream()
                        .filter(row -> Set.of("PENDING", "QUERYING").contains(row.getQueryStatus()))
                        .toList();
                List<CompletableFuture<Void>> futures = new ArrayList<>();
                for (EbayPriceAuditOe oe : pending)
                {
                    futures.add(CompletableFuture.runAsync(() -> queryOe(taskId, oe, site), searchExecutor));
                }
                CompletableFuture.allOf(futures.toArray(CompletableFuture[]::new)).join();
                mapper.refreshTaskStats(taskId);
            }
            finally
            {
                runningTaskIds.remove(taskId);
            }
        });
    }

    private void queryOe(Long taskId, EbayPriceAuditOe oe, String site)
    {
        mapper.markOeQuerying(oe.getId());
        mapper.deleteItemsByOe(oe.getId());
        executeQuery(taskId, oe, site);
    }

    private void executeQuery(Long taskId, EbayPriceAuditOe oe, String site)
    {
        try
        {
            List<EbayItemDetail> candidates = priceService.searchLowestItems(oe.getOe(), site);
            List<EbayPriceAuditItem> rows = new ArrayList<>();
            for (int index = 0; index < candidates.size(); index++)
            {
                rows.add(toAuditItem(taskId, oe, index + 1, candidates.get(index)));
            }
            if (!rows.isEmpty())
            {
                mapper.batchInsertItems(rows);
            }
            String queryStatus = rows.isEmpty() ? "EMPTY" : "SUCCESS";
            String reviewStatus = rows.isEmpty() ? "NOT_REQUIRED" : "PENDING";
            mapper.markOeFinished(oe.getId(), queryStatus, reviewStatus, rows.size(), null);
        }
        catch (Exception e)
        {
            mapper.deleteItemsByOe(oe.getId());
            mapper.markOeFinished(oe.getId(), "FAILED", "PENDING", 0, friendlyError(e));
        }
        finally
        {
            mapper.refreshTaskStats(taskId);
        }
    }

    private EbayPriceAuditItem toAuditItem(Long taskId, EbayPriceAuditOe oe,
            int rank, EbayItemDetail source)
    {
        EbayPriceAuditItem target = new EbayPriceAuditItem();
        target.setTaskId(taskId);
        target.setAuditOeId(oe.getId());
        target.setRankNo(rank);
        target.setOe(oe.getOe());
        target.setItemId(source.getItemId());
        target.setProductId(source.getProductId());
        target.setTitle(source.getTitle());
        target.setPrice(source.getPrice());
        target.setPf(source.getPf());
        target.setCurrency(source.getCurrency());
        target.setEstimatedSoldQuantity(source.getEstimatedSoldQuantity());
        target.setCondition(source.getCondition());
        target.setConditionId(source.getConditionId());
        target.setImages(source.getImages());
        target.setImageUrlsJson(writeImages(source.getImages()));
        target.setLink(source.getLink());
        target.setSeller(source.getSeller());
        target.setSellerFeedback(source.getSellerFeedback());
        target.setShipping(source.getShipping());
        target.setImageDetailComplete(source.isImageDetailComplete());
        target.setImageDetailError(source.getImageDetailError());
        return target;
    }

    private void hydrateImages(List<EbayPriceAuditItem> items)
    {
        for (EbayPriceAuditItem item : items)
        {
            try
            {
                String json = item.getImageUrlsJson();
                item.setImages(json == null || json.isBlank()
                        ? List.of() : objectMapper.readValue(json, STRING_LIST));
            }
            catch (Exception ignored)
            {
                item.setImages(List.of());
            }
        }
    }

    private String writeImages(List<String> images)
    {
        try
        {
            return objectMapper.writeValueAsString(images == null ? List.of() : images);
        }
        catch (Exception e)
        {
            return "[]";
        }
    }

    private ParsedOeFile parse(MultipartFile file)
    {
        checkFile(file);
        try (InputStream input = file.getInputStream(); Workbook workbook = WorkbookFactory.create(input))
        {
            if (workbook.getNumberOfSheets() == 0)
            {
                throw new ServiceException("Excel文件没有工作表");
            }
            Sheet sheet = workbook.getSheetAt(0);
            Row header = sheet.getRow(sheet.getFirstRowNum());
            if (header == null)
            {
                throw new ServiceException("Excel文件为空");
            }
            DataFormatter formatter = new DataFormatter(Locale.ROOT);
            FormulaEvaluator evaluator = workbook.getCreationHelper().createFormulaEvaluator();
            String headerA = normalizeHeader(cellText(header, 0, formatter, evaluator));
            String headerB = normalizeHeader(cellText(header, 1, formatter, evaluator));
            boolean oeOnlyLayout = OE_HEADERS.contains(headerA);
            boolean skuOeLayout = SKU_HEADERS.contains(headerA) && OE_HEADERS.contains(headerB);
            if (!oeOnlyLayout && !skuOeLayout)
            {
                throw new ServiceException("Excel表头不匹配：一列表应为A列“OE号”；两列表应为A列“SKU”、"
                        + "B列“OE号”。当前A列为“" + cellText(header, 0, formatter, evaluator)
                        + "”，B列为“" + cellText(header, 1, formatter, evaluator) + "”");
            }

            List<InputQueryRow> inputRows = new ArrayList<>();
            int totalRows = 0;
            int blankRows = 0;
            for (int rowIndex = header.getRowNum() + 1; rowIndex <= sheet.getLastRowNum(); rowIndex++)
            {
                totalRows++;
                Row row = sheet.getRow(rowIndex);
                String sku = skuOeLayout ? cellText(row, 0, formatter, evaluator).trim() : "";
                String oe = cellText(row, skuOeLayout ? 1 : 0, formatter, evaluator).trim();
                if (sku.isEmpty() && oe.isEmpty())
                {
                    blankRows++;
                    continue;
                }
                if (sku.length() > 255)
                {
                    throw new ServiceException("Excel第 " + (rowIndex + 1)
                            + " 行SKU超过255个字符，请检查单元格内容");
                }
                if (oe.length() > 128)
                {
                    throw new ServiceException("Excel第 " + (rowIndex + 1) + " 行OE号超过128个字符，请检查单元格内容");
                }
                inputRows.add(new InputQueryRow(rowIndex + 1, sku, oe));
            }
            if (inputRows.isEmpty())
            {
                throw new ServiceException(oeOnlyLayout
                        ? "Excel A列没有读取到有效的OE号"
                        : "Excel A、B列没有读取到有效的SKU或OE号");
            }

            LinkedHashSet<String> skuKeys = new LinkedHashSet<>();
            LinkedHashMap<String, String> skuValues = new LinkedHashMap<>();
            for (InputQueryRow row : inputRows)
            {
                if (!row.sku().isBlank())
                {
                    String key = normalizedKey(row.sku());
                    skuKeys.add(key);
                    skuValues.putIfAbsent(key, row.sku());
                }
            }
            Map<String, String> randomOeBySku = skuKeys.isEmpty()
                    ? Map.of()
                    : priceService.loadRandomOeBySku(skuKeys.stream().map(skuValues::get).toList());

            LinkedHashMap<String, String> unique = new LinkedHashMap<>();
            List<String> unresolvedRows = new ArrayList<>();
            int duplicateOe = 0;
            for (InputQueryRow row : inputRows)
            {
                String oe = row.oe();
                if (!row.sku().isBlank())
                {
                    String mappedOe = randomOeBySku.get(normalizedKey(row.sku()));
                    if (mappedOe != null && !mappedOe.isBlank())
                    {
                        oe = mappedOe;
                    }
                    else if (oe.isBlank())
                    {
                        unresolvedRows.add("第" + row.rowNumber() + "行SKU“" + row.sku() + "”");
                        continue;
                    }
                }
                if (oe.length() > 128)
                {
                    throw new ServiceException("SKU映射得到的OE号超过128个字符：" + oe);
                }
                if (unique.putIfAbsent(normalizedKey(oe), oe) != null)
                {
                    duplicateOe++;
                }
            }
            if (!unresolvedRows.isEmpty())
            {
                String preview = String.join("、", unresolvedRows.subList(0, Math.min(10, unresolvedRows.size())));
                String suffix = unresolvedRows.size() > 10 ? "等共" + unresolvedRows.size() + "行" : "";
                throw new ServiceException(preview + suffix
                        + "未在SKU-OE映射表中找到对应OE，且该行B列OE为空；请补充映射或填写OE号");
            }
            if (unique.isEmpty())
            {
                throw new ServiceException("Excel中没有可用于查询的有效OE号");
            }
            return new ParsedOeFile(new ArrayList<>(unique.values()), totalRows, blankRows, duplicateOe);
        }
        catch (ServiceException e)
        {
            throw e;
        }
        catch (Exception e)
        {
            throw new ServiceException("OE批量文件解析失败：" + friendlyError(e));
        }
    }

    private static void checkFile(MultipartFile file)
    {
        if (file == null || file.isEmpty())
        {
            throw new ServiceException("请选择包含OE号的Excel文件");
        }
        String name = file.getOriginalFilename() == null ? "" : file.getOriginalFilename().toLowerCase(Locale.ROOT);
        if (!name.endsWith(".xlsx") && !name.endsWith(".xlsm") && !name.endsWith(".xls"))
        {
            throw new ServiceException("仅支持 .xlsx、.xlsm 或 .xls 文件");
        }
    }

    private static String cellText(Row row, int column, DataFormatter formatter, FormulaEvaluator evaluator)
    {
        if (row == null)
        {
            return "";
        }
        Cell cell = row.getCell(column);
        return cell == null ? "" : formatter.formatCellValue(cell, evaluator).trim();
    }

    private static String normalizeHeader(String value)
    {
        return value == null ? "" : value.trim().toLowerCase(Locale.ROOT).replaceAll("[\\s_]", "");
    }

    private static String normalizedKey(String value)
    {
        return value == null ? "" : value.trim().toUpperCase(Locale.ROOT);
    }

    private static List<String> uniqueOes(List<String> values)
    {
        LinkedHashMap<String, String> unique = new LinkedHashMap<>();
        for (String value : values)
        {
            if (value != null && !value.isBlank())
            {
                unique.putIfAbsent(normalizedKey(value), value.trim());
            }
        }
        return new ArrayList<>(unique.values());
    }

    private static void validateOe(String oe, String source)
    {
        if (oe == null || oe.isBlank())
        {
            throw new ServiceException(source + "未提供有效OE号");
        }
        if (oe.length() > 128)
        {
            throw new ServiceException(source + "得到的OE号超过128个字符：" + oe);
        }
    }

    private static String normalizeSite(String site)
    {
        String value = site == null || site.isBlank() ? "de" : site.trim().toLowerCase(Locale.ROOT);
        if (!SUPPORTED_SITES.contains(value))
        {
            throw new ServiceException("站点仅支持德国、英国或美国");
        }
        return value;
    }

    private static String safeFileName(String value)
    {
        String name = value == null || value.isBlank() ? "OE批量查询.xlsx" : value.trim();
        return name.length() <= 255 ? name : name.substring(name.length() - 255);
    }

    private static String stripExtension(String fileName)
    {
        int index = fileName.lastIndexOf('.');
        return index > 0 ? fileName.substring(0, index) : fileName;
    }

    private static String friendlyError(Throwable error)
    {
        Throwable current = error;
        while (current.getCause() != null && current.getCause() != current)
        {
            current = current.getCause();
        }
        String message = current.getMessage();
        if (message == null || message.isBlank())
        {
            message = current.getClass().getSimpleName();
        }
        message = message.replaceAll("[\\r\\n]+", " ").trim();
        return message.length() <= 1000 ? message : message.substring(0, 1000);
    }

    private record ParsedOeFile(List<String> oes, int totalRows, int blankRows, int duplicateOe) {}

    private record InputQueryRow(int rowNumber, String sku, String oe) {}
}
