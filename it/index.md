# Home Assistant Remote Logger

Ascolta gli eventi del log di sistema di Home Assistant e invia eventi di log strutturati a un collector remoto Syslog o OpenTelemetry (OTLP). Facoltativamente, inoltra altri eventi di Home Assistant, come eventi del ciclo di vita, chiamate a servizi, aggiornamenti di configurazione e cambiamenti di stato.

La struttura dei log viene preservata dall'evento interno di Home Assistant, quindi i log multiriga e gli stack trace vengono conservati come singole voci di log, a differenza degli scraper della console che creano un evento per riga, e catturano correttamente nomi degli script, numeri di riga e versioni.

È supportato solo il server Home Assistant stesso con i suoi componenti personalizzati. I log delle *app* (in precedenza chiamate 'add-in'), di HAOS o del supervisore HA non vengono forniti come eventi catturabili, quindi richiedono una soluzione alternativa. Per questi casi, [LogSpout Home Assistant App](https://github.com/bertbaron/hassio-addons/tree/main/logspout) di Bert Baron è una buona opzione. Può essere usata in combinazione con *Remote Logger* in modo che Home Assistant abbia log strutturati di qualità e tutto il resto venga comunque registrato.

## Installazione

**Remote Logger** è un componente HACS, quindi è necessario prima installare HACS seguendo le istruzioni di [Getting Started with HACS](https://www.hacs.xyz/docs/use/).

L'integrazione si installa dalla pagina delle integrazioni di Home Assistant e **non richiede configurazione YAML**.

È però necessaria una modifica YAML all'integrazione [System Log](https://www.home-assistant.io/integrations/system_log/) di Home Assistant per abilitare l'inoltro degli eventi `system_log_event`.

Configurazione Home Assistant

```yaml
system_log:
    fire_event: true
```

## Open Telemetry (OTEL)

I log vengono inviati utilizzando la specifica Open Telemetry Logs tramite una connessione [Open Telemetry Protocol](https://opentelemetry.io/docs/specs/otlp/) (OTLP), come Protobuf o JSON, attualmente solo via HTTP (gRPC potrebbe essere aggiunto in futuro).

Per ulteriori informazioni, consulta [OpenTelemetry Logging](https://opentelemetry.io/docs/specs/otel/logs/).

I record di log vengono raccolti e inviati in un bundle.

## Syslog

I messaggi vengono inviati nel formato più recente [RFC5424](https://datatracker.ietf.org/doc/html/rfc5424), con dati strutturati aggiuntivi che utilizzano la tassonomia OTEL (vedi [Attributi aggiuntivi](#attributi-aggiuntivi)).

Syslog può essere inviato via TCP o UDP.

## Eventi

### Evento System Log

Nota il requisito in [Installazione](#installazione) per abilitare questo evento, che non viene attivato di default.

*Remote Logger* escluderà i propri eventi di log dallo stream, per evitare la possibilità di loop di eventi. In alternativa, le statistiche e i messaggi di errore sono disponibili come entità diagnostiche.

#### Attributi aggiuntivi

I seguenti attributi aggiuntivi, derivati direttamente dall'evento di log di Home Assistant, sono forniti come attributi `STRUCTURED-DATA` di Syslog o attributi OTEL.

- `code.file.path`
- `code.line.number`
- `code.function.name` (questo è il valore `logger` di Home Assistant)
- `exception.count`
- `exception.first_occurred`
- `exception.stacktrace`

La tassonomia OTEL viene utilizzata sia per OTEL che per Syslog poiché non esiste una tassonomia standard a questo livello di Syslog.

### Altri eventi

*Remote Logger* può registrare qualsiasi evento di Home Assistant e conosce quelli principali, al fine di creare un messaggio più leggibile.

Per comodità, è possibile attivare quattro bundle di eventi predefiniti.

| Bundle                        | Descrizione                                                                                                                 |
| ----------------------------- | --------------------------------------------------------------------------------------------------------------------------- |
| Ciclo di vita                 | Eventi di avvio e arresto del server Home Assistant                                                                         |
| Modifiche al core             | Caricamento o scaricamento di componenti e servizi, configurazione riapplicata                                              |
| Attività del core             | Azioni, azioni mobile, script, automazioni eseguiti                                                                         |
| Cambiamenti di stato          | Cambiamenti di stato delle entità e voci del diario, con stati privi di attributi e contesto per evitare voci di log enormi |
| Cambiamenti di stato completi | Cambiamenti di stato delle entità e voci del diario, completi e non ridotti                                                 |

Il campo eventi in formato libero può essere usato come alternativa per selezionare specifici eventi di Home Assistant o qualsiasi altro evento di componenti personalizzati.

## Server di log

Esistono innumerevoli soluzioni per acquisire, analizzare, aggregare e archiviare i log.

Una combinazione che funziona bene è [Vector](https://vector.dev) e [GreptimeDb](https://greptime.com) — veloci, leggeri, open source, personalizzabili e funzionanti con Docker. Vector supporta il logging OTEL e Syslog, con buone capacità di remapping per affinare ogni sorgente. È poi facile integrare log da server Docker, firewall, switch Unifi o qualsiasi altra fonte in un'unica timeline, insieme a metriche di server e rete.

## Entità diagnostiche

Vengono create e aggiornate delle sensor di Home Assistant per monitorare l'attività dei log, oltre a eventuali errori nella generazione dei messaggi di log o nel loro invio ai server remoti.

## Rhizomatics Open Source per Home Assistant

### HACS

- [AutoArm](https://autoarm.rhizomatics.org.uk) - Arma e disarma automaticamente i pannelli di controllo allarme di Home Assistant usando pulsanti fisici, presenze, calendari, sole e altro
- [Supernotify](https://supernotify.rhizomatics.org.uk) - Notifica unificata per messaggistica multi-canale semplice, con integrazione avanzata di campanelli e telecamere di sicurezza.

### Python / Docker

- [Anpr2MQTT](https://anpr2mqtt.rhizomatics.org.uk) - Integra fotocamere ANPR/ALPR per targhe tramite file system (NAS/FTP) a MQTT con analisi opzionale delle immagini e integrazione DVLA UK.
- [Updates2MQTT](https://updates2mqtt.rhizomatics.org.uk) - Notifica automaticamente via MQTT gli aggiornamenti delle immagini Docker, con gestione avanzata per estrarre versioni e note di rilascio dalle immagini, e opzione per eseguire pull e riavvio remoto dei container da Home Assistant. Disponibile anche su [PyPI](https://pypi.org/project/updates2mqtt/)
