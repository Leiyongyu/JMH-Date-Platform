package com.ruoyi.system.service.operation.sync;

import com.ruoyi.system.domain.operation.TaskStatus;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.TimeUnit;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;

/**
 * Public API for async sync submission and status polling.
 * <p>
 * Actual async execution is delegated to {@link SyncTaskRunner} (a separate bean)
 * so that {@code @Async} works through the Spring AOP proxy.
 */
@Service
public class SyncTaskAsyncService
{
    private static final Logger LOG = LoggerFactory.getLogger(SyncTaskAsyncService.class);

    private final ConcurrentHashMap<String, SyncSubmission> submissions = new ConcurrentHashMap<>();
    private final SyncTaskRunner runner;

    public SyncTaskAsyncService(SyncTaskRunner runner)
    {
        this.runner = runner;
    }

    // ---- public API for Controller ----

    public String submitEbay(String triggerType, String operator, String scope)
    {
        String submissionId = UUID.randomUUID().toString().substring(0, 8);
        SyncSubmission sub = new SyncSubmission(submissionId, "ebay", scope, operator);
        submissions.put(submissionId, sub);
        // Delegate to separate bean — @Async works through Spring proxy
        runner.runEbay(sub, triggerType, operator, scope);
        return submissionId;
    }

    public String submitAmz(String triggerType, String operator, String scope)
    {
        String submissionId = UUID.randomUUID().toString().substring(0, 8);
        SyncSubmission sub = new SyncSubmission(submissionId, "amz", scope, operator);
        submissions.put(submissionId, sub);
        runner.runAmz(sub, triggerType, operator, scope);
        return submissionId;
    }

    public String submitStockOrder(String operator)
    {
        String submissionId = UUID.randomUUID().toString().substring(0, 8);
        SyncSubmission sub = new SyncSubmission(submissionId, "stock_order", "full", operator);
        submissions.put(submissionId, sub);
        runner.runStockOrder(sub, operator);
        return submissionId;
    }

    public SyncSubmission getSubmission(String submissionId)
    {
        return submissions.get(submissionId);
    }

    /** Evict completed submissions older than the given threshold. */
    public void evictCompleted(int maxAgeMinutes)
    {
        long cutoff = System.currentTimeMillis() - TimeUnit.MINUTES.toMillis(maxAgeMinutes);
        int before = submissions.size();
        submissions.entrySet().removeIf(e -> e.getValue().isTerminal() && e.getValue().createdAt < cutoff);
        int removed = before - submissions.size();
        if (removed > 0) LOG.info("Evicted {} completed sync submissions ({} remaining)", removed, submissions.size());
    }

    /** Auto-cleanup every 10 minutes. */
    @Scheduled(fixedRate = 600_000)
    public void scheduledEvict()
    {
        evictCompleted(60); // keep completed submissions for 60 minutes
    }

    // ---- inner class ----

    public static class SyncSubmission
    {
        public final String submissionId;
        public final String syncType;
        public final String scope;
        public final String operator;
        public final long createdAt = System.currentTimeMillis();

        volatile String status = TaskStatus.PENDING.getValue();
        volatile Long parentLogId;
        volatile String parentStatus;
        volatile int totalSteps;
        volatile int successSteps;
        volatile int failedSteps;
        volatile double elapsedSeconds;
        volatile String errorMessage;

        SyncSubmission(String submissionId, String syncType, String scope, String operator)
        {
            this.submissionId = submissionId;
            this.syncType = syncType;
            this.scope = scope;
            this.operator = operator;
        }

        void markRunning() { status = TaskStatus.RUNNING.getValue(); }

        @SuppressWarnings("unchecked")
        void completeFrom(Map<String, Object> result)
        {
            if (result == null) { markFailed("no result from sync"); return; }
            this.parentStatus = (String) result.get("parentStatus");
            Object logId = result.get("parentLogId");
            if (logId != null) this.parentLogId = ((Number) logId).longValue();
            Object ts = result.get("totalSteps");
            if (ts != null) this.totalSteps = ((Number) ts).intValue();
            Object ss = result.get("successSteps");
            if (ss != null) this.successSteps = ((Number) ss).intValue();
            Object fs = result.get("failedSteps");
            if (fs != null) this.failedSteps = ((Number) fs).intValue();
            Object el = result.get("elapsed");
            if (el != null && el instanceof String) {
                try { this.elapsedSeconds = Double.parseDouble(((String) el).replace("s", "")); }
                catch (NumberFormatException ignored) {}
            }
            // Map unified-service status → TaskStatus
            if ("BUSY".equals(parentStatus)) {
                // BUSY = Redis lock acquisition failed; no task was started. Treat as terminal FAILED.
                this.status = TaskStatus.FAILED.getValue();
                this.errorMessage = "同步任务未启动：已有同步任务正在执行中，未能获取锁";
            } else if ("PARTIAL_SUCCESS".equals(parentStatus)) {
                this.status = TaskStatus.PARTIAL.getValue();
            } else if (parentStatus != null) {
                this.status = parentStatus;
            } else {
                this.status = TaskStatus.SUCCESS.getValue();
            }
        }

        void markSuccess(String s) { status = s; }
        void markFailed(String msg) { status = TaskStatus.FAILED.getValue(); errorMessage = msg; }

        public boolean isTerminal()
        {
            String s = status;
            return TaskStatus.SUCCESS.getValue().equals(s)
                    || TaskStatus.PARTIAL.getValue().equals(s)
                    || TaskStatus.FAILED.getValue().equals(s)
                    || TaskStatus.CANCELLED.getValue().equals(s)
                    || TaskStatus.SKIPPED.getValue().equals(s);
        }

        // Getters for serialization
        public String getSubmissionId() { return submissionId; }
        public String getSyncType() { return syncType; }
        public String getScope() { return scope; }
        public String getOperator() { return operator; }
        public long getCreatedAt() { return createdAt; }
        public String getStatus() { return status; }
        public Long getParentLogId() { return parentLogId; }
        public String getParentStatus() { return parentStatus; }
        public int getTotalSteps() { return totalSteps; }
        public int getSuccessSteps() { return successSteps; }
        public int getFailedSteps() { return failedSteps; }
        public double getElapsedSeconds() { return elapsedSeconds; }
        public String getErrorMessage() { return errorMessage; }
    }
}
