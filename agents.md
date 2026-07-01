# JoyIO - handoff para outros agentes

Este arquivo resume o estado atual do repo e as decisoes que ja foram tomadas, para que outro agente consiga continuar sem reconstruir o contexto do zero.

## Estado atual

- Projeto em Python para Linux ARM64/aarch64.
- Fase atual: Fase 1, captura canonica de entrada.
- A CLI existe e funciona com `joyio list` e `joyio inspect`.
- O fluxo atual e:
  - BlueZ conecta o Joy-Con;
  - o kernel `hid_nintendo` expoe o controle como evdev;
  - o projeto le `event*` via `python-evdev`;
  - os eventos sao normalizados para nomes canonicamente estaveis do JoyIO;
  - `inspect` imprime JSONL puro em `stdout` e diagnosticos em `stderr`.
- O ambiente de desenvolvimento usa `.venv`; o projeto deve continuar sendo instalado e executado por esse ambiente virtual.

## Decisoes ja fixadas

### 1. Backend principal de entrada

- A abordagem principal e `hid_nintendo` do kernel + `evdev`.
- Nao estamos implementando o protocolo Joy-Con bruto em Python agora.
- `hidraw`/HIDAPI ficou como alternativa de fallback, nao como caminho principal.
- Justificativa: menos manutencao, usa calibração e protocolo suportados pelo kernel, e deixa a base pronta para `uinput` depois.

### 2. Fronteira de Bluetooth

- A descoberta e conexao continuam separadas do leitor de eventos.
- Na fase atual a integracao de BlueZ usa `bluetoothctl`.
- A migracao para D-Bus/`org.bluez` continua possivel sem mudar o leitor `evdev`.
- Nao misturar parsing de Bluetooth com normalizacao de eventos.

### 3. Estrategia de produto

- Primeiro CLI/script.
- Depois motor de mapeamento, YAML e saida virtual.
- Servico `systemd` so depois de estabilizar as funcionalidades de captura e mapeamento.

### 4. Contrato de saida

- `joyio inspect` deve manter `stdout` limpo em JSONL.
- Mensagens operacionais, erros e debug vao para `stderr`.
- Eventos nao reconhecidos nao devem ser descartados silenciosamente; eles aparecem como `unmapped:<source>`.

### 5. Identidade canonica dos controles

- Os controles canonicamente traduzidos estao em `src/joyio/controls.py`.
- O contrato e lado-especifico para os Joy-Cons L e R.
- SL/SR sao tratados como botoes digitais, nao como gatilhos analogicos.

## O que ja foi entregue

- `joyio list` lista Joy-Cons pareados.
- `joyio inspect --device left|right|MAC` conecta quando necessario, encontra o `evdev` e imprime eventos normalizados.
- Fixtures reais anonimizadas existem em `tests/fixtures/`.
- Testes automatizados cobrem lista, inspecao, mapeamento canonico, desconexao e separacao `stdout`/`stderr`.
- Existe regra udev restrita em `config/udev/70-joyio.rules`.
- Existe ADR registrando a decisao `hid_nintendo` + `evdev`.

## Arquivos que valem leitura antes de mexer no codigo

- `README.md`
- `FASE_0.md`
- `FASE_1.md`
- `docs/adr/0001-usar-hid-nintendo-e-evdev.md`
- `src/joyio/cli.py`
- `src/joyio/bluetooth.py`
- `src/joyio/devices.py`
- `src/joyio/controls.py`
- `src/joyio/events.py`

## Comandos uteis

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pip install --no-deps -e .
.venv/bin/pytest
.venv/bin/joyio list
.venv/bin/joyio inspect --device right
```

## Pontos importantes para continuidade

### Fase 2 ainda nao implementada

- motor de mapeamento;
- configuracao YAML;
- saida virtual via `uinput`;
- `--dry-run`;
- dead zone, curva de mouse, sensibilidade, invert e limite de velocidade;
- reconexao com backoff;
- validacao de config.

### Ponto tecnico relevante

- O spam de analógico e drift nao devem ser tratados no leitor de eventos.
- Esses problemas entram no motor de mapeamento da Fase 2, para manter o evento bruto fiel ao hardware.

### Permissoes

- O host atual usa `TAG+=uaccess` para acesso aos `event*`.
- Para um servico futuro, isso provavelmente precisara ser revisado para uma politica mais explicita.
- Nao assumir `root` como requisito permanente.

### Bluetooth

- Hoje o pareamento continua sendo manual via GNOME ou `bluetoothctl`.
- O programa so conecta dispositivos ja pareados.
- Se a UX de pareamento virar prioridade, o prox passo e separar melhor descoberta/pareamento/conexao via D-Bus.

## Historico curto

- `b7e427e`: Fase 0, prova de viabilidade com `list` e `inspect`.
- `23dbaa7`: Fase 1, eventos canonicamente normalizados, stdout JSONL puro, fixtures reais e regra udev.

## Se for continuar daqui

1. Nao reverta a decisao de usar `hid_nintendo` + `evdev` sem motivo concreto.
2. Nao colocar YAML ou `uinput` no leitor atual; isso e Fase 2.
3. Se for mexer em Bluetooth, preserve a fronteira entre descoberta/conexao e leitura de eventos.
4. Se for iniciar o motor de mapeamento, trate drift, dead zone e repeticao la, nao na camada de captura.
