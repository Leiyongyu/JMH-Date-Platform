package com.ruoyi.quartz.util;

import java.util.Date;
import org.quartz.Job;
import org.quartz.JobExecutionContext;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import com.ruoyi.common.constant.Constants;
import com.ruoyi.common.constant.ScheduleConstants;
import com.ruoyi.common.utils.ExceptionUtil;
import com.ruoyi.common.utils.StringUtils;
import com.ruoyi.common.utils.bean.BeanUtils;
import com.ruoyi.common.utils.spring.SpringUtils;
import com.ruoyi.quartz.domain.SysJob;
import com.ruoyi.quartz.domain.SysJobLog;
import com.ruoyi.quartz.service.ISysJobLogService;

/**
 * 抽象quartz调用
 *
 * @author ruoyi
 */
public abstract class AbstractQuartzJob implements Job
{
    private static final Logger log = LoggerFactory.getLogger(AbstractQuartzJob.class);

    /**
     * 线程本地变量
     */
    private static ThreadLocal<Date> threadLocal = new ThreadLocal<>();

    @Override
    public void execute(JobExecutionContext context)
    {
        SysJob sysJob = new SysJob();
        BeanUtils.copyBeanProp(sysJob, context.getMergedJobDataMap().get(ScheduleConstants.TASK_PROPERTIES));
        try
        {
            before(context, sysJob);
            if (sysJob != null)
            {
                doExecute(context, sysJob);
            }
            after(context, sysJob, null);
        }
        catch (Exception e)
        {
            log.error("任务执行异常  - ：", e);
            after(context, sysJob, e);
        }
    }

    /**
     * 执行前
     *
     * @param context 工作执行上下文对象
     * @param sysJob 系统计划任务
     */
    protected void before(JobExecutionContext context, SysJob sysJob)
    {
        threadLocal.set(new Date());
    }

    /**
     * 执行后
     *
     * @param context 工作执行上下文对象
     * @param sysJob 系统计划任务
     */
    protected void after(JobExecutionContext context, SysJob sysJob, Exception e)
    {
        Date startTime = threadLocal.get();
        threadLocal.remove();

        final SysJobLog sysJobLog = new SysJobLog();
        sysJobLog.setJobName(sysJob.getJobName());
        sysJobLog.setJobGroup(sysJob.getJobGroup());
        sysJobLog.setInvokeTarget(sysJob.getInvokeTarget());
        sysJobLog.setStartTime(startTime);
        sysJobLog.setEndTime(new Date());
        long runMs = sysJobLog.getEndTime().getTime() - sysJobLog.getStartTime().getTime();

        // ★ 增强：尝试从 OperationSyncContext 读取业务同步结果，生成更丰富的 job_message
        String enhancedMessage = tryBuildEnhancedMessage(sysJobLog.getJobName(), runMs);
        if (enhancedMessage != null)
        {
            sysJobLog.setJobMessage(enhancedMessage);
        }
        else
        {
            sysJobLog.setJobMessage(sysJobLog.getJobName() + " 总共耗时：" + runMs + "毫秒");
        }

        if (e != null)
        {
            sysJobLog.setStatus(Constants.FAIL);
            String errorMsg = StringUtils.substring(ExceptionUtil.getExceptionMessage(e), 0, 2000);
            sysJobLog.setExceptionInfo(errorMsg);
            // ★ 方案A：失败时创建系统通知
            createFailureNotice(sysJob.getJobName(), errorMsg, runMs);
        }
        else
        {
            sysJobLog.setStatus(Constants.SUCCESS);
        }

        // 写入数据库当中
        SpringUtils.getBean(ISysJobLogService.class).addJobLog(sysJobLog);
    }

    /**
     * 任务失败时创建一条若依系统通知（sys_notice），管理员登录后顶部铃铛可见。
     * 用反射避免 ruoyi-quartz 对 ruoyi-system 的编译期依赖。
     */
    private void createFailureNotice(String jobName, String errorMsg, long runMs)
    {
        try
        {
            // 先检查 OperationSyncContext 中有没有更详细的失败信息
            String detailMsg = null;
            try
            {
                Class<?> ctxClass = Class.forName(
                        "com.ruoyi.system.service.operation.sync.OperationSyncContext");
                Object result = ctxClass.getMethod("get").invoke(null);
                if (result != null)
                {
                    Object msg = result.getClass().getMethod("toJobMessage", Long.class)
                            .invoke(result, (Long) null);
                    if (msg != null) detailMsg = msg.toString();
                }
            }
            catch (Exception ignored) {}

            String title = "【同步失败】" + (jobName != null ? jobName : "定时任务");
            if (title.length() > 50) title = title.substring(0, 50);

            String content = detailMsg != null ? detailMsg
                    : (jobName + " 执行失败，耗时" + runMs + "ms。\n错误：" + errorMsg);

            // 用反射调用 ISysNoticeService.insertNotice()
            Class<?> svcClass = Class.forName("com.ruoyi.system.service.ISysNoticeService");
            Object svc = SpringUtils.getBean(svcClass);
            Class<?> entityClass = Class.forName("com.ruoyi.system.domain.SysNotice");

            Object notice = entityClass.getDeclaredConstructor().newInstance();
            entityClass.getMethod("setNoticeTitle", String.class).invoke(notice, title);
            entityClass.getMethod("setNoticeType", String.class).invoke(notice, "1"); // 1=通知
            entityClass.getMethod("setNoticeContent", String.class).invoke(notice, content);
            entityClass.getMethod("setStatus", String.class).invoke(notice, "0");      // 0=正常
            entityClass.getMethod("setCreateBy", String.class).invoke(notice, "SYSTEM");

            svcClass.getMethod("insertNotice", entityClass).invoke(svc, notice);
        }
        catch (Exception ignored)
        {
            // 反射失败说明 ruoyi-system 模块不可用，静默忽略
        }
    }

    /**
     * 尝试从 OperationSyncContext ThreadLocal 读取业务同步结果，
     * 生成增强的 job_message。如果上下文中没有结果，返回 null 走默认逻辑。
     */
    private String tryBuildEnhancedMessage(String jobName, long runMs)
    {
        try
        {
            Class<?> contextClass = Class.forName(
                    "com.ruoyi.system.service.operation.sync.OperationSyncContext");
            Object result = contextClass.getMethod("get").invoke(null);
            if (result == null)
            {
                return null;
            }
            // 反射调用 OperationSyncResult.toJobMessage(null) 获取增强消息
            // 然后追加若依耗时信息
            Object msg = result.getClass().getMethod("toJobMessage", Long.class).invoke(result, (Long) null);
            if (msg != null)
            {
                return msg.toString() + "（若依耗时：" + runMs + "ms）";
            }
        }
        catch (Exception ignored)
        {
            // 反射失败说明依赖不可用，回退默认行为
        }
        finally
        {
            // 清理 ThreadLocal 防止内存泄漏
            try
            {
                Class<?> contextClass = Class.forName(
                        "com.ruoyi.system.service.operation.sync.OperationSyncContext");
                contextClass.getMethod("clear").invoke(null);
            }
            catch (Exception ignored) {}
        }
        return null;
    }

    /**
     * 执行方法，由子类重载
     *
     * @param context 工作执行上下文对象
     * @param sysJob 系统计划任务
     * @throws Exception 执行过程中的异常
     */
    protected abstract void doExecute(JobExecutionContext context, SysJob sysJob) throws Exception;
}
