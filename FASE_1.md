# Fase 1 — captura canônica de entrada

Data: 2026-07-01.

## Resultado

O pipeline de entrada está funcional com Joy-Con L e R originais em Linux ARM64. BlueZ conecta os controles, `hid_nintendo` expõe evdev e o JoyIO converte códigos Linux em nomes próprios estáveis.

## Contrato de evento

Cada linha emitida por `joyio inspect` é um objeto JSON independente:

```json
{"code":305,"control":"a","kind":"button","side":"right","source_control":"BTN_EAST","state":"pressed","timestamp":1751391000.25,"value":1.0}
```

- `control`: nome canônico usado futuramente pelo YAML;
- `source_control`: nome evdev para diagnóstico;
- `side`: origem física do evento;
- `kind`: `button` ou `axis`;
- `state`: transição de botão;
- `value`: `0/1` para botão ou eixo em `[-1, 1]`;
- `timestamp`: tempo fornecido pelo kernel.

Mensagens operacionais são enviadas para `stderr`; `stdout` contém somente JSONL.

## Cobertura de controles

Joy-Con L:

```text
left_stick_x, left_stick_y, left_stick_press
dpad_up, dpad_down, dpad_left, dpad_right
l, zl, sl, sr, minus, capture
```

Joy-Con R:

```text
right_stick_x, right_stick_y, right_stick_press
a, b, x, y
r, zr, sl, sr, plus, home
```

O driver usa códigos de ombro do lado oposto para SL/SR. Essa particularidade fica confinada em `controls.py`; consumidores recebem somente `sl` e `sr`.

## Evidência de hardware

- os dois dispositivos aparecem simultaneamente em `joyio list`;
- Joy-Con L expôs todos os 11 botões e 2 eixos esperados;
- Joy-Con R expôs todos os 11 botões e 2 eixos esperados;
- a captura do L observou todos os controles físicos;
- a captura do R observou analógico, clique, A/B/X/Y, R/ZR, Mais e Home;
- as capacidades do R anunciam SL/SR, embora eles ainda não tenham aparecido em uma captura salva;
- nenhum controle anunciado por evdev ficou sem mapeamento canônico;
- encerramento por `SIGINT` fechou o leitor de forma limpa.

As capturas completas permanecem locais e ignoradas pelo Git porque contêm endereços Bluetooth. Os catálogos em `tests/fixtures/` removem endereço e timestamp, preservando somente o contrato observado.

## Testes

```text
26 passed
```

A suíte cobre:

- contratos completos L/R;
- fixtures anonimizadas de hardware;
- normalização e limites de eixo;
- transições `pressed`/`released`;
- marcação explícita de códigos desconhecidos;
- fechamento do handle no fim normal e após desconexão;
- separação de JSONL em `stdout` e diagnóstico em `stderr`;
- comportamento de BlueZ e seleção da CLI.

## Permissões

O host atual já marca os dispositivos com `TAG+=uaccess`. Para ambientes que não façam isso, `config/udev/70-joyio.rules` limita a concessão aos produtos Nintendo `057e:2006` e `057e:2007`.

## Pendências antes da Fase 2

- executar uma desconexão física controlada durante `inspect`;
- capturar SL/SR do Joy-Con R ou documentar a condição física necessária;
- decidir se a fronteira BlueZ migra de `bluetoothctl` para D-Bus agora ou na fase de reconexão;
- adicionar logging configurável se o diagnóstico atual em `stderr` se mostrar insuficiente.

Dead zone e spam de analógico não pertencem ao leitor. Serão tratados no motor de mapeamento da Fase 2, mantendo o evento normalizado fiel ao hardware.
