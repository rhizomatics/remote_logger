# Configuration

Remote Logger is set up from **Settings** > **Devices & services** > **Add integration**. There is no YAML configuration. The settings come in two groups:

- **Connection settings** say where logs go. They are asked for when the entry is added, and changed later with **Reconfigure** on the entry's menu. A test log record is sent to check them before they are saved.
- **Event settings** say what is sent. They are asked for after the connection settings, and changed later with **Configure**.

## OpenTelemetry (OTLP) Connection

Logs are posted over HTTP to `http(s)://<host>:<port><path>`.

| Setting                    | Default    | Description                                                                                                                                                                                                                                        |
| -------------------------- | ---------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Collector host             | (required) | Hostname or IP address of the OTLP collector.                                                                                                                                                                                                      |
| Collector port             | `4318`     | HTTP port of the collector. gRPC (port 4317) isn't supported.                                                                                                                                                                                      |
| Use TLS (HTTPS)            | off        | Send over HTTPS. The collector's certificate is checked.                                                                                                                                                                                           |
| Payload encoding           | `protobuf` | `protobuf` or `json`. Both are standard OTLP; use `json` if your collector only accepts that.                                                                                                                                                      |
| Batch max size             | `20`       | Records held before an early send, from 1 to 10000. See [Sending Logs](#sending-logs).                                                                                                                                                             |
| Custom resource attributes | (none)     | Comma-separated `key=value` pairs added to the resource of every record, for example `deployment.environment=production,service.namespace=home`.                                                                                                   |
| Token type                 | `bearer`   | How the token is put in the `Authorization` header: `bearer` sends `Bearer <token>`; `basic` base64-encodes a `username:password` token; `raw_basic` sends `Basic <token>` with a token that is already encoded; `api_key` sends `ApiKey <token>`. |
| Access token               | (none)     | Optional token for the `Authorization` header. Use TLS when sending a token, or a repair issue is raised.                                                                                                                                          |
| Additional headers         | (none)     | Extra HTTP headers, one `Name: value` per entry, for example `stream-name: my-stream`.                                                                                                                                                             |
| Logs endpoint path         | `/v1/logs` | Path after `host:port`. Some services add a prefix, such as `/api/otlp/v1/logs`.                                                                                                                                                                   |
| Client timeout             | `10`       | Seconds to wait for the collector, from 1 to 300.                                                                                                                                                                                                  |

If the collector answers HTTP 401 or 403, Home Assistant asks for a new token (re-authentication) and shows the entry as needing attention.

## Syslog Connection

Messages use [RFC 5424](https://datatracker.ietf.org/doc/html/rfc5424) format. Only one Syslog entry can be added.

| Setting                 | Default         | Description                                                                                                                                            |
| ----------------------- | --------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Syslog server host      | (required)      | Hostname or IP address of the syslog server.                                                                                                           |
| Syslog server port      | `514`           | Port of the syslog server.                                                                                                                             |
| Transport protocol      | `udp`           | `udp` sends and forgets; `tcp` keeps a connection and uses octet-counted framing (RFC 6587).                                                           |
| Use TLS (TCP only)      | off             | Encrypt the TCP connection. Not available with UDP.                                                                                                    |
| CA certificate file     | (none)          | Path to a PEM file with the certificate authority for a private CA. Leave empty to use the system certificate store.                                   |
| Client certificate file | (none)          | Path to a PEM client certificate, for servers that require mutual TLS.                                                                                 |
| Client key file         | (none)          | Path to the PEM private key for the client certificate, if it isn't in the same file.                                                                  |
| Application name        | `homeassistant` | The `APP-NAME` field of each message.                                                                                                                  |
| Syslog facility         | `local0`        | Facility used to work out the `PRI` value.                                                                                                             |
| Batch max size          | `20`            | Messages held before an early send, from 1 to 10000. See [Sending Logs](#sending-logs).                                                                |
| Client timeout          | `10`            | Seconds to wait when connecting over TCP, from 1 to 300.                                                                                               |
| Strict RFC 5424 mode    | off             | Syslog-native output for receivers that check messages closely, such as Grafana Alloy. See [Syslog](https://remote-logger.rhizomatics.org.uk/#syslog). |
| Enterprise number       | `67614`         | IANA Private Enterprise Number for the strict mode SD-ID `homeassistant@<number>`. 32473 (RFC 5612) can be used for testing.                           |

## Event Settings

These are the same for both backends.

| Setting                                              | Default | Description                                                                                                                                                                                                                                                                                                                   |
| ---------------------------------------------------- | ------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Use System Log events in place of Python root logger | off     | Off: records are taken from Python's root logger, at or above the minimum log level. On: records come from the `system_log_event` event, which only carries warnings and errors, and needs `fire_event: true` under `system_log:` (see [Event Based Logging](https://remote-logger.rhizomatics.org.uk/#event-based-logging)). |
| Minimum log level                                    | `INFO`  | `DEBUG`, `INFO`, `WARNING`, `ERROR` or `CRITICAL`. Only used with the root logger.                                                                                                                                                                                                                                            |
| Home Assistant lifecycle events                      | off     | Start, started and stop events.                                                                                                                                                                                                                                                                                               |
| Home Assistant core change events                    | off     | Components loaded, configuration and service changes, dashboards, themes and users.                                                                                                                                                                                                                                           |
| Home Assistant core activity                         | off     | Service calls, automations triggered and scripts started.                                                                                                                                                                                                                                                                     |
| State changes, without attributes or context         | off     | Each state change with its old and new state only, and logbook entries.                                                                                                                                                                                                                                                       |
| State changes                                        | off     | Each state change in full, and logbook entries. Choose only one of the two state change options.                                                                                                                                                                                                                              |
| Serialize event data into log body                   | off     | Puts the event data in the log body as JSON, keeping only `entity_id`, `domain` and `service` as attributes. Off, each data field is its own attribute, so a log database may make a column for every field.                                                                                                                  |
| Custom events                                        | (none)  | Other Home Assistant event names to send, one per entry, for example `zha_event`.                                                                                                                                                                                                                                             |
| Suppress system_log_event as event name              | on      | Records from the system log are sent without an event name. Turn off when using Remote Logger as a general event recorder, so all event types can be told apart.                                                                                                                                                              |

See [Events](https://remote-logger.rhizomatics.org.uk/events/index.md) for what each event group contains.

## Sending Logs

Records are buffered in memory and sent in batches:

- every 120 seconds;
- sooner, when the buffer reaches the **Batch max size**;
- when Home Assistant stops, or the entry is unloaded or reconfigured;
- when the `remote_logger.flush` action is called.

If an OTLP collector can't be reached, or rejects a batch, that batch is dropped and counted by the **Posting Errors** sensor. Syslog messages that couldn't be sent are kept and retried on the next send. At most 10000 records are buffered; beyond that the oldest are dropped. A warning is logged once when the collector becomes unavailable, and an info message once when it can be reached again.

The diagnostic sensors are read from in-memory counters every 30 seconds.
