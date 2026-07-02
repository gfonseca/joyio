# Prompt de desenvolvimento — JoyIO

> **Documento histórico:** este prompt originou o projeto e descreve o estado inicial. Para continuar o desenvolvimento atual, use [GESTAO_PROJETO.md](GESTAO_PROJETO.md), [PROMPTS_ROADMAP.md](PROMPTS_ROADMAP.md) e [agents.md](../../agents.md). Em caso de divergência, os documentos atuais têm precedência.

Use o texto abaixo como prompt para planejar e implementar o projeto.

---

## Papel

Atue como um engenheiro de software sênior especializado em Python, Linux, Bluetooth HID e dispositivos de entrada. Desenvolva o **JoyIO**, inicialmente como um programa de linha de comando e, somente depois de estabilizado, como um serviço Linux.

Não tente implementar todo o produto de uma vez. Trabalhe fase a fase, mantenha os componentes desacoplados e entregue software testável a cada etapa. Antes de adicionar uma dependência, confirme que ela funciona em **Linux ARM64/aarch64**, está disponível por `pip` ou pelo gerenciador de pacotes da distribuição e não depende de uma interface gráfica.

## Objetivo do produto

Criar uma aplicação Python para Linux ARM64 que:

1. encontre Joy-Cons Nintendo Switch disponíveis por Bluetooth;
2. permita selecionar, conectar e reconectar um Joy-Con;
3. leia os eventos HID do controle;
4. normalize botões e eixos analógicos para um modelo interno independente do hardware;
5. converta esses eventos em entradas comuns de teclado e mouse no Linux;
6. carregue os mapeamentos de um arquivo YAML;
7. comece como script/CLI executado no terminal;
8. seja preparada arquiteturalmente para virar um serviço `systemd` em uma fase posterior.

O primeiro marco deve funcionar sem interface gráfica e sem exigir a criação do serviço de sistema.

## Premissas técnicas

- Plataforma inicial: Linux ARM64/aarch64.
- Linguagem: Python 3 moderno, escolhendo explicitamente uma versão mínima suportada.
- Bluetooth do sistema: BlueZ.
- Leitura do controle: preferencialmente HID/hidraw, avaliando bibliotecas existentes antes de implementar o protocolo Joy-Con do zero.
- Emissão de teclado e mouse: dispositivo virtual Linux via `uinput`, preferencialmente por uma abstração bem mantida como `python-evdev`.
- Configuração: YAML validado antes do início da captura.
- Execução inicial: processo em foreground com logs no terminal e encerramento limpo via `SIGINT`/`SIGTERM`.
- Não use automação de desktop baseada em X11 como núcleo da solução. A emissão por `uinput` deve funcionar independentemente de X11 ou Wayland.
- Não suponha que o processo possa rodar como root. Documente permissões mínimas para `hidraw`, Bluetooth e `/dev/uinput`, com regras `udev` ou grupos quando necessário.
- ZL, ZR, SL e SR são botões digitais nos Joy-Cons; trate-os como botões, não como gatilhos analógicos.

## Limites da primeira fase funcional

Implemente inicialmente:

- descoberta/listagem de Joy-Cons conhecidos ou disponíveis;
- identificação clara de Joy-Con esquerdo e direito;
- conexão com **um Joy-Con por vez**;
- captura e exibição opcional dos eventos brutos e normalizados;
- mapeamento de botões para teclas individuais, combinações de teclas e cliques de mouse;
- mapeamento de um analógico para movimento relativo do mouse;
- dead zone, sensibilidade, inversão de eixo e limite de velocidade configuráveis;
- recarregamento da configuração apenas ao reiniciar o programa;
- reconexão básica com backoff quando o controle desconectar;
- logs úteis e códigos de saída previsíveis;
- modo `--dry-run`, que mostra as ações resultantes sem emitir eventos no sistema.

Adie explicitamente:

- pareamento de dois Joy-Cons como um único controle virtual;
- giroscópio, acelerômetro, IR, NFC, vibração HD e LEDs avançados;
- perfis por aplicativo;
- interface gráfica;
- edição interativa de mapeamentos;
- hot reload do YAML;
- daemonização e unidade `systemd`;
- suporte multiplataforma;
- macros com linguagem de script complexa.

## Experiência de linha de comando

Projete uma CLI semelhante a:

```text
joyio list
joyio inspect --device <id>
joyio run --device <id> --config config.yaml
joyio run --auto --config config.yaml
joyio validate-config config.yaml
joyio --version
```

Requisitos de comportamento:

- `list`: apresenta ID estável quando possível, endereço Bluetooth, nome, lado esquerdo/direito e estado da conexão;
- `inspect`: imprime eventos brutos e normalizados sem criar teclado/mouse virtual;
- `run`: conecta, lê eventos, aplica o mapeamento e emite entradas virtuais;
- `--auto`: seleciona um Joy-Con por critérios explícitos no YAML, sem escolha ambígua silenciosa;
- `validate-config`: valida o YAML e informa caminhos precisos para campos inválidos;
- `--verbose` ou `-v`: aumenta o nível de diagnóstico;
- `--dry-run`: processa normalmente, mas apenas registra as ações de saída.

Se “encontrar dispositivos disponíveis” exigir pareamento prévio pelo BlueZ, diferencie claramente **descobrir**, **parear**, **confiar** e **conectar**. Na primeira fase, é aceitável exigir pareamento prévio por `bluetoothctl`, desde que isso seja detectado e documentado com uma mensagem acionável. Não misture a gestão de pareamento com o leitor HID sem uma abstração própria.

## Arquitetura proposta

Organize o código em pacotes com responsabilidades pequenas e interfaces explícitas:

```text
joyio/
  __init__.py
  __main__.py
  cli.py
  config/
    loader.py
    models.py
    validation.py
  bluetooth/
    discovery.py
    bluez.py
  devices/
    base.py
    joycon.py
    protocol.py
    calibration.py
  events/
    models.py
    normalizer.py
  mapping/
    engine.py
    actions.py
    mouse_curve.py
  output/
    base.py
    uinput.py
    dry_run.py
  runtime/
    controller.py
    reconnect.py
    signals.py
  logging_config.py
tests/
  unit/
  integration/
  fixtures/
config.example.yaml
pyproject.toml
README.md
```

Adapte nomes se houver uma razão concreta, mas preserve estas fronteiras:

### 1. Descoberta e conexão

Responsável por consultar BlueZ, enumerar dispositivos e abrir/fechar o transporte HID. Não deve conhecer mapeamentos de teclado ou mouse.

### 2. Driver Joy-Con

Responsável pelos IDs de produto, protocolo, relatórios HID, estado dos botões, eixos, calibração e particularidades de Joy-Con L/R. Deve transformar bytes em eventos normalizados, sem emitir comandos no computador.

### 3. Modelo de eventos

Defina tipos imutáveis ou dataclasses para, no mínimo:

- `ButtonEvent(control, pressed, timestamp)`;
- `AxisEvent(control, value, timestamp)`, com valor normalizado em intervalo documentado, por exemplo `[-1.0, 1.0]`;
- `DeviceEvent` para conexão, desconexão e erro.

Não exponha pacotes binários HID ao motor de mapeamento.

### 4. Motor de mapeamento

Recebe eventos normalizados e produz ações abstratas como:

- pressionar/soltar tecla;
- pressionar/soltar uma combinação;
- clicar, pressionar ou soltar botão do mouse;
- mover mouse relativamente;
- rolar a roda;
- nenhuma ação.

Ele deve controlar estado para evitar teclas presas e repetições indevidas. Ao desconectar ou encerrar, deve liberar todas as teclas e botões virtuais ainda pressionados.

### 5. Backend de saída

Converte ações abstratas em eventos `uinput`. Disponibilize uma implementação `DryRunOutput`, permitindo testar o pipeline sem `/dev/uinput`.

### 6. Orquestração

Coordena ciclo de vida, sinais, conexão, loop de eventos, reconexão, carregamento da configuração e encerramento. Não concentre parsing HID, regras de mapeamento e chamadas `uinput` no mesmo loop.

## Contratos importantes

- Use injeção de dependências simples: transporte, relógio e backend de saída devem poder ser substituídos em testes.
- Mantenha I/O nas bordas. Parsing, normalização, curvas de mouse e resolução de mapeamentos devem ser funções puras sempre que possível.
- Tipagem estática deve cobrir o núcleo do projeto.
- Erros esperados devem ter exceções próprias e mensagens acionáveis; não capture `Exception` indiscriminadamente.
- Nenhum erro de configuração deve resultar em um mapeamento parcial silencioso.
- Eventos de botão devem preservar transições `press` e `release`.
- O movimento do mouse deve ser independente, tanto quanto possível, da frequência irregular dos relatórios HID. Documente a estratégia de tempo usada.

## Configuração YAML

Defina um esquema versionado. Um ponto de partida:

```yaml
version: 1

device:
  select:
    side: right          # left | right | any
    address: null        # opcional; tem precedência se preenchido
  reconnect:
    enabled: true
    initial_delay_ms: 500
    max_delay_ms: 10000

mouse:
  stick: right_stick
  dead_zone: 0.12
  sensitivity: 900.0    # unidade deve ser documentada
  acceleration: 1.4
  max_speed: 1800.0
  invert_x: false
  invert_y: true

mappings:
  buttons:
    a:
      type: mouse_button
      button: left
      mode: hold
    zr:
      type: mouse_button
      button: right
      mode: hold
    b:
      type: key
      key: KEY_ESC
      mode: tap
    x:
      type: key_chord
      keys: [KEY_LEFTCTRL, KEY_C]
      mode: tap
    plus:
      type: key
      key: KEY_ENTER
      mode: tap
    stick_press:
      type: mouse_button
      button: middle
      mode: tap
```

Defina formalmente:

- nomes canônicos de todos os controles para Joy-Con L e R;
- ações válidas;
- semântica de `tap`, `hold` e, se implementado depois, `repeat`;
- códigos de tecla aceitos, preferencialmente nomes Linux `KEY_*` validados;
- intervalos permitidos para dead zone, sensibilidade, aceleração e velocidade;
- comportamento para campos desconhecidos e controles incompatíveis com o lado selecionado;
- precedência entre configuração padrão e configuração do usuário.

O exemplo deve ser válido e executável. Não crie opções no YAML sem implementá-las ou marcá-las explicitamente como futuras.

## Movimento do mouse

O analógico não deve ser tratado como deslocamento bruto por pacote. Crie uma transformação documentada:

1. aplique calibração e normalize cada eixo;
2. aplique dead zone radial ou axial, deixando a escolha explícita;
3. reescale o intervalo restante para evitar um salto na borda da dead zone;
4. aplique sensibilidade e curva de aceleração configuráveis;
5. limite a velocidade;
6. integre pelo tempo decorrido para gerar deslocamento relativo;
7. preserve resíduos fracionários entre ciclos para reduzir trepidação em baixa velocidade.

Escolha e teste o comportamento diagonal para que não seja mais rápido que o axial de maneira acidental.

## Fases de entrega

### Fase 0 — investigação e prova de viabilidade

- identificar modelo de placa/distribuição Linux e versão do BlueZ;
- confirmar que Bluetooth, `hidraw` e `/dev/uinput` estão disponíveis;
- levantar IDs Bluetooth/USB relevantes de Joy-Con L e R;
- comparar bibliotecas Python candidatas quanto a manutenção, licença, protocolo suportado e ARM64;
- fazer uma prova curta: conectar a um Joy-Con e imprimir um botão e um eixo;
- registrar decisões em um ADR curto, principalmente “biblioteca existente versus driver próprio”.

**Saída:** relatório de viabilidade e script experimental descartável ou isolado.

### Fase 1 — captura confiável de entrada

- criar pacote Python, CLI e logging;
- listar e selecionar um Joy-Con;
- conectar a um controle previamente pareado;
- decodificar botões e um stick;
- normalizar eventos;
- oferecer `list` e `inspect`;
- adicionar fixtures de relatórios HID gravados e testes de parsing;
- tratar desconexão e encerramento limpo.

**Critério de aceite:** pressionar cada botão suportado e movimentar o stick gera exatamente os eventos normalizados esperados, sem travar o processo.

### Fase 2 — mapeamento e saída virtual

- implementar modelos e validação do YAML;
- implementar ações de teclado, combinações, cliques e movimento do mouse;
- criar backends `uinput` e `dry-run`;
- garantir liberação de entradas presas;
- fornecer configuração de exemplo e instruções de permissões.

**Critério de aceite:** usando somente o Joy-Con, o usuário consegue mover o ponteiro, clicar e executar pelo menos uma tecla e uma combinação, tanto em X11 quanto em Wayland quando o ambiente aceitar dispositivos `uinput`.

### Fase 3 — robustez

- reconexão com backoff;
- seleção automática determinística;
- leitura de calibração quando disponível e fallback seguro;
- métricas/logs de perda de pacotes, latência e reconexão;
- testes prolongados e testes de falha;
- empacotamento e instalação reproduzível em ARM64.

**Critério de aceite:** desconectar e reconectar o Joy-Con não deixa teclas pressionadas e retoma o funcionamento sem reiniciar o programa.

### Fase 4 — dois Joy-Cons e recursos avançados

- combinar L/R com política de sincronização;
- múltiplos perfis e troca explícita;
- rolagem, curvas adicionais e repetição controlada;
- avaliar giroscópio, vibração e LEDs separadamente;
- adicionar hot reload somente com atualização atômica e rollback em erro.

### Fase 5 — serviço Linux

- separar configuração de usuário e de sistema;
- definir unidade `systemd`, usuário/grupo, capabilities e regras `udev` mínimas;
- escolher conscientemente entre serviço de usuário e serviço de sistema;
- integrar logs ao journal;
- definir políticas de restart, readiness e shutdown;
- documentar instalação, atualização e remoção.

Não avance para esta fase antes de o script ser confiável e observável.

## Estratégia de testes

Inclua desde o início:

- testes unitários do parser HID usando pacotes binários anonimizados/gravados como fixtures;
- testes parametrizados para todos os botões de Joy-Con L e R;
- testes de extremos, centro, dead zone e diagonais dos eixos;
- testes do motor de mapeamento para `press`, `release`, `tap` e chords;
- teste que garante liberação de todas as teclas após erro, desconexão ou sinal;
- testes de validação para YAML válido, inválido e versão não suportada;
- backend falso para verificar sequências de saída sem acessar `uinput`;
- poucos testes de integração marcados, que dependem de hardware real;
- uma checklist manual separada para Bluetooth, Wayland/X11 e ARM64.

Os testes padrão não devem exigir Bluetooth, root, Joy-Con físico nem `/dev/uinput`.

## Qualidade e ferramentas

- Use `pyproject.toml` como fonte de configuração e dependências.
- Fixe apenas versões quando houver motivo; defina intervalos compatíveis e lockfile conforme a ferramenta escolhida.
- Use formatador, lint, testes e verificação de tipos, mantendo a quantidade de ferramentas razoável.
- Não esconda warnings relevantes.
- Registre versões e ambiente no modo de diagnóstico.
- Gere documentação curta para desenvolvimento e uso.
- Evite threads globais sem ciclo de vida controlado. Se usar `asyncio` ou threads, justifique a escolha com base nas APIs de Bluetooth/HID utilizadas.

## Lacunas e riscos que precisam de decisão explícita

Antes ou durante a Fase 0, investigue e documente:

1. **Escopo do Bluetooth:** o programa apenas conecta dispositivos já pareados ou também realizará discovery, pairing, trust e autorização pelo BlueZ?
2. **Biblioteca Joy-Con:** existe uma biblioteca mantida que cobre o protocolo necessário e ARM64, ou será necessário manter um driver próprio?
3. **Acesso ao dispositivo:** depois de pareado, os relatórios estarão acessíveis por `hidraw`, por uma biblioteca HID, por L2CAP direto ou por outra interface? Evite duas camadas disputando o mesmo dispositivo.
4. **Permissões:** quais regras `udev`, grupos e políticas BlueZ são necessárias sem conceder privilégios excessivos?
5. **Calibração:** como ler calibração de fábrica e usuário; qual fallback usar se a leitura falhar?
6. **Identidade:** endereço Bluetooth pode ser aleatório em algum cenário? Qual identificador persistente usar para seleção automática?
7. **Taxa de eventos:** qual frequência real de relatórios e qual estratégia mantém movimento consistente e baixa latência?
8. **Consumo de bateria:** como detectar bateria, suspensão e perda de conexão sem polling agressivo?
9. **Layout do teclado:** códigos `KEY_*` representam posições/eventos Linux, não necessariamente caracteres. Documente a interação com layouts ABNT2 e outros.
10. **Segurança:** qualquer processo com acesso a `uinput` pode injetar entrada. Restrinja permissões e valide arquivos de configuração.
11. **Compatibilidade:** testar Joy-Con original e deixar clones/controles de terceiros fora do suporte inicial, salvo decisão contrária.
12. **Interferência do desktop:** verificar se o ambiente cria simultaneamente outro joystick ou aplica mapeamentos duplicados.
13. **Dois Joy-Cons:** definir no futuro sincronização, side-specific controls e comportamento quando apenas um lado desconectar.
14. **Teclas presas:** definir recuperação em exceção, unplug, perda de Bluetooth, reload e encerramento forçado recuperável.
15. **Licenças:** confirmar licença e possibilidade de redistribuição de bibliotecas ou trechos de protocolo.

## Critérios de aceite do MVP

Considere o MVP concluído somente quando:

- a instalação for reproduzível em uma máquina Linux ARM64 limpa e suportada;
- `joyio list` identificar Joy-Con L/R previamente pareado;
- `joyio inspect` mostrar botões e eixos normalizados;
- `joyio validate-config` rejeitar configurações inválidas com mensagens claras;
- `joyio run` mover o mouse e emitir teclado/cliques conforme o YAML;
- `--dry-run` funcionar sem permissões de `uinput`;
- desconexão ou `Ctrl+C` liberar todas as teclas/botões emitidos;
- testes unitários não dependerem de hardware;
- README explicar pareamento, permissões, execução, configuração, diagnóstico e limitações;
- nenhuma funcionalidade futura seja apresentada como já suportada.

## Forma de trabalho e entregas esperadas

Para cada fase:

1. apresente primeiro um plano curto e as decisões ainda abertas;
2. implemente apenas o escopo da fase atual;
3. mantenha commits ou mudanças pequenas e coerentes;
4. execute testes, lint e type-check relevantes;
5. informe exatamente o que foi validado com hardware real e o que foi apenas simulado;
6. atualize README, YAML de exemplo e decisões arquiteturais;
7. pare ao final da fase e apresente resultados, limitações e próximo passo.

Não invente resultados de testes em hardware. Se não houver Joy-Con conectado, desenvolva com fixtures e backend falso, deixando a validação física como pendência explícita.

## Primeira tarefa

Comece somente pela **Fase 0**. Inspecione o ambiente, proponha no máximo duas abordagens tecnológicas viáveis, compare os trade-offs e construa a menor prova de conceito capaz de:

1. listar um Joy-Con previamente pareado;
2. conectar ou explicar de forma acionável por que a conexão não foi possível;
3. imprimir eventos de pelo menos um botão e um eixo;
4. encerrar limpamente.

Ao concluir, produza:

- diagnóstico do ambiente;
- decisão tecnológica recomendada e alternativa;
- lista de dependências e justificativas;
- riscos confirmados;
- comandos exatos para executar a prova;
- resultado dos testes automatizados e manuais, distinguindo claramente ambos;
- plano ajustado para a Fase 1.

---

## Decisões iniciais sugeridas para o responsável pelo projeto

Estas sugestões não substituem a investigação da Fase 0:

- suportar primeiro apenas Joy-Cons originais já pareados;
- começar com um controle por processo;
- escolher Joy-Con R como dispositivo do primeiro teste, pois o exemplo usa o stick direito;
- usar `uinput` como único mecanismo de saída no MVP;
- manter o parser Joy-Con isolado mesmo se uma biblioteca externa for usada;
- tornar `dry-run` um backend real desde o início, pois ele reduz muito o custo de testes e diagnóstico;
- deixar pairing automatizado, sensores de movimento e combinação L/R fora do MVP.
