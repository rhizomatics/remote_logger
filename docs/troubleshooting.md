---
title: Troubleshooting
description: Known limitations of Remote Logger, and what to check when logs don't arrive.
---
# Troubleshooting

## Known Limitations

* **Home Assistant core only.** Logs from apps (add-ons), the Supervisor and the operating system aren't sent. Use
  something like the [LogSpout Home Assistant App](https://github.com/bertbaron/hassio-addons/tree/main/logspout)
  alongside Remote Logger for those.
* **Records from before setup are missed.** Remote Logger starts listening when its entry is set up, so anything
  logged earlier in Home Assistant's startup isn't sent.
* **Remote Logger's own log records aren't sent**, to avoid loops. Its activity is shown by the diagnostic sensors.
* **System log events carry only warnings and errors.** With *Use System Log events in place of Python root
  logger* on, info and debug records aren't available.
* **OTLP over HTTP only.** gRPC isn't supported.
* **One Syslog entry.** Several OTLP entries can be added, one per collector host and port.
* **TLS for Syslog needs TCP.** Syslog over UDP is always unencrypted.
* **Delivery is best effort.** An OTLP batch that fails to send is dropped, Syslog over UDP has no
  acknowledgement, and at most 10000 records are held while the endpoint is unavailable. See
  [Sending Logs](configuration.md#sending-logs).

## Setup Says It Can't Connect

When the connection settings are saved, a test log record is sent with the message *Home Assistant remote_logger
configuration validation, safe to ignore*.

* Check the host and port, and that nothing between Home Assistant and the collector blocks the port.
* For OTLP, check **Use TLS** matches the collector (`http` or `https`), and the **Logs endpoint path**; many
  services want a prefix before `/v1/logs`.
* For Syslog with TLS, check the certificate file paths can be read by Home Assistant and are PEM files.

If the collector is down when Home Assistant starts, the entry shows as *retrying setup* and connects when the
collector is back.

## No Logs Arrive

1. Wait up to two minutes: records are sent in batches. Calling the **Flush** action (`remote_logger.flush`) sends
   them straight away.
2. Look at the **Posting Errors** sensor on the Remote Logger device. Its `last_error_message` attribute has the
   collector's reply or the connection error.
3. Enable the **Postings** sensor (it's disabled by default) to see whether batches are being sent at all.
4. Call the **Last Log** action (`remote_logger.last_log`) to see the last payload that was sent.
5. With *Use System Log events in place of Python root logger* on, check `fire_event: true` is set under
   `system_log:` (see [Event Based Logging](index.md#event-based-logging)).

The Home Assistant log shows one warning when the endpoint becomes unavailable, and one info message when it can be
reached again.

## The Collector Rejects Records

* An OTLP collector that answers HTTP 4xx may not accept the **Payload encoding**; try `json` instead of
  `protobuf`, or the other way round.
* A Syslog receiver that drops or rejects messages, such as Grafana Alloy, may need **Strict RFC 5424 mode**.

## Repairs and Re-authentication

* **Access token sent without encryption**: an OTLP token is set but TLS is off. Reconfigure the entry to use TLS,
  or ignore the repair if the collector is on the same host or a trusted network.
* **Re-authentication**: the collector answered HTTP 401 or 403. Enter a new token in the prompt shown on the
  integration's page.

## Reporting a Problem

Download the diagnostics from the entry's menu (⋮ > **Download diagnostics**) and attach them to an
[issue](https://github.com/rhizomatics/remote_logger/issues). Tokens, headers and the client key path are
redacted, but the last payload sent is included, so check it for anything you don't want to share.
