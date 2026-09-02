package com.ruoyi.common.utils;

import java.io.PrintWriter;
import java.io.StringWriter;
import java.util.List;
import org.apache.commons.lang3.exception.ExceptionUtils;

/**
 * 错误信息处理类。
 *
 * @author ruoyi
 */
public class ExceptionUtil
{
    /**
     * 获取exception的详细错误信息。
     */
    public static String getExceptionMessage(Throwable e)
    {
        StringWriter sw = new StringWriter();
        e.printStackTrace(new PrintWriter(sw, true));
        return sw.toString();
    }

    /**
     * 获取根因优先的异常详情，避免Quartz反射异常的外层堆栈截断真正业务原因。
     */
    public static String getRootFirstExceptionMessage(Throwable e)
    {
        if (e == null)
        {
            return "";
        }

        List<Throwable> chain = ExceptionUtils.getThrowableList(e);
        Throwable root = chain.isEmpty() ? e : chain.get(chain.size() - 1);
        String rootMessage = StringUtils.defaultString(root.getMessage(), "无异常消息");
        rootMessage = StringUtils.substring(rootMessage, 0, 800);

        StringBuilder result = new StringBuilder(1024);
        result.append("根因：")
                .append(root.getClass().getName())
                .append(": ")
                .append(rootMessage)
                .append('\n');
        result.append("异常链：");
        for (int i = 0; i < chain.size(); i++)
        {
            if (i > 0)
            {
                result.append(" -> ");
            }
            result.append(chain.get(i).getClass().getSimpleName());
        }
        result.append("\n完整堆栈：\n").append(getExceptionMessage(e));
        return result.toString();
    }

    public static String getRootErrorMessage(Exception e)
    {
        Throwable root = ExceptionUtils.getRootCause(e);
        root = (root == null ? e : root);
        if (root == null)
        {
            return "";
        }
        String msg = root.getMessage();
        if (msg == null)
        {
            return "null";
        }
        return StringUtils.defaultString(msg);
    }
}
