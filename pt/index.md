# Home Assistant Remote Logger

Monitoriza os eventos do registo do sistema do Home Assistant e envia eventos de registo estruturados para um coletor remoto Syslog ou OpenTelemetry (OTLP). Opcionalmente reencaminha outros eventos do Home Assistant, como eventos do ciclo de vida, chamadas de serviço, atualizações de configuração e alterações de estado.

A estrutura dos registos é preservada a partir do evento interno do Home Assistant, pelo que os registos multi-linha e os rastreios de pilha são mantidos como entradas únicas — ao contrário dos scrapers de consola, que criam um evento por linha. Os nomes dos scripts, números de linha e versões são corretamente capturados.

Apenas o servidor do Home Assistant com os seus componentes personalizados é suportado. Os registos das *apps* (anteriormente chamadas de "add-ins"), do HAOS ou do supervisor HA não são fornecidos como eventos capturáveis e requerem uma solução alternativa. A [LogSpout Home Assistant App](https://github.com/bertbaron/hassio-addons/tree/main/logspout) de Bert Baron cobre esses casos. Pode ser usada em combinação com o *Remote Logger* para que o Home Assistant tenha bons registos estruturados e tudo o resto fique pelo menos registado.

## Instalação

O **Remote Logger** instala-se a partir do [Home Assistant Marketplace](https://www.home-assistant.io/integrations/marketplace): vá a **Configurações → Marketplace** e procure **Remote Logger**. Antes do Home Assistant 2026.11, instale-o a partir do [HACS](https://www.hacs.xyz/docs/use/).

A integração instala-se a partir da página de integrações do Home Assistant e **não requer configuração YAML**.

No entanto, é necessária uma alteração YAML na integração [System Log](https://www.home-assistant.io/integrations/system_log/) do Home Assistant para ativar o reencaminhamento de eventos `system_log_event`.

Configuração do Home Assistant

```yaml
system_log:
    fire_event: true
```

### Alterar definições

Para alterar para onde os registos são enviados (anfitrião, porta, TLS, token, cabeçalhos e as restantes definições de ligação), abra a entrada na página da integração e escolha **Reconfigurar**. O botão **Configurar** abrange o nível de registo e quais os eventos do Home Assistant que são reencaminhados.

## Open Telemetry (OTEL)

Os registos são enviados utilizando a especificação Open Telemetry Logs através de uma ligação [Open Telemetry Protocol](https://opentelemetry.io/docs/specs/otlp/) (OTLP), em Protobuf ou JSON, atualmente apenas por HTTP (gRPC poderá ser adicionado no futuro).

Para mais informações, consulte [OpenTelemetry Logging](https://opentelemetry.io/docs/specs/otel/logs/).

Os registos são recolhidos e enviados em lote.

## Syslog

As mensagens são enviadas no formato mais recente [RFC5424](https://datatracker.ietf.org/doc/html/rfc5424), com dados estruturados adicionais usando a taxonomia OTEL (ver [Atributos adicionais](#atributos-adicionais)).

O Syslog pode ser enviado por TCP ou UDP.

O **modo RFC 5424 estrito** destina-se a recetores que verificam as mensagens com rigor, como o Grafana Alloy. Ative-o no formulário de configuração do Syslog ou mais tarde com **Reconfigurar**. Os dados estruturados passam a usar os nomes próprios do Home Assistant, como `name`, `source`, `exception` e `event_type`, e as chaves dos dados do evento são encurtadas para o limite de 32 caracteres do RFC (por exemplo, `new_state.attributes.friendly_name` passa a `new.attr.friendly_name`). O `MSGID` é truncado para 32 caracteres, e o SD-ID é `homeassistant@<número>`, com o [IANA Private Enterprise Number](https://www.iana.org/assignments/enterprise-numbers/) indicado ou, se ficar vazio, 67614, o PEN da Rhizomatics. Para testes, pode indicar 32473, o número de documentação do RFC 5612. Sem o modo estrito, são usados os nomes OTEL indicados abaixo.

## Eventos

### Evento do Registo do Sistema

Note o requisito em [Instalação](#instala%C3%A7%C3%A3o) para ativar este evento, que não é acionado por predefinição.

O *Remote Logger* excluirá os seus próprios eventos de registo do fluxo, para evitar a possibilidade de ciclos de eventos. Em alternativa, as estatísticas e mensagens de erro estão disponíveis como entidades de diagnóstico.

#### Atributos adicionais

Os seguintes atributos adicionais, derivados diretamente do evento de registo do Home Assistant, são fornecidos como atributos `STRUCTURED-DATA` do Syslog ou atributos OTEL.

- `code.file.path`
- `code.line.number`
- `code.function.name` (este é o valor `logger` do Home Assistant)
- `exception.count`
- `exception.first_occurred`
- `exception.stacktrace`

A taxonomia OTEL é usada tanto para OTEL como para Syslog, uma vez que não existe uma taxonomia padrão a este nível do Syslog.

### Outros eventos

O *Remote Logger* pode registar qualquer evento do Home Assistant e conhece os principais para criar mensagens mais legíveis.

Por conveniência, podem ser ativados quatro conjuntos de eventos pré-definidos.

| Conjunto                       | Descrição                                                                                                                          |
| ------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------- |
| Ciclo de vida                  | Eventos de início e paragem do servidor Home Assistant                                                                             |
| Alterações do núcleo           | Carregamento ou descarregamento de componentes e serviços, configuração reaplicada                                                 |
| Atividade do núcleo            | Ações, ações móveis, scripts, automatizações executadas                                                                            |
| Alterações de estado           | Alterações de estado de entidades e entradas do livro de registo, sem atributos ou contexto para evitar entradas demasiado grandes |
| Alterações de estado completas | Alterações de estado de entidades e entradas do livro de registo, completas e sem redução                                          |

O campo de eventos em formato livre pode ser usado como alternativa para selecionar eventos específicos do Home Assistant ou quaisquer outros eventos de componentes personalizados.

## Servidores de registos

Existem imensas soluções para capturar, analisar, agregar e armazenar registos.

Uma combinação que funciona bem é [Vector](https://vector.dev) e [GreptimeDb](https://greptime.com) — rápidos, leves, open source, personalizáveis e executáveis em Docker. O Vector suporta o registo OTEL e Syslog, com boas capacidades de remapeamento para afinar cada fonte. É então fácil integrar registos de servidores Docker, firewalls, switches Unifi ou outras fontes numa única linha de tempo, juntamente com métricas de servidor e rede.

## Entidades de diagnóstico

São criados e atualizados sensores do Home Assistant para monitorizar a atividade dos registos, bem como quaisquer erros na geração de mensagens de registo ou no seu envio para servidores remotos.

## Remoção

1. No Home Assistant, vá a **Definições** > **Dispositivos e serviços** > **Remote Logger**. Em cada entrada, abra o menu (⋮) e escolha **Eliminar**. A exportação de registos para de imediato, e os sensores de diagnóstico e o respetivo dispositivo são removidos.
1. Para remover também os ficheiros da integração, vá a **Configurações → Marketplace**, abra o **Remote Logger** e escolha **Desinstalar** no menu de três pontos. (**Excluir e desinstalar** faz também o passo 1.) Antes do Home Assistant 2026.11, abra o **HACS**, procure **Remote Logger**, escolha **Remover** e reinicie o Home Assistant.
1. Se adicionou `fire_event: true` em `system_log:` no `configuration.yaml` apenas para o Remote Logger, pode retirá-lo.

## Rhizomatics Open Source para Home Assistant

### Home Assistant Marketplace

- [AutoArm](https://autoarm.rhizomatics.org.uk) - Armar e desarmar automaticamente painéis de controlo de alarme do Home Assistant usando botões físicos, presença, calendários, sol e muito mais
- [Supernotify](https://supernotify.rhizomatics.org.uk) - Notificação unificada para mensagens multi-canal simples, com integração avançada de campaínhas e câmaras de segurança.

### Python / Docker

- [Anpr2MQTT](https://anpr2mqtt.rhizomatics.org.uk) - Integra câmaras ANPR/ALPR de reconhecimento de matrículas através do sistema de ficheiros (NAS/FTP) para MQTT com análise opcional de imagens e integração com a DVLA do Reino Unido.
- [Updates2MQTT](https://updates2mqtt.rhizomatics.org.uk) - Notifica automaticamente por MQTT as atualizações de imagens Docker, com tratamento avançado para extrair versões e notas de lançamento das imagens, e opção para desencadear remotamente a obtenção e reinício de contentores a partir do Home Assistant. Também disponível no [PyPI](https://pypi.org/project/updates2mqtt/)
