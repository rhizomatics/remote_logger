# Home Assistant Remote Logger

Lauscht auf Home Assistant-Systemprotokollereignisse und sendet strukturierte Protokollereignisse an einen entfernten Syslog- oder OpenTelemetry (OTLP)-Collector. Optional werden weitere Home Assistant-Ereignisse weitergeleitet, z. B. Lebenszyklusereignisse, Dienstaufrufe, Konfigurationsaktualisierungen und Zustandsänderungen.

Die Protokollstruktur wird vom internen Home Assistant-Ereignis beibehalten, sodass mehrzeilige Protokolle und Stack Traces als einzelne Protokolleinträge erhalten bleiben – im Gegensatz zu Console-Scrapern, die pro Zeile ein Ereignis erstellen. Skriptnamen, Zeilennummern und Versionen werden dabei korrekt erfasst.

Unterstützt wird ausschließlich der Home Assistant-Server selbst mit seinen benutzerdefinierten Komponenten. Protokolle von *Apps* (ehemals „Add-ins"), HAOS oder dem HA-Supervisor werden nicht als erfassbare Ereignisse bereitgestellt und erfordern daher eine alternative Lösung. Bert Barons [LogSpout Home Assistant App](https://github.com/bertbaron/hassio-addons/tree/main/logspout) deckt diese Fälle ab. Sie kann in Kombination mit *Remote Logger* verwendet werden, damit Home Assistant gute strukturierte Protokolle hat und alles andere zumindest protokolliert wird.

## Installation

**Remote Logger** ist eine HACS-Komponente, die daher zuerst installiert werden muss. Die Anleitung dazu findet sich unter [Getting Started with HACS](https://www.hacs.xyz/docs/use/).

Die Integration wird über die Home Assistant-Integrationsseite installiert und erfordert **keine YAML-Konfiguration**.

Allerdings ist eine YAML-Änderung an der Home Assistant-Integration [System Log](https://www.home-assistant.io/integrations/system_log/) erforderlich, um die Ereignisweiterleitung für `system_log_event` zu aktivieren.

Home Assistant-Konfiguration

```yaml
system_log:
    fire_event: true
```

## Open Telemetry (OTEL)

Protokolle werden gemäß der Open Telemetry Logs-Spezifikation über eine [Open Telemetry Protocol](https://opentelemetry.io/docs/specs/otlp/)-Verbindung (OTLP) gesendet, entweder als Protobuf oder JSON, derzeit ausschließlich über HTTP (gRPC könnte in Zukunft hinzugefügt werden).

Weitere Informationen finden sich unter [OpenTelemetry Logging](https://opentelemetry.io/docs/specs/otel/logs/).

Protokolleinträge werden gesammelt und gebündelt gesendet.

## Syslog

Nachrichten werden im neueren Format [RFC5424](https://datatracker.ietf.org/doc/html/rfc5424) mit zusätzlichen strukturierten Daten gemäß OTEL-Taxonomie gesendet (siehe [Zusätzliche Attribute](#zus%C3%A4tzliche-attribute)).

Syslog kann per TCP oder UDP übertragen werden.

## Ereignisse

### System-Log-Ereignis

Hinweis auf die Anforderung unter [Installation](#installation), dieses Ereignis zu aktivieren, das standardmäßig nicht ausgelöst wird.

*Remote Logger* schließt eigene Protokollereignisse aus dem Stream aus, um mögliche Ereignisschleifen zu verhindern. Alternativ stehen Fehlerstatistiken und -meldungen als diagnostische Entitäten zur Verfügung.

#### Zusätzliche Attribute

Die folgenden zusätzlichen Attribute, die direkt aus dem Home Assistant-Protokollereignis abgeleitet werden, stehen als Syslog-`STRUCTURED-DATA`-Attribute oder OTEL-Attribute zur Verfügung.

- `code.file.path`
- `code.line.number`
- `code.function.name` (dies ist der `logger`-Wert von Home Assistant)
- `exception.count`
- `exception.first_occurred`
- `exception.stacktrace`

Die OTEL-Taxonomie wird sowohl für OTEL als auch für Syslog verwendet, da es auf dieser Syslog-Ebene keine standardisierte Taxonomie gibt.

### Weitere Ereignisse

*Remote Logger* kann beliebige Home Assistant-Ereignisse protokollieren und kennt die wichtigsten davon, um lesbarere Meldungen zu erzeugen.

Der Einfachheit halber können vier vordefinierte Ereignis-Bundles aktiviert werden.

| Bundle                          | Beschreibung                                                                                                                       |
| ------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| Lebenszyklus                    | Start- und Stoppereignisse des Home Assistant-Servers                                                                              |
| Kernänderungen                  | Laden oder Entladen von Komponenten und Diensten, Konfiguration neu angewendet                                                     |
| Kernaktivität                   | Aktionen, mobile Aktionen, Skripte, ausgeführte Automatisierungen                                                                  |
| Zustandsänderungen              | Zustandsänderungen von Entitäten und Logbucheinträge, ohne Attribute und Kontext um übermäßig große Protokolleinträge zu vermeiden |
| Vollständige Zustandsänderungen | Zustandsänderungen von Entitäten und Logbucheinträge, vollständig und ungekürzt                                                    |

Das Freitextfeld für Ereignisse kann alternativ verwendet werden, um spezifische Home Assistant-Ereignisse oder andere Ereignisse benutzerdefinierter Komponenten auszuwählen.

## Protokoll-Server

Es gibt unzählige Lösungen zum Erfassen, Analysieren, Aggregieren und Speichern von Protokollen.

Eine gut funktionierende Kombination ist [Vector](https://vector.dev) und [GreptimeDb](https://greptime.com) – schnell, schlank, Open Source, anpassbar und unter Docker lauffähig. Vector unterstützt OTEL-Logging sowie Syslog und bietet gute Remapping-Möglichkeiten zur Feinabstimmung jeder Quelle. Protokolle von Docker-Servern, Firewalls, Unifi-Switches oder anderen Quellen lassen sich dann einfach in einer gemeinsamen Zeitachse zusammenführen, zusammen mit Server- und Netzwerkmetriken.

## Diagnostische Entitäten

Home Assistant-Sensoren werden erstellt und aktualisiert, um die Protokollaktivität sowie etwaige Fehler bei der Erzeugung von Protokollmeldungen oder deren Übertragung an entfernte Server zu überwachen.

## Rhizomatics Open Source für Home Assistant

### HACS

- [AutoArm](https://autoarm.rhizomatics.org.uk) - Scharf- und Unscharfschalten von Home Assistant-Alarmzentralen automatisch mit physischen Tasten, Anwesenheit, Kalendern, Sonnenstand und mehr
- [Supernotify](https://supernotify.rhizomatics.org.uk) - Einheitliche Benachrichtigung für einfaches Multi-Kanal-Messaging, einschließlich leistungsstarker Türklingel- und Sicherheitskameraintegration.

### Python / Docker

- [Anpr2MQTT](https://anpr2mqtt.rhizomatics.org.uk) - Integration von ANPR/ALPR-Kennzeichenkameras über Dateisystem (NAS/FTP) nach MQTT mit optionaler Bildanalyse und UK DVLA-Integration.
- [Updates2MQTT](https://updates2mqtt.rhizomatics.org.uk) - Automatische Benachrichtigung per MQTT über Docker-Image-Updates, mit erweiterter Verarbeitung zur Extraktion von Versionen und Release-Notes aus Images sowie der Möglichkeit, Container-Pulls und -Neustarts aus Home Assistant heraus fernzusteuern. Auch verfügbar auf [PyPI](https://pypi.org/project/updates2mqtt/)
