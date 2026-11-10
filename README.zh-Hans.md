![Remote Logger](https://remote-logger.rhizomatics.org.uk/assets/images/remote-logger-dark-256x256.png){ align=left }


# Home Assistant Remote Logger

[![Rhizomatics Open Source](https://img.shields.io/badge/rhizomatics%20open%20source-lightseagreen)](https://github.com/rhizomatics) [![Home Assistant Marketplace][marketplacebadge]][marketplace]

[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/rhizomatics/ha_remote_logger)
![Coverage](https://raw.githubusercontent.com/rhizomatics/ha_remote_logger/refs/heads/badges/badges/coverage.svg)
![Tests](https://raw.githubusercontent.com/rhizomatics/ha_remote_logger/refs/heads/badges/badges/tests.svg)
[![Github Deploy](https://github.com/rhizomatics/ha_remote_logger/actions/workflows/deploy.yml/badge.svg?branch=main)](https://github.com/rhizomatics/ha_remote_logger/actions/workflows/deploy.yml)
[![CodeQL](https://github.com/rhizomatics/ha_remote_logger/actions/workflows/github-code-scanning/codeql/badge.svg)](https://github.com/rhizomatics/ha_remote_logger/actions/workflows/github-code-scanning/codeql)
[![Dependabot Updates](https://github.com/rhizomatics/ha_remote_logger/actions/workflows/dependabot/dependabot-updates/badge.svg)](https://github.com/rhizomatics/ha_remote_logger/actions/workflows/dependabot/dependabot-updates)

<br/>
<br/>
<br/>


监听 Home Assistant 系统日志事件，并将结构化日志事件发送到远程 Syslog 或 OpenTelemetry（OTLP）采集器。可选择转发其他 Home Assistant 事件，例如生命周期事件、服务调用、配置更新和状态变更。

![OTEL 堆栈跟踪示例](https://remote-logger.rhizomatics.org.uk/assets/images/otel_stack_trace.png){width=600}

日志结构从 Home Assistant 内部事件中完整保留，因此多行日志和堆栈跟踪作为单条日志条目保存——与控制台抓取工具不同，后者会为每行创建一个日志事件。脚本名称、行号和版本信息均能被正确捕获。

仅支持 Home Assistant 服务器本身及其自定义组件。来自 *应用*（原称"附加组件"）、HAOS 或 HA 监督者的日志不作为可捕获事件提供，需要其他解决方案。Bert Baron 的 [LogSpout Home Assistant App](https://github.com/bertbaron/hassio-addons/tree/main/logspout) 可覆盖这些情况，可与 *Remote Logger* 结合使用，使 Home Assistant 拥有良好的结构化日志，同时其他日志也能得到记录。

## 安装

**Remote Logger** 可从 [Home Assistant Marketplace][marketplace] 安装：前往 **设置 → Marketplace**，搜索 **Remote Logger**。Home Assistant 2026.11 之前的版本，请改为通过 [HACS](https://www.hacs.xyz/docs/use/) 安装。

该集成通过 Home Assistant 集成页面安装，**无需 YAML 配置**。

![选择集成](https://remote-logger.rhizomatics.org.uk/assets/images/config_choose.png){width=400}

但需要在 Home Assistant 的 [System Log](https://www.home-assistant.io/integrations/system_log/) 集成中修改 YAML，以启用 `system_log_event` 的事件转发。

```yaml title="Home Assistant 配置"
system_log:
    fire_event: true
```

### 更改设置

要更改日志的发送目标（主机、端口、TLS、令牌、请求头及其他连接设置），请在集成页面打开该条目并选择 **重新配置**。**配置** 按钮用于设置日志级别以及转发哪些 Home Assistant 事件。

## Open Telemetry（OTEL）

日志通过 [Open Telemetry Protocol](https://opentelemetry.io/docs/specs/otlp/)（OTLP）连接，按照 Open Telemetry Logs 规范发送，支持 Protobuf 或 JSON 格式，目前仅支持 HTTP（未来可能添加 gRPC）。

![配置 OTLP](https://remote-logger.rhizomatics.org.uk/assets/images/config_otel.png){width=480}

更多信息请参阅 [OpenTelemetry Logging](https://opentelemetry.io/docs/specs/otel/logs/)。

日志记录将批量收集后统一发送。

## Syslog

消息以更新的 [RFC5424](https://datatracker.ietf.org/doc/html/rfc5424) 格式发送，并附带使用 OTEL 分类法的额外结构化数据（参见[附加属性](#附加属性)）。

Syslog 支持 TCP 或 UDP 传输。

![配置 Syslog](https://remote-logger.rhizomatics.org.uk/assets/images/config_syslog.png){width=360}

**严格 RFC 5424 模式**适用于会严格检查消息的接收端，例如 Grafana Alloy。可在 Syslog 设置表单中启用，或之后通过**重新配置**启用。启用后，结构化数据使用 Home Assistant 自己的名称，如 `name`、`source`、`exception` 和 `event_type`，事件数据的键会缩短到 RFC 规定的 32 个字符以内（例如 `new_state.attributes.friendly_name` 变为 `new.attr.friendly_name`）。`MSGID` 截断为 32 个字符，SD-ID 为 `homeassistant@<编号>`，编号使用你填写的 [IANA Private Enterprise Number](https://www.iana.org/assignments/enterprise-numbers/)，留空时使用文档用编号 32473。未启用严格模式时，使用下方列出的 OTEL 名称。

## 事件

### 系统日志事件

请注意[安装](#安装)中启用此事件的要求，该事件默认不触发。

*Remote Logger* 会从事件流中排除自身的日志事件，以防止事件循环。作为替代方案，错误统计和消息可通过诊断实体查看。

#### 附加属性

以下附加属性直接从 Home Assistant 日志事件中提取，作为 Syslog `STRUCTURED-DATA` 属性或 OTEL 属性提供。

* `code.file.path`
* `code.line.number`
* `code.function.name`（即 Home Assistant 的 `logger` 值）
* `exception.count`
* `exception.first_occurred`
* `exception.stacktrace`

OTEL 分类法同时用于 OTEL 和 Syslog，因为在此级别的 Syslog 中没有标准分类法。

### 其他事件

*Remote Logger* 可以记录任何 Home Assistant 事件，并了解核心事件以生成更易读的消息。

为方便使用，可开启四组预定义事件包。

| 事件包 | 描述 |
| ------ | ---- |
| 生命周期 | Home Assistant 服务器启动和停止事件 |
| 核心变更 | 组件和服务的加载或卸载、配置重新应用 |
| 核心活动 | 动作、移动端动作、脚本、自动化执行 |
| 状态变更 | 实体状态变更和日志本条目，去除属性和上下文以避免日志条目过大 |
| 完整状态变更 | 实体状态变更和日志本条目，完整且未经裁剪 |

自由格式事件框可作为替代方式，用于选择特定的 Home Assistant 事件或任何自定义组件事件。

![OpenObserve 中的 Home Assistant 事件](https://remote-logger.rhizomatics.org.uk/assets/images/ha_events_in_openobserve.png){width=720}

## 日志服务器

用于捕获、分析、聚合和存储日志的解决方案不计其数。

一个运行良好的组合是 [Vector](https://vector.dev) 和 [GreptimeDb](https://greptime.com)——快速、轻量、开源、可定制，并可在 Docker 下运行。Vector 支持 OTEL 日志记录和 Syslog，具有良好的重映射能力以精细调整每个来源。随后可轻松将 Docker 服务器、防火墙、Unifi 交换机等各处的日志整合到同一时间线，并附带服务器和网络指标。


## 诊断实体

系统会创建并更新 Home Assistant 传感器，用于监控日志活动，以及生成日志消息或将其发送到远程服务器时出现的任何错误。

![诊断实体](https://remote-logger.rhizomatics.org.uk/assets/images/diagnostic_entities.png){width=480}

## 移除

1. 在 Home Assistant 中打开 **设置** > **设备与服务** > **Remote Logger**。对每个条目，打开其菜单 (⋮) 并选择 **删除**。日志导出会立即停止，诊断传感器及其设备也会被移除。
2. 如需同时移除集成文件，前往 **设置 → Marketplace**，打开 **Remote Logger**，在三点菜单中选择 **卸载**（选择 **删除并卸载** 会同时完成第 1 步）。Home Assistant 2026.11 之前的版本：打开 **HACS**，找到 **Remote Logger**，选择 **移除**，然后重启 Home Assistant。
3. 如果你只是为了 Remote Logger 才在 `configuration.yaml` 的 `system_log:` 下添加了 `fire_event: true`，可以将其删除。

##  Rhizomatics Home Assistant 开源项目

### Home Assistant Marketplace
- [AutoArm](https://autoarm.rhizomatics.org.uk) - 使用实体按钮、存在感应、日历、太阳位置等自动布撤防 Home Assistant 报警控制面板
- [Supernotify](https://supernotify.rhizomatics.org.uk) - 统一通知，轻松实现多渠道消息推送，包含强大的门铃和安防摄像头集成。


### Python / Docker

- [Anpr2MQTT](https://anpr2mqtt.rhizomatics.org.uk) - 通过文件系统（NAS/FTP）将 ANPR/ALPR 车牌摄像头集成到 MQTT，支持可选的图像分析和英国 DVLA 集成。
- [Updates2MQTT](https://updates2mqtt.rhizomatics.org.uk) - 自动通过 MQTT 通知 Docker 镜像更新，具备从镜像中提取版本和发布说明的高级处理能力，并支持从 Home Assistant 远程拉取和重启容器。同样可在 [PyPI](https://pypi.org/project/updates2mqtt/) 获取。

[marketplace]: https://www.home-assistant.io/integrations/marketplace
[marketplacebadge]: https://img.shields.io/badge/Home%20Assistant-Marketplace-blue.svg
