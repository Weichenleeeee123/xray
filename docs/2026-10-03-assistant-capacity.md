# 小企助手容量与发布验收

本次默认单次输入容量提高到 600000 字符，相关证据读取容量提高到 400000 字符。完整材料与否定条件仍保留；显式配置较小容量时仍执行限制。应用字符数不等同于模型 token 容量，网关的实际限制与请求超时仍可能使请求失败。

生产环境文件中的旧值会覆盖代码默认值，因此发布时必须同步设置：

```dotenv
XRAY_CASE_MEMORY_ENABLED=1
XRAY_ASSISTANT_CONTEXT_MODE=selective
XRAY_CASE_MEMORY_DIR=/var/lib/qier/case_memory
XRAY_ASSISTANT_CONTEXT_CHARS=600000
XRAY_ASSISTANT_EVIDENCE_CHARS=400000
```

保留当前模型、密钥、持久化目录及原始案卷，记忆目录仅服务账号可访问。先备份环境文件和运行数据，确认无执行中任务后重启服务。不能只更新代码或刷新浏览器。

发布后核对两个公网域名 `/api/health` 的实际值：`assistant_context.mode=selective`、`memory_enabled=true`、`context_chars=600000`、`evidence_chars=400000`，并核对 `deployment.release_id`。接口只展示非敏感的容量数值，不展示记忆目录或内容。

回归覆盖：约 40 万字符材料不截断而进入模型调用、400 条合成记录的综合问题完整按需读取、显式小预算仍拦截、健康接口反映实际配置。上述合成容量测试使用假模型验证应用传参，不代表外部网关已验证能接收任意 60 万字符输入。

回退时恢复备份环境与旧版本链接，保留所有案卷、记忆和发布目录。
