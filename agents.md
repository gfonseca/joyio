# JoyIO - handoff para outros agentes

Este arquivo resume o estado atual do repo e as decisoes que ja foram tomadas, para que outro agente consiga continuar sem reconstruir o contexto do zero.

## Estado atual

- Projeto em Python para Linux ARM64/aarch64.
- Fase atual: Fase 3, robustez e reconexao em foreground.
- A CLI funciona com `joyio list`, `joyio inspect`, `joyio validate-config` e `joyio run`.
- O fluxo atual e:
  - BlueZ conecta o Joy-Con;
  - o kernel `hid_nintendo` expoe o controle como evdev;
  - o projeto le `event*` via `python-evdev`;
  - os eventos sao normalizados para nomes canonicamente estaveis do JoyIO;
  - `inspect` imprime JSONL puro em `stdout` e diagnosticos em `stderr`.
  - `run` coordena L e R no mesmo controle logico, com ciclo de vida independente por lado;
  - `--dry-run` imprime as acoes em JSONL; sem ele, a saida usa `uinput`.
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
- O runtime considera L+R um unico controle logico; `left`/`right` identificam a origem, nao modos de execucao separados.
- No YAML, botoes ficam sob `mappings.buttons.left` e `mappings.buttons.right`, evitando colisao entre SL/SR.

## O que ja foi entregue

- `joyio list` lista Joy-Cons pareados.
- `joyio inspect --device left|right|MAC` conecta quando necessario, encontra o `evdev` e imprime eventos normalizados.
- `joyio validate-config` valida integralmente o schema v1 antes de acessar hardware.
- `joyio run` exige e executa o par L/R no mesmo pipeline, com saida `dry-run` ou `uinput`.
- `config.example.yaml` e um perfil funcional para o par Joy-Con L/R.
- Fixtures reais anonimizadas existem em `tests/fixtures/`.
- Testes automatizados cobrem lista, inspecao, mapeamento canonico, desconexao e separacao `stdout`/`stderr`.
- Existe regra udev restrita em `config/udev/70-joyio.rules`.
- Existe ADR registrando a decisao `hid_nintendo` + `evdev`.
- A suite possui 67 testes sem dependencia de hardware.
- `tests/test_functional_profile.py` atravessa YAML, mapping e dry-run para todos os 22 botoes, mouse e scroll horizontal/vertical.
- `PERFORMANCE.md` registra benchmarks ARM64, parametros evdev reais e decisoes do caminho critico.

## Arquivos que valem leitura antes de mexer no codigo

- `README.md`
- `docs/project/FASE_0.md`
- `docs/project/FASE_1.md`
- `docs/project/FASE_2.md`
- `docs/project/FASE_3.md`
- `docs/project/README.md`
- `docs/project/GESTAO_PROJETO.md`
- `docs/project/PROMPTS_ROADMAP.md`
- `docs/project/Melhorias.md`
- `docs/adr/0001-usar-hid-nintendo-e-evdev.md`
- `src/joyio/cli.py`
- `src/joyio/bluetooth.py`
- `src/joyio/devices.py`
- `src/joyio/controls.py`
- `src/joyio/events.py`

O `README.md` e intencionalmente uma pagina de apresentacao e manual do usuario. Detalhes de arquitetura, fases e benchmarks devem permanecer nos documentos tecnicos vinculados ao final dele.

O backlog ativo e sua ordem ficam em `docs/project/Melhorias.md` e `docs/project/GESTAO_PROJETO.md`. Use um prompt de `docs/project/PROMPTS_ROADMAP.md` por vez e mantenha limite de uma tarefa em andamento.

## Comandos uteis

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pip install --no-deps -e .
.venv/bin/pytest
.venv/bin/pytest -q tests/test_functional_profile.py
.venv/bin/joyio list
.venv/bin/joyio inspect --device right
.venv/bin/joyio validate-config config.example.yaml
.venv/bin/joyio run --config config.example.yaml --dry-run
```

## Pontos importantes para continuidade

### Fase 2 implementada

- motor de mapeamento com `tap`, `hold` e acordes;
- schema YAML v1 estrito e exemplo executavel;
- saida virtual via `uinput` e backend `--dry-run`;
- dead zone radial, curva, sensibilidade, inversao e limite de velocidade;
- mouse pelo analogico esquerdo e scroll horizontal/vertical pelo analogico direito;
- Joy-Con L: `ZL` clique esquerdo e `L` direito; Joy-Con R: `ZR` clique direito e `R` esquerdo;
- integracao temporal a 120 Hz e residuos fracionarios;
- liberacao de entradas presas no encerramento/falha;
- multiplexacao simultanea dos Joy-Cons L/R e selecao obrigatoria de um controle de cada lado;

### Fase 3 em andamento

- reconexao independente por lado com backoff e limite opcional implementada;
- o runtime preserva o `uinput`, o mapping e o leitor do lado que continua ativo;
- leitores `evdev` entram e saem dinamicamente, inclusive se o caminho `event*` mudar;
- a desconexao libera apenas holds e movimento analogico originados naquele lado;
- `bluetoothctl connect` roda sem bloquear o loop de entrada e `InProgress` e tratado como pendente;
- `--no-reconnect` permite diagnostico de sessao unica;
- prova real no Joy-Con R detectou `ENODEV` e retomou de `event10` para `event8` sem reiniciar o processo;
- controles com `WakeAllowed: no` podem exigir um botao fisico para acordar antes da reconexao;
- prova fisica independente nos dois lados, hot reload e servico ainda pendentes;
- metricas/logging estruturado;
- testes prolongados e empacotamento reproduzivel.

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
2. Nao colocar YAML ou `uinput` no leitor de eventos; preserve as fronteiras da Fase 2.
3. Se for mexer em Bluetooth, preserve a fronteira entre descoberta/conexao e leitura de eventos.
4. Preserve a separacao entre config, mapping, output e runtime ao implementar reconexao.
