# JoyIO

Aplicação Python para usar um par de Joy-Cons como um único teclado e mouse virtual no Linux, com mapeamento YAML e suporte independente de X11/Wayland por `uinput`.

## O que já funciona

- listar Joy-Cons L/R previamente pareados pelo BlueZ;
- selecionar cada controle pelo lado ou por seu endereço Bluetooth;
- conectar os Joy-Cons L e R e consumir seus eventos simultaneamente;
- localizar o dispositivo evdev criado pelo driver `hid_nintendo`;
- traduzir todos os botões e eixos de Joy-Con L/R para nomes canônicos;
- imprimir transições de botões e valores normalizados dos eixos como JSONL puro;
- validar configurações YAML versionadas antes de conectar o controle;
- mapear botões para teclas, combinações e botões do mouse nos modos `tap` e `hold`;
- mover o ponteiro com um analógico e produzir scroll horizontal/vertical com o outro, cada um com dead zone, sensibilidade, curva, inversão e velocidade máxima;
- executar em `--dry-run`, imprimindo as ações resultantes como JSONL;
- emitir teclado e mouse virtual pelo subsistema Linux `uinput`;
- liberar teclas e botões virtuais mantidos ao encerrar ou desconectar;
- encerrar a leitura com `Ctrl+C` fechando o dispositivo corretamente;
- informar erros de Bluetooth, seleção, permissão e dispositivo por códigos de saída distintos.

O projeto está na **Fase 2**. Reconexão automática, seleção `--auto` e serviço `systemd` ainda não fazem parte desta fase.

## Ambiente suportado nesta fase

- Linux ARM64/aarch64;
- Python 3.12 ou posterior;
- BlueZ com `bluetoothctl`;
- kernel com `CONFIG_HID_NINTENDO` e interface evdev;
- um Joy-Con original esquerdo (`057e:2006`) e um direito (`057e:2007`), previamente pareados.

## Instalação no ambiente virtual

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pip install --no-deps -e .
```

Todo pacote Python do projeto deve ser instalado em `.venv`. BlueZ, módulos do kernel e regras de dispositivo são dependências do sistema e não podem ser instalados no ambiente virtual.

Confirme a instalação:

```bash
.venv/bin/joyio --version
.venv/bin/joyio --help
```

Não é necessário ativar o ambiente virtual. Os exemplos usam os executáveis dentro de `.venv` explicitamente para evitar executar outro Python por engano.

## Pareamento atual

O programa ainda não gerencia o pareamento. Inicie `bluetoothctl`, mantenha pressionado o botão de sincronização do Joy-Con até os LEDs correrem e use:

```text
power on
agent on
default-agent
pairable on
scan on
pair AA:BB:CC:DD:EE:FF
trust AA:BB:CC:DD:EE:FF
connect AA:BB:CC:DD:EE:FF
scan off
quit
```

Substitua o endereço pelo que aparecer como `Joy-Con (L)` ou `Joy-Con (R)`. `pair`, `trust` e `connect` são estados/operações diferentes no BlueZ.

## Uso rápido

### 1. Liste os Joy-Cons pareados

```bash
.venv/bin/joyio list
```

Quando houver controles pareados, a saída contém endereço, lado e nome:

```text
AA:BB:CC:DD:EE:01    left     Joy-Con (L)
AA:BB:CC:DD:EE:02    right    Joy-Con (R)
```

Se nenhum Joy-Con for encontrado, o comando termina normalmente e explica como iniciar o pareamento manual. Outros dispositivos Bluetooth são ignorados.

### 2. Inspecione um controle

Selecione por lado:

```bash
.venv/bin/joyio inspect --device right
.venv/bin/joyio inspect --device left
```

Ou use o endereço mostrado por `list`:

```bash
.venv/bin/joyio inspect --device AA:BB:CC:DD:EE:FF
```

Usar o endereço remove ambiguidades quando há mais de um Joy-Con do mesmo lado pareado. O comando:

1. confirma que o Joy-Con está pareado;
2. solicita a conexão Bluetooth, se necessária;
3. espera o nó evdev aparecer;
4. imprime um objeto JSON para cada evento de botão ou eixo em `stdout`.

Mensagens de conexão e diagnóstico são escritas em `stderr`. Portanto, este comando cria um arquivo JSONL válido sem misturar cabeçalhos textuais:

```bash
.venv/bin/joyio inspect --device right > out-right.jsonl
```

Exemplo de saída:

```json
{"code": 305, "control": "a", "kind": "button", "side": "right", "source_control": "BTN_EAST", "state": "pressed", "timestamp": 1751391000.25, "value": 1.0}
{"code": 305, "control": "a", "kind": "button", "side": "right", "source_control": "BTN_EAST", "state": "released", "timestamp": 1751391000.34, "value": 0.0}
{"code": 3, "control": "right_stick_x", "kind": "axis", "side": "right", "source_control": "ABS_RX", "state": null, "timestamp": 1751391001.12, "value": 0.72}
```

Campos dos eventos:

- `kind`: `button` ou `axis`;
- `control`: nome canônico e estável do JoyIO;
- `source_control`: código evdev apresentado pelo kernel, mantido para diagnóstico;
- `side`: `left` ou `right`;
- `code`: valor numérico desse código;
- `state`: `pressed`, `released` ou `repeat` para botões; `null` para eixos;
- `value`: estado numérico do botão ou eixo normalizado entre `-1.0` e `1.0`;
- `timestamp`: instante do evento informado pelo kernel.

Pressione `Ctrl+C` para encerrar.

## Controles canônicos

Joy-Con L:

| Controle físico | Nome JoyIO |
|---|---|
| Analógico | `left_stick_x`, `left_stick_y` |
| Clique do analógico | `left_stick_press` |
| Direcional | `dpad_up`, `dpad_down`, `dpad_left`, `dpad_right` |
| L / ZL | `l`, `zl` |
| SL / SR | `sl`, `sr` |
| Menos / Capture | `minus`, `capture` |

Joy-Con R:

| Controle físico | Nome JoyIO |
|---|---|
| Analógico | `right_stick_x`, `right_stick_y` |
| Clique do analógico | `right_stick_press` |
| A / B / X / Y | `a`, `b`, `x`, `y` |
| R / ZR | `r`, `zr` |
| SL / SR | `sl`, `sr` |
| Mais / Home | `plus`, `home` |

O campo `side` diferencia SL/SR dos dois controles. No YAML, os mapeamentos ficam separados em `mappings.buttons.left` e `mappings.buttons.right`. Códigos evdev não reconhecidos são preservados como `unmapped:<código>` para não esconder lacunas do driver.

### 3. Ajuste o tempo de espera

Por padrão, `inspect` espera até oito segundos pelo evdev depois da conexão. Para controles que demoram mais:

```bash
.venv/bin/joyio inspect --device right --timeout 15
```

## Mapeamento de teclado e mouse

O arquivo [`config.example.yaml`](config.example.yaml) é um perfil executável para o par Joy-Con L/R. Valide-o sem acessar Bluetooth ou dispositivos de entrada:

```bash
.venv/bin/joyio validate-config config.example.yaml
```

Teste o pipeline completo sem criar um dispositivo virtual:

```bash
.venv/bin/joyio run --config config.example.yaml --dry-run
```

Cada ação aparece em JSONL. Por exemplo, pressionar e soltar `A` com o perfil de exemplo produz:

```json
{"button": "right", "pressed": true, "type": "mouse_button"}
{"button": "right", "pressed": false, "type": "mouse_button"}
```

Depois do dry-run, execute com saída real:

```bash
.venv/bin/joyio run --config config.example.yaml
```

O perfil de exemplo cobre todos os botões. O analógico esquerdo move o ponteiro e o direito controla scroll horizontal/vertical. No Joy-Con L, `ZL` segura o clique esquerdo e `L` o direito; no Joy-Con R, `ZR` segura o clique direito e `R` o esquerdo. Assim, cada lado possui os dois cliques com uma convenção espacial. Os demais botões produzem teclas, acordes ou clique central. Os `SL`/`SR` de cada lado possuem ações diferentes, permitindo confirmar que os dois Joy-Cons estão sendo processados independentemente.

Por padrão, `run` seleciona exatamente um Joy-Con pareado de cada lado. Se houver mais de um do mesmo lado, fixe os endereços em `devices.left.address` e `devices.right.address`, ou use `--left-device` e `--right-device`. O comando falha em vez de escolher ambiguamente.

### Schema YAML v1

- campos desconhecidos são erros;
- teclas devem usar nomes Linux `KEY_*` existentes;
- os botões são separados por lado em `mappings.buttons.left` e `mappings.buttons.right`;
- controles inexistentes no lado declarado são erros;
- `tap` envia pressão e liberação ao pressionar o botão físico;
- `hold` preserva as transições físicas de pressão e liberação;
- `sensitivity` e `max_speed` são medidas em pixels por segundo;
- `scroll.sensitivity` e `scroll.max_speed` são passos de roda por segundo;
- ponteiro e scroll são atualizados a 120 Hz, integrados por tempo e mantêm resíduos fracionários independentes;
- configurações inválidas nunca são aplicadas parcialmente.

Use o exemplo como referência dos campos implementados. Opções de reconexão ainda não entram no YAML porque pertencem à Fase 3.

## Referência dos comandos

```text
joyio list
joyio inspect --device <left|right|endereço> [--timeout SEGUNDOS]
joyio validate-config <arquivo.yaml>
joyio run [--left-device <endereço>] [--right-device <endereço>] --config <arquivo.yaml> [--dry-run]
joyio --version
joyio --help
```

Códigos de saída:

- `0`: execução concluída;
- `2`: Joy-Con solicitado não encontrado ou seleção ambígua;
- `3`: falha de BlueZ/`bluetoothctl`;
- `4`: nó evdev ausente, inacessível ou desconectado;
- `5`: configuração YAML inválida;
- `6`: não foi possível criar ou usar a saída `uinput`.

## Permissões

Ler `/dev/input/event*` normalmente exige uma regra udev/ACL ou participação no grupo `input`. Para desenvolvimento, uma opção simples é adicionar o usuário ao grupo:

```bash
sudo usermod -aG input "$USER"
```

É necessário encerrar e iniciar a sessão depois. Esse grupo permite ler outros dispositivos de entrada, inclusive teclado, portanto é amplo demais para a instalação final. Antes de transformar o programa em serviço, crie uma regra udev específica para os Joy-Cons e conceda somente o acesso necessário.

O projeto fornece uma regra restrita aos IDs oficiais de Joy-Con L/R em `config/udev/70-joyio.rules`. Ambientes GNOME normalmente já aplicam `TAG+=uaccess` para joysticks da sessão ativa; instale a regra somente se esse acesso não estiver disponível.

A emissão real também exige acesso de escrita a `/dev/uinput`. Confirme com:

```bash
ls -l /dev/uinput
```

O modo `--dry-run` não requer essa permissão. Na sessão desktop atual, ACLs podem já conceder o acesso. A política definitiva de instalação será fechada junto ao empacotamento; não execute todo o programa como root apenas para contornar uma permissão ausente.

Confirme a participação no grupo depois de entrar novamente:

```bash
id
```

## Solução de problemas

### “Nenhum Joy-Con previamente pareado foi encontrado”

O programa somente conecta controles já pareados. Repita o procedimento em `bluetoothctl`, confirme que o nome é `Joy-Con (L)` ou `Joy-Con (R)` e execute `joyio list` novamente.

### “nenhum Joy-Con pareado corresponde a 'right'”

Não existe um controle desse lado ou o nome anunciado não foi reconhecido. Execute `joyio list` e tente selecionar pelo endereço.

### “sem permissão” ou “nenhum dispositivo de entrada acessível”

O usuário não consegue abrir `/dev/input/event*`. Ajuste a permissão conforme a seção anterior e inicie uma nova sessão.

### “nenhum evdev compatível apareceu”

Confirme que o driver está disponível e verifique mensagens do kernel:

```bash
modinfo hid_nintendo
dmesg | tail -n 50
```

Também é possível aumentar `--timeout`. Se o Joy-Con aparece no BlueZ, mas não no evdev, o problema está entre a conexão HID, o driver do kernel e as permissões, não no parser de eventos.

### Falha ou timeout do `bluetoothctl`

Verifique se o serviço e o adaptador estão ativos:

```bash
systemctl status bluetooth
bluetoothctl show
```

## Testes

```bash
.venv/bin/pytest
```

Para validar somente o perfil completo, atravessando YAML, motor de mapeamento e saída JSONL:

```bash
.venv/bin/pytest -q tests/test_functional_profile.py
```

O teste funcional sintetiza pressão e liberação de todos os 22 botões configurados, movimento do mouse e scroll nos dois eixos. Os testes usam respostas BlueZ, eventos evdev simulados, configurações temporárias e catálogos anonimizados obtidos das capturas reais. Eles não precisam de Bluetooth, root, `uinput` ou controle físico.

## Limitações atuais

- somente Joy-Cons originais, um L e um R por execução;
- pareamento feito manualmente;
- identificação Bluetooth pelo nome oficial do produto;
- não há reconexão automática, seleção `--auto`, hot reload ou serviço `systemd`;
- a calibração usada nesta fase é a fornecida pelo driver `hid_nintendo`/evdev;
- desconexão física durante captura tem teste automatizado, mas ainda precisa de uma prova manual controlada.

Consulte [FASE_0.md](FASE_0.md), [FASE_1.md](FASE_1.md) e [FASE_2.md](FASE_2.md) para o histórico e os contratos de cada etapa.
