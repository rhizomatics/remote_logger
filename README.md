![Remote Logger](https://remote-logger.rhizomatics.org.uk/assets/images/remote-logger-dark-256x256.png){ align=left }


# Remote Logger for Home Assistant

[![Rhizomatics Open Source](https://img.shields.io/badge/rhizomatics%20open%20source-lightseagreen)](https://github.com/rhizomatics) [![managed by hq](https://raw.githubusercontent.com/rhizomatics/hq/main/assets/badge-managed-by-hq.svg)](https://hq.rhizomatics.org.uk/) [![Home Assistant Marketplace][marketplacebadge]][marketplace]

![py3.14](https://img.shields.io/badge/Python-3.14-blue)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/rhizomatics/ha_remote_logger)
![Coverage](https://raw.githubusercontent.com/rhizomatics/ha_remote_logger/refs/heads/badges/badges/coverage.svg)
![Tests](https://raw.githubusercontent.com/rhizomatics/ha_remote_logger/refs/heads/badges/badges/tests.svg)
[![Github Deploy](https://github.com/rhizomatics/ha_remote_logger/actions/workflows/deploy.yml/badge.svg?branch=main)](https://github.com/rhizomatics/ha_remote_logger/actions/workflows/deploy.yml)
[![CodeQL](https://github.com/rhizomatics/ha_remote_logger/actions/workflows/github-code-scanning/codeql/badge.svg)](https://github.com/rhizomatics/ha_remote_logger/actions/workflows/github-code-scanning/codeql)
[![Dependabot Updates](https://github.com/rhizomatics/ha_remote_logger/actions/workflows/dependabot/dependabot-updates/badge.svg)](https://github.com/rhizomatics/ha_remote_logger/actions/workflows/dependabot/dependabot-updates)

<br/>
<br/>
<br/>

Use log aggregation and analysis tools to get a complete picture of your home automation. Remote Logger for Home Assistant listens to Home Assistant logging at source and sends structured log events to a remote Syslog or OpenTelemetry (OTLP) collector. Optionally forwards other Home Assistant events, such as lifecycle events, service calls, configuration updates, state changes.

![Example OTEL Stack Trace](https://remote-logger.rhizomatics.org.uk/assets/images/otel_stack_trace.png){width=600}

Unlike many logging solutions that scrape consoles logs, Remote Logger taps into either the root Python logger or the `system_log_event` Event fired by Home Assistant, preserving the **full structure so multi-line logs and stacktraces are preserved as single log entries**, utilizes the Home Assistant logic to **tie exceptions back to source code lines**, and will capture script names, line numbers and versions properly.

Only Home Assistant server itself, with its custom components is supported. Logs from *apps* (previously known as 'add-ins'), HAOS or the HA Supervisor aren't provided as events to be captured, so require an alternative solution, like Bert Baron's [LogSpout Home Assistant App](https://github.com/bertbaron/hassio-addons/tree/main/logspout) will cover these. It can be used in combination with *Remote Logger* so that Home Assistant has good structured logs, and everything else is at least logged. Since it uses Syslog and OTLP it can also be easily integrated with practically
everything else in your environment, including SIEM cybersecurity logs from firewalls, Unifi networking, Docker logs etc. See the section on [aggregators](https://remote-logger.rhizomatics.org.uk/aggregators/) for suggestions if you're not familiar with these.

Translations are available for Dutch, English, French, German, Hindi, Italian, Japanese, Polish, Portuguese, Simplified Mandarin and Spanish.

## Installation

Install **Remote Logger** from the [Home Assistant Marketplace][marketplace]: go to **Settings → Marketplace** and search for **Remote Logger**. Before Home Assistant 2026.11, install it from [HACS](https://www.hacs.xyz/docs/use/) instead.

The integration installs using the Home Assistant integrations page, and has **no YAML configuration**.

![Choose Integration](https://remote-logger.rhizomatics.org.uk/assets/images/config_choose.png){width=400}

### Changing Settings

To change where logs are sent (host, port, TLS, token, headers and the other connection settings), open the entry on the integration's page and choose **Reconfigure**. The **Configure** button covers the log level and which Home Assistant events are forwarded.

### Event Based Logging

If choosing event based logging over the Python root logger, then a YAML change is required to the Home Assistant [System Log](https://www.home-assistant.io/integrations/system_log/) integration, to enable event forwarding for `system_log_event`. This is not required if using the default Python root logger approach.

```yaml title="Home Assistant Configuration"
system_log:
    fire_event: true
```

!!! tip "Choosing a Log Format"

    If you're not sure about which log format to choose, Open Telemetry (*aka* **OTEL Logging**, *aka* **OTLP**) is the best if you have a modern logging service that can handle it. It has the richest format, for example knows how to hold a multi-line stacktrace attached to a log message, and generally requires minimal configuration. Syslog is the best choice if the back end logging is more primitive, since it has been around since the dawn of time, although is much more semantically limited.

## Open Telemetry (OTEL)

Logs are sent using Open Telemetry Logs specification over a [Open Telemetry Protocol](https://opentelemetry.io/docs/specs/otlp/)(OTLP) connection, either as Protobuf or JSON, and currently only as HTTP (gRPC may be added in future).

![Configure OTLP](https://remote-logger.rhizomatics.org.uk/assets/images/config_otel.png){width=480}

For more information, see [OpenTelemetry Logging](https://opentelemetry.io/docs/specs/otel/logs/).

Log records are collected and sent in a bundle

## Syslog

Messages are sent using the more recent [RFC5424](https://datatracker.ietf.org/doc/html/rfc5424) format, with additional structured data using OTEL taxonomy (see [Additional Attributes](#additional-attributes)).

Syslog can be sent as TCP or UDP.

![Configure Syslog](https://remote-logger.rhizomatics.org.uk/assets/images/config_syslog.png){width=360}

**Strict RFC 5424 mode** is for receivers that check messages closely, such as Grafana Alloy. Turn it on in the Syslog setup form, or later with **Reconfigure**. Structured data then uses Home Assistant's own names, such as `name`, `source`, `exception` and `event_type`, and event data keys are shortened to fit the RFC's 32-character limit (for example `new_state.attributes.friendly_name` becomes `new.attr.friendly_name`). `MSGID` is cut to 32 characters, and the SD-ID is `homeassistant@<number>`, using the [IANA Private Enterprise Number](https://www.iana.org/assignments/enterprise-numbers/) you enter, or 67614, the Rhizomatics PEN, if you leave it empty. For testing, you can enter 32473, the RFC 5612 documentation number, instead. Without strict mode, the OTEL names below are used.

## Events

### System Log Event

Note the requirement at [Installation](#installation) to enable this event, which isn't fired by default. This
is limited to *Warning* and *Error* events. Find out more at the [System Log](https://www.home-assistant.io/integrations/system_log/) integration documentation.

*Remote Logger* will omit its own log events from the stream, to prevent the possibility of event loops. As an alternative, error stats and messages are available as diagnostic entities.

#### Additional Attributes

The following additional attributes, derived directly from the
Home Assistant log event, are provided as Syslog `STRUCTURED-DATA` attributes, or OTEL attributes.

* `code.file.path`
* `code.line.number`
* `code.function.name` (this is the `logger` value from Home Assistant)
* `exception.count`
* `exception.first_occurred`
* `exception.stacktrace`

OTEL taxonomy is used for both OTEL and Syslog since there's no standard taxonomy at this level of Syslog.

### Other Events

*Remote Logger* can log any Home Assistant event, and knows about the core ones, in order to create a more readable message. Find out more in the [Events](https://remote-logger.rhizomatics.org.uk/events/) guidance.

![Home Assistant Events in OpenObserve](https://remote-logger.rhizomatics.org.uk/assets/images/ha_events_in_openobserve.png){width=720}

## Log Servers

There are a zillion possible solutions for capturing, analyzing, aggregating and storing logs. Generally a log setup requires:

* **Collector** - The thing that sits on the monitored service and sends out the logs. This *Remote Logger* is a collector for Home Assistant core, as is [LogSpout Home Assistant App](https://github.com/bertbaron/hassio-addons/tree/main/logspout) for HAOS.
* **Aggregator** - Receives logs from collectors, enriches, filters, converts formats and forwards on. See [Log Aggregators](https://remote-logger.rhizomatics.org.uk/aggregators/) for more information.
* **Store** - Typically a database that holds the logs, and any column indexes or free text search indexes
* **Analytics** - Query by SQL or similar, keyword search, graphing, counting etc

These suggestions are for options that are open source and free, at least for home use, and will work in Docker.

* [Vector](https://vector.dev) as the aggregator and [GreptimeDb](https://greptime.com) as the store and analytics - they are fast, lightweight, open source, customizable and run under Docker. Vector has support for OTEL logging, as well as Syslog, and has good remapping ability to fine tune each source. Its then easy to pull in logs from Docker servers, firewalls, Unifi switches or wherever else into one time-line, as well as server and network metrics.  See the [examples](https://remote-logger.rhizomatics.org.uk/examples/vector_greptimedb/) for a sample configuration.

* [OpenObserve](https://openobserve.ai) can do all three jobs ( aggregator, store, analytics ) for many sources, although it now recommends using Vector for Syslog. It also has a more functional log query interface, especially for people used to Splunk, and reuses the *VRL* (Vector Remap Language) for its own pipelines.


## Diagnostic Entities

Home Assistant sensors are created and updated to monitor log activity, plus any errors either generating log messages or posting them to remote servers.

## Diagnostic Actions

Home Assistant actions are supported to send a test event, force flush the log
buffers and show the last payload posted.

![Diagnostic Entities](https://remote-logger.rhizomatics.org.uk/assets/images/diagnostic_entities.png){width=480}

![Event Counter Sensor](https://remote-logger.rhizomatics.org.uk/assets/images/events_counter_sensor.png){width=480}

## Removal

1. In Home Assistant, go to **Settings** > **Devices & services** > **Remote Logger**. For each entry, open its menu (⋮) and choose **Delete**. Log export stops straight away, and the diagnostic sensors and their device are removed.
2. To remove the integration's files as well, go to **Settings → Marketplace**, open **Remote Logger** and choose **Uninstall** from the three dots menu. (**Delete and uninstall** there does step 1 as well.) Before Home Assistant 2026.11, open **HACS**, find **Remote Logger**, choose **Remove**, then restart Home Assistant.
3. If you added `fire_event: true` under `system_log:` in `configuration.yaml` only for Remote Logger, you can take it out again.

##  Rhizomatics Open Source for Home Assistant

### Home Assistant Marketplace
- [Appliance AutoNotify](https://appliance-autonotify.rhizomatics.org.uk) - Live activities on your phone for dishwashers, robot vacuums, power monitors etc with no config, no YAML, no blueprints, no automations.
- [Auto Arm](https://autoarm.rhizomatics.org.uk) - Automatically arm and disarm Home Assistant alarm control panels using physical buttons, presence, calendars, sun and more. Integrates with Frigate profiles.
- [Camera AutoNotify](https://camera-autonotify.rhizomatics.org.uk) - Instant notifications for Frigate (and other camera systems coming) with no config, no blueprints, no YAML, no automations.
- [Supernotify](https://supernotify.rhizomatics.org.uk) - Unified notification for easy multi-channel messaging, including powerful chime and security camera integration.


### Python / Docker

- [Anpr2MQTT](https://anpr2mqtt.rhizomatics.org.uk) - Integrate with ANPR/ALPR licence plate cameras via file system (NAS/FTP) to MQTT with optional image analysis and UK DVLA integration.
- [Home Assistant REPL](https://homeassistant-repl.rhizomatics.org.uk) - Python REPL for direct internal API and SQL access for Home Assistant development and data exploration.
- [Updates2MQTT](https://updates2mqtt.rhizomatics.org.uk) - Automatically notify via MQTT on Docker image updates, with advanced handling to extract versions and release notes from images, and option to remotely pull and restart containers from Home Assistant. Also available on [PyPI](https://pypi.org/project/updates2mqtt/)

[marketplace]: https://www.home-assistant.io/integrations/marketplace
[marketplacebadge]: https://img.shields.io/badge/Home%20Assistant-Marketplace-blue.svg
