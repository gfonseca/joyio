# Revisão de performance

Data: 2026-07-02. Ambiente medido: Linux ARM64, Python 3.12.3 e `python-evdev` 1.9.3.

## Caminho crítico

O caminho de produção permanece síncrono e orientado a eventos:

```text
select(2 fds) -> evdev.read() em lote -> normalização -> mapping -> uinput
```

Com apenas dois descritores, `select.select` é menor e mais direto que introduzir threads ou um event loop assíncrono. `InputDevice.read()` já chama `device_read_many` na extensão C do `python-evdev`, portanto não há ganho em implementar buffering Python adicional.

## Parâmetros mantidos

- Taxa de saída: 120 Hz, ou 8,33 ms entre atualizações. A leitura real em repouso consumiu aproximadamente 0,8–1,1% de um núcleo; reduzir para 60 Hz aumentaria a latência sem economia relevante.
- `uinput.max_effects`: 0, pois o dispositivo virtual não oferece force feedback.
- Leitura: bloqueante via `select`, sem polling ativo.
- YAML: `PyYAML` está usando a extensão C `LibYAML`; a configuração é carregada uma vez por sessão supervisionada.
- Backoff: fora do caminho crítico de eventos; não afeta CPU durante uma sessão conectada.

## Calibração observada

O `hid_nintendo` expôs os dois analógicos com:

```text
min=-32767 max=32767 fuzz=250 flat=500 resolution=0
```

Normalizados, `fuzz` equivale a aproximadamente `0,0076` e `flat` a `0,0153`. Em cinco segundos de repouso, o maior ruído repetido observado foi `0,0723` no eixo X esquerdo.

Por isso, os valores atuais são adequados:

- mouse `dead_zone: 0.12`: margem de aproximadamente 66% sobre o ruído medido, preservando movimento fino;
- scroll `dead_zone: 0.18`: mais conservador para impedir passos involuntários;
- mouse a 600 px/s, curva 1,3 e teto 1800 px/s;
- scroll a 18 passos/s, curva 1,3 e teto 30 passos/s.

Sensibilidade e aceleração alteram a resposta, não o custo computacional de forma material.

## Otimizações aplicadas

- `AbsInfo` é armazenado uma vez por dispositivo/eixo. A consulta é um `ioctl`; antes ocorria em toda amostra analógica.
- Nomes evdev e estados digitais usam estruturas estáticas/cacheadas.
- O motor executa no máximo 120 ticks/s mesmo durante rajadas de eventos.
- Curva, magnitude e velocidade analógica são recalculadas somente quando um eixo muda.
- Chamadas vazias ao backend foram eliminadas.
- Movimento e scroll do mesmo tick compartilham um único `SYN_REPORT`.
- Códigos `KEY_*` são resolvidos uma vez na criação do backend.
- JSONL de diagnóstico evita `dataclasses.asdict` e cópias profundas.
- A lista fixa de descritores para `select` é criada uma vez por sessão.

## Resultados sintéticos

- Pipeline do motor: aproximadamente 329 mil para 645 mil iterações/s no ARM64, cerca de 96% de ganho no cenário medido.
- Serialização de ação JSONL: ganho de aproximadamente 1,37x.
- Rajada simulada de 100 eventos em 100 ms: cerca de 10 cálculos temporais, em vez de 100.
- Mouse + scroll: um `SYN_REPORT` por tick, em vez de dois.

`--dry-run` inclui serialização e flush de JSON a cada ação e não representa o custo do backend `uinput` usado em produção.
