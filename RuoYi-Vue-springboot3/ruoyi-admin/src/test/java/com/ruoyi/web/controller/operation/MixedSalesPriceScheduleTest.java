package com.ruoyi.web.controller.operation;

import com.ruoyi.quartz.domain.SysJob;
import com.ruoyi.quartz.util.ScheduleUtils;
import java.time.Instant;
import java.util.Date;
import java.util.Properties;
import org.junit.jupiter.api.Test;
import org.quartz.CronTrigger;
import org.quartz.impl.StdSchedulerFactory;
import static org.junit.jupiter.api.Assertions.*;

class MixedSalesPriceScheduleTest
{
    @Test
    void monthlyPriceJobRunsAtSevenShanghaiTimeOnDayThree() throws Exception
    {
        var props=new Properties();
        props.setProperty("org.quartz.scheduler.instanceName","mixed-price-test");
        props.setProperty("org.quartz.threadPool.threadCount","1");
        props.setProperty("org.quartz.threadPool.makeThreadsDaemons","true");
        props.setProperty("org.quartz.jobStore.class","org.quartz.simpl.RAMJobStore");
        var scheduler=new StdSchedulerFactory(props).getScheduler();
        try
        {
            var job=new SysJob(); job.setJobId(1L);job.setJobName("混销售价");job.setJobGroup("TEST");
            job.setInvokeTarget("pythonEbayMixedSalesPriceTask.runMonthly()");
            job.setCronExpression("0 0 7 3 * ?");job.setStatus("0");job.setConcurrent("1");job.setMisfirePolicy("3");
            ScheduleUtils.createScheduleJob(scheduler,job);
            var trigger=(CronTrigger)scheduler.getTrigger(ScheduleUtils.getTriggerKey(1L,"TEST"));
            assertEquals("Asia/Shanghai",trigger.getTimeZone().getID());
            ((org.quartz.spi.MutableTrigger)trigger).setStartTime(Date.from(Instant.parse("2026-10-01T00:00:00Z")));
            assertEquals(Instant.parse("2026-11-02T23:00:00Z"),
                    trigger.getFireTimeAfter(Date.from(Instant.parse("2026-11-01T00:00:00Z"))).toInstant());
        }
        finally { scheduler.shutdown(); }
    }
}
