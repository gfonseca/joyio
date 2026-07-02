# Fase 2 — mapeamento e saída virtual

Data: 2026-07-01.

## Resultado

O JoyIO agora conecta um Joy-Con L e um Joy-Con R como uma única sessão lógica, carrega um schema YAML v1 estrito, transforma eventos canônicos de ambos em ações abstratas e pode enviá-las para um backend JSONL de diagnóstico ou para um dispositivo virtual Linux `uinput`.

## Componentes

- `joyio.config`: modelos imutáveis, leitura segura do YAML e validação integral;
- `joyio.mapping`: ações abstratas e motor com estado para `tap`, `hold`, combinações, ponteiro e scroll bidimensional;
- `joyio.output`: backends `DryRunOutput` e `UInputOutput`;
- `joyio.runtime`: ciclo em foreground para o par e liberação garantida das entradas;
- `joyio.devices.read_runtime_events`: multiplexação dos dois nós evdev com ticks a 120 Hz para o mouse não depender da frequência dos relatórios HID.

O leitor de Joy-Con continua sem conhecer YAML ou comandos do computador. O backend de saída não conhece Bluetooth nem eventos evdev de origem.

## Contrato de movimento

Cada analógico usa dead zone radial. O vetor restante é reescalado para `[0, 1]`, passa pela potência configurada em `acceleration` e é limitado por `max_speed`. O runtime integra por tempo monotônico e preserva resíduos fracionários independentes para ponteiro e scroll. O backend traduz scroll para `REL_WHEEL` e `REL_HWHEEL`.

Um tick atrasado é limitado a 100 ms para impedir saltos grandes após uma pausa do processo. A normalização diagonal mantém a direção e não multiplica acidentalmente a velocidade máxima.

## Segurança de estado

- transições físicas repetidas são ignoradas pelo motor;
- o estado físico usa `(side, control)`, evitando colisão entre `SL`/`SR` esquerdo e direito;
- saídas compartilhadas usam contagem de referências, evitando soltar uma tecla ainda mantida pelo outro Joy-Con;
- acordes pressionam teclas na ordem declarada e soltam na ordem inversa;
- `tap` não repete a ação no release físico;
- o backend mantém o conjunto de teclas/botões pressionados;
- saída, interrupção e desconexão passam por `release_all()` antes do fechamento.

## Teste manual

```bash
.venv/bin/joyio validate-config config.example.yaml
.venv/bin/joyio run --config config.example.yaml --dry-run
.venv/bin/joyio run --config config.example.yaml
```

O primeiro comando não acessa hardware. O segundo acessa o Joy-Con, mas não `/dev/uinput`. O terceiro cria o teclado/mouse virtual.

## Testes automatizados

```text
50 passed
```

A cobertura inclui um teste funcional de todas as entradas do perfil, schema e erros com caminho preciso, seleção do par, multiplexação L/R, independência de `SL`/`SR`, mouse e scroll simultâneos, `REL_WHEEL`/`REL_HWHEEL`, semântica `tap`/`hold`, ordem de acordes, dead zone, integração temporal, resíduos, limite de tick, JSONL do dry-run e liberação de saída em falhas.

## Fase 3

- reconexão com backoff e retomada do loop (entregue no primeiro incremento da Fase 3);
- seleção automática determinística;
- calibração/fallback explicitamente medidos;
- logging estruturado e métricas operacionais;
- testes prolongados e de desconexão física;
- empacotamento e permissões reproduzíveis para ARM64.
