package com.ruoyi.system.service.operation.sync;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

@Component
@ConfigurationProperties(prefix = "sync.alert.mail")
public class SyncAlertMailProperties
{
    private String host = "smtp.exmail.qq.com";
    private int port = 465;
    private boolean ssl = true;
    private String username = "";
    private String password = "";
    private String to = "";
    public String getHost() { return host; }
    public void setHost(String value) { host = value; }
    public int getPort() { return port; }
    public void setPort(int value) { port = value; }
    public boolean isSsl() { return ssl; }
    public void setSsl(boolean value) { ssl = value; }
    public String getUsername() { return username; }
    public void setUsername(String value) { username = value; }
    public String getPassword() { return password; }
    public void setPassword(String value) { password = value; }
    public String getTo() { return to; }
    public void setTo(String value) { to = value; }
}
