# JoyIO

Use um par de Joy-Cons como teclado e mouse no Linux.

O JoyIO conecta o controle esquerdo e o direito como uma única interface: um analógico move o ponteiro, o outro controla o scroll, e cada botão pode executar teclas, atalhos ou cliques configurados em YAML. Funciona em X11 e Wayland por meio de um dispositivo virtual do Linux.

> Projeto em desenvolvimento para Linux ARM64. O uso pelo terminal já está funcional; instalação como serviço e interface gráfica ainda estão no roadmap.

## Destaques

- Joy-Con L e R trabalhando juntos;
- ponteiro, scroll vertical e scroll horizontal;
- cliques esquerdo, direito e central;
- teclas simples e atalhos como `Ctrl+C` e `Ctrl+V`;
- perfil totalmente personalizável em YAML;
- modo de teste que não interfere no teclado ou mouse reais;
- reconexão automática quando o par fica disponível novamente;
- baixo consumo no ARM64, com atualização a 120 Hz.

## Requisitos

- Linux ARM64/aarch64;
- Python 3.12 ou mais recente;
- BlueZ/Bluetooth ativo;
- um Joy-Con original esquerdo e um direito;
- driver `hid_nintendo` do kernel.

O pareamento pode ser feito normalmente nas configurações de Bluetooth do GNOME. O JoyIO não substitui a tela de pareamento; ele conecta e utiliza controles que já foram pareados.

## Instalação

Na pasta do projeto, crie o ambiente virtual e instale as dependências:

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
```

Confirme a instalação:

```bash
.venv/bin/joyio --version
.venv/bin/joyio --help
```

Os exemplos usam `.venv/bin/joyio` diretamente, portanto não é necessário ativar o ambiente virtual.

## Primeiros passos

### 1. Pareie os dois Joy-Cons

Abra **Configurações → Bluetooth** no GNOME. Em cada Joy-Con, mantenha pressionado o pequeno botão de sincronização até os LEDs começarem a correr e conclua o pareamento.

Se preferir o terminal, use `bluetoothctl`:

```text
power on
agent on
default-agent
scan on
pair AA:BB:CC:DD:EE:FF
trust AA:BB:CC:DD:EE:FF
connect AA:BB:CC:DD:EE:FF
scan off
quit
```

Repita para `Joy-Con (L)` e `Joy-Con (R)`.

### 2. Confirme que o JoyIO encontrou o par

```bash
.venv/bin/joyio list
```

Exemplo:

```text
AA:BB:CC:DD:EE:01    left     Joy-Con (L)
AA:BB:CC:DD:EE:02    right    Joy-Con (R)
```

### 3. Valide o perfil

```bash
.venv/bin/joyio validate-config config.example.yaml
```

### 4. Faça um teste seguro

O `--dry-run` conecta os controles e mostra as ações no terminal, sem criar um teclado ou mouse virtual:

```bash
.venv/bin/joyio run --config config.example.yaml --dry-run
```

Mova os analógicos e pressione os botões. Encerre com `Ctrl+C`.

### 5. Use como teclado e mouse

```bash
.venv/bin/joyio run --config config.example.yaml
```

Enquanto o comando estiver em execução, os aplicativos enxergarão o JoyIO como um teclado e mouse comuns.

## Controles do perfil padrão

O arquivo [config.example.yaml](config.example.yaml) cobre todos os botões dos dois Joy-Cons.

### Joy-Con esquerdo

| Controle | Ação padrão |
|---|---|
| Analógico | Move o ponteiro |
| Direcional | Setas do teclado |
| ZL | Clique esquerdo |
| L | Clique direito |
| Clique do analógico | Espaço |
| Menos | Tab |
| Capture | F12 |
| SL / SR | F5 / F6 |

### Joy-Con direito

| Controle | Ação padrão |
|---|---|
| Analógico | Scroll horizontal e vertical |
| ZR | Clique direito |
| R | Clique esquerdo |
| A | Clique direito |
| B | Esc |
| X | Ctrl+C |
| Y | Ctrl+V |
| Mais | Enter |
| Clique do analógico | Clique central |
| Home | Home |
| SL / SR | F7 / F8 |

## Personalizando os controles

Comece copiando o perfil de exemplo:

```bash
cp config.example.yaml config.yaml
```

Depois execute o JoyIO com o novo arquivo:

```bash
.venv/bin/joyio run --config config.yaml
```

### Ponteiro e scroll

```yaml
mouse:
  stick: left_stick
  dead_zone: 0.12
  sensitivity: 600.0
  acceleration: 1.3
  max_speed: 1800.0
  invert_x: false
  invert_y: false

scroll:
  stick: right_stick
  dead_zone: 0.18
  sensitivity: 18.0
  acceleration: 1.3
  max_speed: 30.0
  invert_x: false
  invert_y: true
```

- `runtime.enabled` define o estado inicial do mapping. Use `true` para desktop e `false` para iniciar desligado.
- `dead_zone` ignora pequenos movimentos e drift;
- `sensitivity` define a velocidade principal;
- `acceleration` controla a curva de resposta;
- `max_speed` limita a velocidade máxima;
- `invert_x` e `invert_y` invertem a direção.

Os valores do perfil padrão foram medidos nos Joy-Cons usados durante o desenvolvimento e são um bom ponto de partida.

### Teclas e cliques

Uma tecla simples:

```yaml
mappings:
  buttons:
    left:
      minus:
        type: key
        key: KEY_TAB
        mode: tap
```

Um atalho:

```yaml
mappings:
  buttons:
    right:
      x:
        type: key_chord
        keys: [KEY_LEFTCTRL, KEY_C]
        mode: tap
```

Um botão do mouse:

```yaml
mappings:
  buttons:
    right:
      zr:
        type: mouse_button
        button: right
        mode: hold
```

Use `tap` para enviar uma ação completa ao pressionar o botão. Use `hold` quando a ação deve permanecer pressionada até soltar o botão físico.

Para alternar entre mapping ligado e desligado, use `type: toggle` em um botão que continue acessível enquanto o Joy-Con estiver pareado. O exemplo padrão usa `left.capture`:

```yaml
mappings:
  buttons:
    left:
      capture:
        type: toggle
```

Quando o mapping é desligado, o JoyIO libera imediatamente as teclas e cliques virtuais mantidos e continua observando os Joy-Cons para que o toggle possa ser acionado de novo.

Sempre valide depois de editar:

```bash
.venv/bin/joyio validate-config config.yaml
```

## Referência para criar seu próprio perfil

### Nomes dos controles Joy-Con

Use estes identificadores dentro de `mappings.buttons.left` e `mappings.buttons.right`.

Joy-Con esquerdo:

| Controle físico | Identificador YAML |
|---|---|
| Direcional para cima | `dpad_up` |
| Direcional para baixo | `dpad_down` |
| Direcional para esquerda | `dpad_left` |
| Direcional para direita | `dpad_right` |
| L | `l` |
| ZL | `zl` |
| Menos | `minus` |
| Clique do analógico | `left_stick_press` |
| Capture | `capture` |
| SL | `sl` |
| SR | `sr` |

Joy-Con direito:

| Controle físico | Identificador YAML |
|---|---|
| A | `a` |
| B | `b` |
| X | `x` |
| Y | `y` |
| R | `r` |
| ZR | `zr` |
| Mais | `plus` |
| Clique do analógico | `right_stick_press` |
| Home | `home` |
| SL | `sl` |
| SR | `sr` |

Para `mouse.stick` e `scroll.stick`, os valores aceitos são `left_stick` e `right_stick`. Nos eventos de diagnóstico, os eixos aparecem como `left_stick_x`, `left_stick_y`, `right_stick_x` e `right_stick_y`.

Se quiser confirmar o nome emitido pelo seu controle, execute `inspect` e pressione o botão desejado:

```bash
.venv/bin/joyio inspect --device left
.venv/bin/joyio inspect --device right
```

O campo `control` da saída mostra o identificador usado pelo JoyIO.

### Códigos de teclado

O JoyIO usa os nomes de teclas do subsistema de entrada do Linux. Eles começam com `KEY_` e são escritos em inglês e letras maiúsculas.

Alguns códigos comuns:

| Tecla | Código |
|---|---|
| Letras | `KEY_A` até `KEY_Z` |
| Números | `KEY_0` até `KEY_9` |
| Enter | `KEY_ENTER` |
| Escape | `KEY_ESC` |
| Espaço | `KEY_SPACE` |
| Tab | `KEY_TAB` |
| Backspace | `KEY_BACKSPACE` |
| Delete | `KEY_DELETE` |
| Setas | `KEY_UP`, `KEY_DOWN`, `KEY_LEFT`, `KEY_RIGHT` |
| Home / End | `KEY_HOME`, `KEY_END` |
| Page Up / Page Down | `KEY_PAGEUP`, `KEY_PAGEDOWN` |
| Ctrl | `KEY_LEFTCTRL`, `KEY_RIGHTCTRL` |
| Shift | `KEY_LEFTSHIFT`, `KEY_RIGHTSHIFT` |
| Alt | `KEY_LEFTALT`, `KEY_RIGHTALT` |
| Windows / Super | `KEY_LEFTMETA`, `KEY_RIGHTMETA` |
| Teclas de função | `KEY_F1` até `KEY_F24` |
| Volume | `KEY_VOLUMEUP`, `KEY_VOLUMEDOWN`, `KEY_MUTE` |
| Mídia | `KEY_PLAYPAUSE`, `KEY_NEXTSONG`, `KEY_PREVIOUSSONG` |

Para consultar a lista completa disponível na versão instalada do `python-evdev`:

```bash
.venv/bin/python -c 'from evdev import ecodes; print("\n".join(sorted({name for value in ecodes.keys.values() for name in ((value,) if isinstance(value, str) else value) if name.startswith("KEY_")})))'
```

Essa lista vem diretamente dos códigos suportados pelo kernel e pela biblioteca no computador. O comando `validate-config` informa se algum nome digitado não é reconhecido.

### Botões do mouse

Para um mapeamento com `type: mouse_button`, os valores aceitos em `button` são:

| Valor | Ação |
|---|---|
| `left` | Clique esquerdo |
| `right` | Clique direito |
| `middle` | Clique central |

## Seleção dos controles e reconexão

Quando existe exatamente um Joy-Con de cada lado pareado, o JoyIO seleciona o par automaticamente. Se houver mais de um controle do mesmo lado, informe os endereços no YAML ou pela linha de comando:

```bash
.venv/bin/joyio run \
  --left-device AA:BB:CC:DD:EE:01 \
  --right-device AA:BB:CC:DD:EE:02 \
  --config config.yaml
```

A reconexão é configurada no perfil:

```yaml
reconnect:
  enabled: true
  initial_delay: 1.0
  max_delay: 30.0
  multiplier: 2.0
  max_attempts: null
```

`max_attempts: null` mantém as tentativas ativas em cada lado. Use `--no-reconnect` quando quiser encerrar na primeira falha.

Cada lado é acompanhado separadamente. Se um Joy-Con cair, o outro continua funcionando; quando o nó `evdev` reaparece, ele é incorporado à mesma sessão sem recriar o teclado/mouse virtual. Somente teclas e cliques originados pelo lado desconectado são liberados.

Um Joy-Con adormecido pode precisar de um toque em qualquer botão para voltar a responder. Os estados `connecting`, `bluetooth_ready`, `evdev_ready`, `active` e `offline` aparecem em `stderr` para diagnóstico.

## Comandos úteis

| Comando | Uso |
|---|---|
| `joyio list` | Lista Joy-Cons pareados |
| `joyio validate-config ARQUIVO` | Valida um perfil YAML |
| `joyio run --config ARQUIVO` | Inicia teclado e mouse virtual |
| `joyio run --config ARQUIVO --dry-run` | Testa sem gerar entradas reais |
| `joyio inspect --device left` | Mostra eventos do Joy-Con L |
| `joyio inspect --device right` | Mostra eventos do Joy-Con R |
| `joyio --version` | Mostra a versão instalada |

## Permissões

O JoyIO precisa ler os dispositivos em `/dev/input` e escrever em `/dev/uinput`. Em sessões GNOME, as permissões de leitura normalmente são concedidas automaticamente ao usuário ativo.

Confira a saída virtual:

```bash
ls -l /dev/uinput
```

Se os dispositivos de entrada não estiverem acessíveis, o projeto fornece a regra específica [config/udev/70-joyio.rules](config/udev/70-joyio.rules). Evite executar todo o programa como root apenas para contornar permissões.

O modo `--dry-run` não precisa acessar `/dev/uinput` e é o melhor primeiro diagnóstico.

## Solução de problemas

### Os LEDs ficam correndo e o controle não conecta

Pressione um botão para acordar o Joy-Con e aguarde a próxima tentativa indicada em `stderr`. Confirme também que ele aparece como pareado em `joyio list`. O outro lado deve continuar operacional durante a espera.

### Nenhum Joy-Con aparece em `joyio list`

Refaça o pareamento pelo GNOME ou `bluetoothctl`. Os nomes esperados são `Joy-Con (L)` e `Joy-Con (R)`.

### “Nenhum evdev compatível apareceu”

Confirme que o driver está disponível:

```bash
modinfo hid_nintendo
```

Você também pode aumentar o tempo de espera:

```bash
.venv/bin/joyio run --config config.yaml --timeout 15
```

### Erro de permissão

Comece com `--dry-run`. Se a leitura de `/dev/input` continuar bloqueada, instale uma regra udev específica ou ajuste as permissões da sessão. Consulte a seção anterior.

### Falha de Bluetooth

```bash
systemctl status bluetooth
bluetoothctl show
```

## Estado atual

O JoyIO está na Fase 3. O mapeamento de teclado/mouse, perfil YAML, scroll bidimensional, reconexão independente por lado e o toggle de mapping já funcionam. As próximas entregas previstas são o aumento temporário de ponteiro, execução como serviço e interface de bandeja.

Limitações atuais:

- requer um Joy-Con original L e um R;
- o pareamento ainda é feito pelo sistema operacional;
- a execução acontece em foreground;
- alterações no YAML exigem reiniciar o comando;
- o teste físico completo da reconexão independente ainda precisa ser repetido nos dois lados.

## Desenvolvimento e documentação técnica

Execute a suíte completa:

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest -q
```

Documentação para desenvolvimento:

- [Fases 0 a 3](docs/project/README.md): histórico e contratos de cada fase;
- [PERFORMANCE.md](PERFORMANCE.md): benchmarks e parâmetros medidos no ARM64;
- [docs/project/](docs/project/README.md): backlog, estratégia de gestão e prompts do roadmap;
- [docs/adr/0001-usar-hid-nintendo-e-evdev.md](docs/adr/0001-usar-hid-nintendo-e-evdev.md): decisão de arquitetura de entrada;
- [agents.md](agents.md): contexto para continuidade por outros agentes.
