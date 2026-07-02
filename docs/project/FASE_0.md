# Fase 0 — investigação e prova de viabilidade

Data do diagnóstico: 2026-07-01.

## Resultado

A abordagem é viável neste equipamento. O sistema tem Bluetooth ativo, suporte de kernel para Joy-Con e `uinput`, Python ARM64 e uma biblioteca Python compatível compilada com sucesso. A CLI lista dispositivos pareados, solicita conexão e possui um leitor de botões/eixos normalizados.

Durante o diagnóstico inicial nenhum Joy-Con estava pareado. Posteriormente, Joy-Con L e R originais foram pareados pelo GNOME e usados para concluir o checkpoint físico; os resultados estão registrados em `FASE_1.md`.

## Diagnóstico do ambiente

| Item | Resultado |
|---|---|
| Arquitetura | `aarch64`, 64 bits |
| Distribuição | Ubuntu 24.04.4 LTS |
| Kernel | `6.18.2-4-qcom` |
| Python | 3.12.3 |
| BlueZ | 5.72 |
| Serviço Bluetooth | ativo e habilitado |
| Adaptador | presente, ligado, papel central disponível |
| `CONFIG_HID_NINTENDO` | módulo disponível (`hid-nintendo.ko`) |
| `CONFIG_INPUT_UINPUT` | módulo disponível e carregado |
| `/dev/uinput` | presente |
| Bibliotecas Python | `evdev 1.9.3` compilado para CPython 3.12/aarch64 no `.venv` |
| Joy-Con pareado no diagnóstico inicial | nenhum |
| Validação posterior | Joy-Con L e R reconhecidos e lidos por evdev |
| Permissão evdev | acesso concedido à sessão local por `TAG+=uaccess` |

O kernel anuncia suporte aos IDs Bluetooth Nintendo `057e:2006` (Joy-Con L) e `057e:2007` (Joy-Con R). O módulo não aparece carregado enquanto nenhum controle compatível está conectado, comportamento esperado.

## Abordagens avaliadas

### A. Driver do kernel + evdev — recomendada

Fluxo: BlueZ conecta o controle, `hid_nintendo` cuida do protocolo/calibração, o kernel cria `/dev/input/event*` e `python-evdev` lê eventos.

Vantagens:

- usa suporte oficial já presente no kernel;
- reaproveita calibração e mapeamentos mantidos no kernel;
- evita manter o protocolo binário do Joy-Con no projeto;
- integra diretamente com a futura saída `uinput`;
- pacote `evdev` foi compilado com sucesso em ARM64.

Limitações:

- depende de um kernel com `HID_NINTENDO`;
- recursos avançados ficam limitados ao que o driver expõe;
- exige acesso aos nós evdev.

### B. HIDAPI/hidraw + parser próprio — fallback

Fluxo: BlueZ conecta, HIDAPI abre `/dev/hidraw*`, e o projeto envia subcomandos e interpreta relatórios Nintendo.

Vantagens:

- controle direto do protocolo;
- pode viabilizar recursos futuros não expostos por evdev.

Custos e riscos:

- precisa implementar inicialização, calibração, parsing e recuperação de falhas;
- `/dev/hidraw*` no ambiente está restrito a root;
- pode disputar o dispositivo com `hid_nintendo`;
- aumenta significativamente a superfície de testes;
- o backend libusb do HIDAPI não atende Bluetooth; no Linux teria de ser usado o backend hidraw.

Decisão detalhada: [ADR 0001](../adr/0001-usar-hid-nintendo-e-evdev.md).

## Dependências

### Sistema

- BlueZ/`bluetoothctl`: enumeração, estado e conexão;
- `hid_nintendo`: driver e normalização inicial do hardware;
- evdev do kernel: leitura dos eventos;
- `uinput`: confirmado agora, mas só será usado na Fase 2.

### `.venv`

- `evdev==1.9.3`: leitura evdev; também servirá para `uinput` depois;
- `pytest==9.1.1`: testes automatizados.

Não foi adicionada uma biblioteca YAML nesta fase porque ainda não há configuração de mapeamento.

## Prova de conceito entregue

Estrutura relevante:

```text
src/joyio/bluetooth.py  # fronteira bluetoothctl/BlueZ
src/joyio/devices.py    # localização e leitura evdev
src/joyio/events.py     # eventos normalizados
src/joyio/cli.py        # comandos list e inspect
tests/                  # simulações sem hardware
```

Comandos:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pip install --no-deps -e .
.venv/bin/pytest
.venv/bin/joyio list
.venv/bin/joyio inspect --device right
```

## Validação executada

### Automatizada

- 18 testes passaram;
- parsing de dispositivos pareados e identificação L/R;
- conexão omitida quando já conectado e solicitada quando desconectado;
- falha de BlueZ convertida em erro acionável;
- normalização dos extremos e centro dos eixos;
- eventos de pressionar/soltar botão;
- CLI sem controle e seleção inválida.

### Integração local

- o `.venv` foi criado e o projeto instalado em modo editável;
- `evdev` foi compilado nativamente para aarch64;
- `joyio list` consultou o BlueZ real e informou corretamente que não existe Joy-Con pareado;
- `joyio inspect --device right` retornou código `2` e orientação para executar `joyio list`;
- módulos e nós de kernel foram inspecionados no sistema real.

### Checkpoint de hardware concluído posteriormente

- Joy-Con L e R originais pareados e apresentados por `joyio list`;
- `hid_nintendo` carregado e dispositivos evdev criados;
- botões e eixos de ambos os lados capturados;
- `Ctrl+C` confirmado com fechamento limpo;
- catálogos anonimizados registrados em `tests/fixtures/`;
- desconexão tratada e testada automaticamente; prova manual controlada permanece para robustez.

## Riscos confirmados

1. O acesso atual depende da ACL de sessão (`uaccess`); um serviço de sistema precisará de outra política explícita.
2. A Fase 0 identifica dispositivos BlueZ pelo nome oficial; clones ficam fora do escopo.
3. O uso de `bluetoothctl` é adequado à prova, mas uma integração D-Bus será mais robusta para serviço e reconexão.
4. Ambientes isolados podem bloquear D-Bus e `/dev`; diagnósticos de hardware precisam executar com acesso ao host.

## Ajuste proposto para a Fase 1

Antes de ampliar o código, concluir o checkpoint físico acima. Em seguida:

1. criar nomes canônicos JoyIO para todos os botões/eixos de L e R, desacoplando-os dos nomes `BTN_*`/`ABS_*`;
2. capturar fixtures reais e parametrizar testes por lado;
3. separar metadados de descoberta dos handles abertos de dispositivo;
4. tratar desconexão e fechamento com testes de falha;
5. definir uma regra udev restrita ao Joy-Con, evitando depender do grupo `input` no produto final;
6. avaliar D-Bus direto para substituir parsing textual de `bluetoothctl`;
7. adicionar logging estruturado e `--verbose`;
8. manter YAML e `uinput` fora da Fase 1; eles entram na Fase 2.

## Referências

- [Driver hid-nintendo do kernel Linux](https://github.com/torvalds/linux/blob/master/drivers/hid/hid-nintendo.c)
- [Configuração HID_NINTENDO do kernel](https://github.com/torvalds/linux/blob/master/drivers/hid/Kconfig)
- [Documentação do python-evdev](https://python-evdev.readthedocs.io/en/stable/)
- [Documentação de uinput do kernel](https://docs.kernel.org/input/uinput.html)
- [API Device1 do BlueZ](https://github.com/bluez/bluez/blob/master/doc/org.bluez.Device.rst)
- [HIDAPI oficial](https://github.com/libusb/hidapi)
