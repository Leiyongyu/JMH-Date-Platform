package com.ruoyi.system.service.operation.sync;

/**
 * ThreadLocal 上下文，用于在 Quartz 任务执行期间暂存 OperationSyncResult，
 * 供 AbstractQuartzJob.after() 读取并增强 sys_job_log 的 job_message。
 *
 * 使用方式：
 * <pre>
 *   OperationSyncContext.set(result);
 *   try { ... } finally { OperationSyncContext.clear(); }
 * </pre>
 *
 * @author JMH
 */
public class OperationSyncContext
{
    private static final ThreadLocal<OperationSyncResult> HOLDER = new ThreadLocal<>();

    private OperationSyncContext() {}

    public static void set(OperationSyncResult result)
    {
        HOLDER.set(result);
    }

    public static OperationSyncResult get()
    {
        return HOLDER.get();
    }

    public static void clear()
    {
        HOLDER.remove();
    }
}
