# Security Policy

Remote Logger follows the [Rhizomatics security policy](https://github.com/rhizomatics/.github/blob/main/SECURITY.md),
which covers supported versions, what belongs with Home Assistant itself, and what to expect from a report.

## Reporting a vulnerability

Please report it privately, from the [Security tab](https://github.com/rhizomatics/remote_logger/security) of this
repository, with **Report a vulnerability**. Don't open a public issue, discussion or pull request.

Only the latest release gets security fixes.

## What Remote Logger trusts

Remote Logger is a Home Assistant custom integration, so it runs inside Home Assistant with everything Home
Assistant can do. It has no login or network service of its own: it only makes outgoing connections, to the
log collector it is configured with.

- **Administrators** set it up, and are trusted completely, including with the choice of collector, which
  receives everything that is exported.
- **Other Home Assistant users**, and the automations and scripts that call its actions, can add a log record
  with `send_log`. Home Assistant lets any user call any action, so they are not trusted with the configuration,
  the credentials for the collector, or the content of the logs.
- **The content of logs and events** is not trusted at all. Log messages, event names and event data often start
  outside Home Assistant, in a device, an incoming message or another integration.
- **The log collector** is trusted with the logs, but not with Home Assistant: nothing it sends back is acted on.

## Measures in place

### In the integration

- `last_log` and `flush` are for administrators only. `last_log` gives back log content, which Home Assistant
  otherwise shows only to administrators.
- A record added with `send_log` by a user carries that user's id as `user.id`, which the caller can't override.
- `last_log` masks the value of every configured HTTP header, not only `Authorization`.
- The values of event data and state attributes named `code`, `pin`, `password`, `secret`, `token`,
  `access_token`, `refresh_token`, `api_key`, `client_secret` or `entity_picture` are replaced with
  `**REDACTED**` before export, so alarm and lock codes and camera access tokens stay in Home Assistant.
- TLS connections verify the server's certificate, for OTLP and for Syslog over TCP. Syslog can also use a
  private certificate authority and a client certificate (mutual TLS).
- Syslog over UDP can't be encrypted, and the configuration refuses TLS with UDP rather than quietly sending
  plain text.
- A token sent to an OTLP collector over plain HTTP raises a Home Assistant repair issue.
- HTTP redirects from a collector are not followed, so credentials aren't sent on to another address.
- Syslog `APP-NAME`, `MSGID` and structured data names are reduced to the characters RFC 5424 allows, and a
  continuation line can't begin with `<`, so event names, event data and messages can't add fields or records.
- Records waiting for a collector that can't be reached are capped at 10,000, the oldest dropped first, so an
  outage can't use up Home Assistant's memory.
- Error text from a collector is cut to 200 characters before it is logged or shown on a sensor, and a failure
  to format an event logs the event type, not its data.

### In development

- CodeQL analysis and the [OpenSSF Scorecard](https://github.com/rhizomatics/remote_logger/actions/workflows/scorecard.yml)
  run on the default branch, and Bandit and [zizmor](https://docs.zizmor.sh) on every change.
- Dependabot raises dependency and GitHub Action updates, with a cooling-off period for new versions, and
  pull requests get a dependency review.
- Every GitHub Action is pinned to a commit. Workflow tokens have no permissions unless a job needs them, and
  the tests of a pull request run with a read-only token.
- The integration has no runtime dependencies beyond Home Assistant itself, checked by hassfest.
- Releases are built and published by GitHub Actions, not from a developer's machine, with a SHA-256 checksum
  and a build provenance attestation for the zip, which can be checked with
  `gh attestation verify remote_logger.zip --repo rhizomatics/remote_logger`.
- Ruff, mypy and a test suite with over 95% coverage run on every change, with a regression test for each fix.

## Known limitations

- Redaction goes by the name of a key. A secret under another name, or inside a log message or a state value,
  is exported as it is. Only subscribe to the events you need, see
  [Security](https://remote-logger.rhizomatics.org.uk/security/).
- Syslog over UDP, and OTLP over plain HTTP, can be read and altered by anyone on the network path.
- A syslog receiver can't tell who sent a record: anything that can reach it can send records that look like
  Home Assistant's, unless it requires client certificates.
- The collector token and headers are kept as Home Assistant keeps all credentials, in plain text in its
  `.storage` folder and in backups.
- The oldest records are dropped without a count when the cap on waiting records is reached.
