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


Nasłuchuje zdarzeń dziennika systemowego Home Assistant i wysyła ustrukturyzowane zdarzenia dziennika do zdalnego
kolektora Syslog lub OpenTelemetry (OTLP). Opcjonalnie przekazuje inne zdarzenia Home Assistant, takie jak
zdarzenia cyklu życia, wywołania usług, aktualizacje konfiguracji i zmiany stanu.

![Przykładowy ślad stosu OTEL](https://remote-logger.rhizomatics.org.uk/assets/images/otel_stack_trace.png){width=600}

Struktura dzienników jest zachowywana z wewnętrznego zdarzenia Home Assistant, dzięki czemu wieloliniowe dzienniki i ślady stosu są przechowywane jako pojedyncze wpisy — w przeciwieństwie do scraperów konsoli, które tworzą jedno zdarzenie na wiersz. Nazwy skryptów, numery linii i wersje są prawidłowo przechwytywane.

Obsługiwany jest wyłącznie serwer Home Assistant wraz z jego niestandardowymi komponentami. Dzienniki z *aplikacji* (dawniej „dodatków"), HAOS ani supervisora HA nie są dostępne jako przechwytywalne zdarzenia i wymagają alternatywnego rozwiązania. [LogSpout Home Assistant App](https://github.com/bertbaron/hassio-addons/tree/main/logspout) Berta Barona pokrywa te przypadki. Może być używana w połączeniu z *Remote Logger*, aby Home Assistant miał dobre ustrukturyzowane dzienniki, a wszystko inne było przynajmniej rejestrowane.

## Instalacja

**Remote Logger** instaluje się z [Home Assistant Marketplace][marketplace]: przejdź do **Ustawienia → Marketplace** i wyszukaj **Remote Logger**. Przed Home Assistant 2026.11 zainstaluj go z [HACS](https://www.hacs.xyz/docs/use/).

Integracja instaluje się ze strony integracji Home Assistant i **nie wymaga konfiguracji YAML**.

![Wybierz integrację](https://remote-logger.rhizomatics.org.uk/assets/images/config_choose.png){width=400}

Wymagana jest jednak zmiana YAML w integracji [System Log](https://www.home-assistant.io/integrations/system_log/) Home Assistant, aby włączyć przekazywanie zdarzeń `system_log_event`.

```yaml title="Konfiguracja Home Assistant"
system_log:
    fire_event: true
```

### Zmiana ustawień

Aby zmienić miejsce wysyłania logów (host, port, TLS, token, nagłówki i pozostałe ustawienia połączenia), otwórz wpis na stronie integracji i wybierz **Zmień konfigurację**. Przycisk **Konfiguruj** obejmuje poziom logowania i to, które zdarzenia Home Assistant są przekazywane.

## Open Telemetry (OTEL)

Dzienniki są wysyłane zgodnie ze specyfikacją Open Telemetry Logs przez połączenie [Open Telemetry Protocol](https://opentelemetry.io/docs/specs/otlp/) (OTLP), jako Protobuf lub JSON, obecnie wyłącznie przez HTTP (gRPC może zostać dodane w przyszłości).

![Konfiguruj OTLP](https://remote-logger.rhizomatics.org.uk/assets/images/config_otel.png){width=480}

Więcej informacji znajdziesz w [OpenTelemetry Logging](https://opentelemetry.io/docs/specs/otel/logs/).

Rekordy dzienników są zbierane i wysyłane partiami.

## Syslog

Wiadomości są wysyłane w nowszym formacie [RFC5424](https://datatracker.ietf.org/doc/html/rfc5424) z dodatkowymi danymi strukturalnymi według taksonomii OTEL (zob. [Dodatkowe atrybuty](#dodatkowe-atrybuty)).

Syslog może być wysyłany przez TCP lub UDP.

![Konfiguruj Syslog](https://remote-logger.rhizomatics.org.uk/assets/images/config_syslog.png){width=360}

**Ścisły tryb RFC 5424** jest przeznaczony dla odbiorców, którzy dokładnie sprawdzają wiadomości, np. Grafana Alloy. Włącza się go w formularzu konfiguracji Syslog lub później przez **Zmień konfigurację**. Dane strukturalne używają wtedy własnych nazw Home Assistant, takich jak `name`, `source`, `exception` i `event_type`, a klucze danych zdarzeń są skracane do limitu 32 znaków z RFC (np. `new_state.attributes.friendly_name` staje się `new.attr.friendly_name`). `MSGID` jest skracany do 32 znaków, a SD-ID to `homeassistant@<numer>`, z podanym [IANA Private Enterprise Number](https://www.iana.org/assignments/enterprise-numbers/) lub, gdy pole jest puste, z 67614, numerem PEN firmy Rhizomatics. Do testów można zamiast tego podać 32473, numer dokumentacyjny z RFC 5612. Bez trybu ścisłego używane są nazwy OTEL podane poniżej.

## Zdarzenia

### Zdarzenie dziennika systemowego

Zwróć uwagę na wymóg w sekcji [Instalacja](#instalacja) dotyczący włączenia tego zdarzenia,
które domyślnie nie jest wyzwalane.

*Remote Logger* wyklucza własne zdarzenia dziennika ze strumienia, aby zapobiec
możliwości pętli zdarzeń. Alternatywnie statystyki i komunikaty błędów
są dostępne jako encje diagnostyczne.

#### Dodatkowe atrybuty

Następujące dodatkowe atrybuty, wywodzone bezpośrednio ze zdarzenia dziennika
Home Assistant, są udostępniane jako atrybuty `STRUCTURED-DATA` Sysloga lub atrybuty OTEL.

* `code.file.path`
* `code.line.number`
* `code.function.name` (jest to wartość `logger` z Home Assistant)
* `exception.count`
* `exception.first_occurred`
* `exception.stacktrace`

Taksonomia OTEL jest używana zarówno dla OTEL, jak i Sysloga, ponieważ na tym poziomie Sysloga nie istnieje standardowa taksonomia.

### Inne zdarzenia

*Remote Logger* może rejestrować dowolne zdarzenia Home Assistant i zna
główne z nich, aby tworzyć bardziej czytelne komunikaty.

Dla wygody można włączyć cztery predefiniowane zestawy zdarzeń.

| Zestaw | Opis |
| ------ | ---- |
| Cykl życia | Zdarzenia uruchamiania i zatrzymywania serwera Home Assistant |
| Zmiany rdzenia | Ładowanie lub wyładowywanie komponentów i usług, ponowne zastosowanie konfiguracji |
| Aktywność rdzenia | Akcje, akcje mobilne, skrypty, wykonane automatyzacje |
| Zmiany stanu | Zmiany stanu encji i wpisy dziennika, bez atrybutów i kontekstu, aby unikać zbyt dużych wpisów |
| Pełne zmiany stanu | Zmiany stanu encji i wpisy dziennika, pełne i nieprzycinane |

Pole zdarzeń w formacie swobodnym może być używane jako alternatywa do wybierania
konkretnych zdarzeń Home Assistant lub dowolnych innych zdarzeń niestandardowych komponentów.

![Zdarzenia Home Assistant w OpenObserve](https://remote-logger.rhizomatics.org.uk/assets/images/ha_events_in_openobserve.png){width=720}

## Serwery dzienników

Istnieje niezliczona liczba rozwiązań do przechwytywania, analizowania, agregowania i przechowywania dzienników.

Dobrze działającą kombinacją jest [Vector](https://vector.dev) i [GreptimeDb](https://greptime.com) — szybkie, lekkie, open source, konfigurowalne i działające pod Dockerem. Vector obsługuje logowanie OTEL oraz Syslog i ma dobre możliwości przemapowania do dostrajania każdego źródła. Następnie łatwo jest zbierać dzienniki z serwerów Docker, zapór sieciowych, przełączników Unifi i innych źródeł w jednej osi czasu, wraz z metrykami serwera i sieci.


## Encje diagnostyczne

Sensory Home Assistant są tworzone i aktualizowane w celu monitorowania aktywności dzienników oraz wszelkich błędów podczas generowania komunikatów dziennika lub wysyłania ich do zdalnych serwerów.

![Encje diagnostyczne](https://remote-logger.rhizomatics.org.uk/assets/images/diagnostic_entities.png){width=480}

## Usuwanie

1. W Home Assistant przejdź do **Ustawienia** > **Urządzenia oraz usługi** > **Remote Logger**. Dla każdego wpisu otwórz menu (⋮) i wybierz **Usuń**. Eksport logów zatrzymuje się od razu, a sensory diagnostyczne i ich urządzenie zostają usunięte.
2. Aby usunąć także pliki integracji, przejdź do **Ustawienia → Marketplace**, otwórz **Remote Logger** i wybierz **Odinstaluj** z menu z trzema kropkami. (**Usuń i odinstaluj** wykonuje też krok 1.) Przed Home Assistant 2026.11 otwórz **HACS**, znajdź **Remote Logger**, wybierz **Usuń**, a następnie uruchom ponownie Home Assistant.
3. Jeśli `fire_event: true` w sekcji `system_log:` w `configuration.yaml` zostało dodane tylko dla Remote Logger, można je usunąć.

##  Rhizomatics Open Source dla Home Assistant

### Home Assistant Marketplace
- [AutoArm](https://autoarm.rhizomatics.org.uk) - Automatyczne uzbrajanie i rozbrajanie paneli alarmowych Home Assistant za pomocą fizycznych przycisków, obecności, kalendarzy, słońca i nie tylko
- [Supernotify](https://supernotify.rhizomatics.org.uk) - Ujednolicone powiadomienia dla łatwej wielokanałowej komunikacji, z potężną integracją dzwonków i kamer bezpieczeństwa.


### Python / Docker

- [Anpr2MQTT](https://anpr2mqtt.rhizomatics.org.uk) - Integracja kamer ANPR/ALPR do rozpoznawania tablic rejestracyjnych przez system plików (NAS/FTP) do MQTT z opcjonalną analizą obrazu i integracją z brytyjskim DVLA.
- [Updates2MQTT](https://updates2mqtt.rhizomatics.org.uk) - Automatyczne powiadamianie przez MQTT o aktualizacjach obrazów Docker, z zaawansowaną obsługą wyodrębniania wersji i informacji o wydaniu z obrazów oraz opcją zdalnego pobierania i restartowania kontenerów z Home Assistant. Dostępny również na [PyPI](https://pypi.org/project/updates2mqtt/)

[marketplace]: https://www.home-assistant.io/integrations/marketplace
[marketplacebadge]: https://img.shields.io/badge/Home%20Assistant-Marketplace-blue.svg
