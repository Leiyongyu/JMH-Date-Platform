package com.ruoyi.system.domain.operation;

/**
 * Unified task status for sync, import, and export operations.
 * <p>
 * Lifecycle: PENDING → RUNNING → SUCCESS / PARTIAL / FAILED
 */
public enum TaskStatus
{
    /** Task submitted, not yet started. */
    PENDING("PENDING"),
    /** Task is currently executing. */
    RUNNING("RUNNING"),
    /** Task completed successfully. */
    SUCCESS("SUCCESS"),
    /** Task completed with partial failures (some steps/rows failed). */
    PARTIAL("PARTIAL"),
    /** Task failed entirely. */
    FAILED("FAILED"),
    /** Task was cancelled before completion. */
    CANCELLED("CANCELLED"),
    /** Task was skipped (e.g. no new data). */
    SKIPPED("SKIPPED");

    private final String value;

    TaskStatus(String value)
    {
        this.value = value;
    }

    public String getValue()
    {
        return value;
    }

    /** True if this status represents a terminal (finished) state. */
    public boolean isTerminal()
    {
        return this == SUCCESS || this == PARTIAL || this == FAILED || this == CANCELLED || this == SKIPPED;
    }

    /** True if the task is still in flight. */
    public boolean isRunning()
    {
        return this == PENDING || this == RUNNING;
    }

    public static TaskStatus fromValue(String value)
    {
        if (value == null) return null;
        for (TaskStatus s : values())
        {
            if (s.value.equalsIgnoreCase(value)) return s;
        }
        // Backward-compatible aliases
        if ("PARTIAL_SUCCESS".equalsIgnoreCase(value)) return PARTIAL;
        if ("TIMEOUT".equalsIgnoreCase(value)) return FAILED;
        if ("BUSY".equalsIgnoreCase(value)) return RUNNING;
        return null;
    }

    @Override
    public String toString()
    {
        return value;
    }
}
