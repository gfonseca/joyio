# JoyIO

Aplicação Python para localizar Joy-Cons pareados no Linux, conectar um controle e imprimir eventos normalizados com nomes estáveis do JoyIO.

## O que já funciona

- listar Joy-Cons L/R previamente pareados pelo BlueZ;
- selecionar um controle pelo lado (`left` ou `right`) ou endereço Bluetooth;
- solicitar a conexão quando o controle estiver desconectado;
- localizar o dispositivo evdev criado pelo driver `hid_nintendo`;
- traduzir todos os botões e eixos de Joy-Con L/R para nomes canônicos;
- imprimir transições de botões e valores normalizados dos eixos como JSONL puro;
- encerrar a leitura com `Ctrl+C` fechando o dispositivo corretamente;
- informar erros de Bluetooth, seleção, permissão e dispositivo por códigos de saída distintos.

O projeto está na **Fase 1**. Ainda não há mapeamento YAML nem emissão de teclado e mouse.

## Ambiente suportado nesta fase

- Linux ARM64/aarch64;
- Python 3.12 ou posterior;
- BlueZ com `bluetoothctl`;
- kernel com `CONFIG_HID_NINTENDO` e interface evdev;
- Joy-Con original esquerdo (`057e:2006`) ou direito (`057e:2007`), previamente pareado.

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

O campo `side` diferencia SL/SR quando os dois controles forem usados simultaneamente no futuro. Códigos evdev não reconhecidos são preservados como `unmapped:<código>` para não esconder lacunas do driver.

### 3. Ajuste o tempo de espera

Por padrão, `inspect` espera até oito segundos pelo evdev depois da conexão. Para controles que demoram mais:

```bash
.venv/bin/joyio inspect --device right --timeout 15
```

## Referência dos comandos

```text
joyio list
joyio inspect --device <left|right|endereço> [--timeout SEGUNDOS]
joyio --version
joyio --help
```

Códigos de saída:

- `0`: execução concluída;
- `2`: Joy-Con solicitado não encontrado ou seleção ambígua;
- `3`: falha de BlueZ/`bluetoothctl`;
- `4`: nó evdev ausente, inacessível ou desconectado.

## Permissões

Ler `/dev/input/event*` normalmente exige uma regra udev/ACL ou participação no grupo `input`. Para desenvolvimento, uma opção simples é adicionar o usuário ao grupo:

```bash
sudo usermod -aG input "$USER"
```

É necessário encerrar e iniciar a sessão depois. Esse grupo permite ler outros dispositivos de entrada, inclusive teclado, portanto é amplo demais para a instalação final. Antes de transformar o programa em serviço, crie uma regra udev específica para os Joy-Cons e conceda somente o acesso necessário.

O projeto fornece uma regra restrita aos IDs oficiais de Joy-Con L/R em `config/udev/70-joyio.rules`. Ambientes GNOME normalmente já aplicam `TAG+=uaccess` para joysticks da sessão ativa; instale a regra somente se esse acesso não estiver disponível.

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

Os testes unitários usam respostas BlueZ, eventos evdev simulados e catálogos anonimizados obtidos das capturas reais. Eles não precisam de Bluetooth, root ou controle físico.

## Limitações atuais

- somente Joy-Cons originais L/R, um por execução;
- pareamento feito manualmente;
- identificação Bluetooth pelo nome oficial do produto;
- drift/dead zone e redução da frequência dos analógicos serão tratados no motor de mapeamento;
- não há reconexão, YAML, `uinput`, mouse, teclado ou serviço `systemd`;
- desconexão física durante captura tem teste automatizado, mas ainda precisa de uma prova manual controlada.

Consulte [FASE_0.md](FASE_0.md) para o diagnóstico inicial e [FASE_1.md](FASE_1.md) para o contrato atual.
