# Security

Remote Logger copies logs and events out of Home Assistant to another system. That system, and the network in between, then hold whatever was in them, so it is worth choosing what is sent and how.

To report a vulnerability, see the [security policy](https://github.com/rhizomatics/remote_logger/blob/main/SECURITY.md).

## What is exported

| Setting                                      | What leaves Home Assistant                                                                            |
| -------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| Always                                       | Log records at the chosen level and above: logger name, source file and line, message and stack trace |
| Lifecycle events                             | Start and stop events, with no personal data                                                          |
| Core change events                           | Registry changes, including user ids for added, changed and removed users                             |
| Core activity                                | Every action call with its data, automation and script runs, notification actions from the mobile app |
| State changes, without attributes or context | Entity id, old and new state for every state change                                                   |
| State changes                                | The same, plus every attribute and the context, including the id of the user who caused it            |
| Custom events                                | All the data of each event named                                                                      |

Action calls and state attributes can hold things you would not want in a log database: location and presence, who is at home, the text of notifications, and what is playing or being watched. Switch on only what you will use.

### Redaction

The values of event data and state attributes with these names are replaced with `**REDACTED**` before export, at any depth:

`access_token`, `api_key`, `client_secret`, `code`, `entity_picture`, `password`, `pin`, `refresh_token`, `secret`, `token`

This keeps alarm and lock codes, and the access tokens of cameras and media players, in Home Assistant. It goes by the name only, so a secret under a different name, or written into a log message or a state, is still exported.

## Protecting logs in transit

| Protocol                 | Encryption | Notes                                                                                          |
| ------------------------ | ---------- | ---------------------------------------------------------------------------------------------- |
| OTLP with TLS (HTTPS)    | Yes        | The collector's certificate is verified                                                        |
| OTLP without TLS         | No         | The token and all logs are readable on the network. A repair issue is raised if a token is set |
| Syslog over TCP with TLS | Yes        | The server's certificate is verified                                                           |
| Syslog over TCP          | No         |                                                                                                |
| Syslog over UDP          | No         | Can't be encrypted, and messages can be lost or forged by others on the network                |

Plain HTTP or Syslog is reasonable when the collector is on the same host as Home Assistant, or on a network you trust. Otherwise use TLS.

### Private certificates and mutual TLS for Syslog

For a Syslog server with a certificate from your own certificate authority, give the path to the CA certificate, as a PEM file Home Assistant can read, for example `/ssl/syslog-ca.pem`. If the server requires client certificates (mutual TLS), also give the client certificate and, if it is in a separate file, its key. Requiring client certificates is the one way a Syslog server can be sure a record came from Home Assistant.

## Actions

| Action                   | Who can call it                                                                               |
| ------------------------ | --------------------------------------------------------------------------------------------- |
| `remote_logger.send_log` | Any user, automation or script. A record sent by a user has that user's id added as `user.id` |
| `remote_logger.flush`    | Administrators, automations and scripts                                                       |
| `remote_logger.last_log` | Administrators, automations and scripts. Header values are masked in the result               |

An automation, or a script it starts, runs without a user and so is always allowed. A script started from a dashboard by a user who is not an administrator runs as that user, and can't call `flush` or `last_log`.

## The collector

Whatever receives the logs should itself need a login, and should not be reachable from the internet. The [examples](https://remote-logger.rhizomatics.org.uk/examples/index.md) are starting points for a home network, not hardened deployments: set your own passwords, pin image versions, and publish only the ports you use.
