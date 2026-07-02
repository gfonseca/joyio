# Prompts de execução do roadmap JoyIO

Estes prompts são preparados para agentes que trabalham diretamente no repositório. Execute um por vez, seguindo a ordem de [GESTAO_PROJETO.md](GESTAO_PROJETO.md).

## Contexto obrigatório para todos os prompts

Acrescente este bloco ao início de qualquer tarefa:

```text
Você está trabalhando no JoyIO, em Python 3.12 para Linux ARM64. Leia integralmente agents.md, README.md, docs/project/FASE_3.md, PERFORMANCE.md e docs/project/GESTAO_PROJETO.md antes de alterar código. Inspecione o git status e preserve alterações existentes.

Decisões fixadas:
- entrada via hid_nintendo + python-evdev;
- saída via uinput e backend dry-run;
- Joy-Con L/R formam uma sessão lógica, mas devem evoluir para reconexão independente;
- config, Bluetooth, evdev, mapping, output e runtime permanecem desacoplados;
- stdout de inspect/dry-run continua adequado a JSONL; diagnóstico vai para stderr;
- todo Python roda no .venv;
- não adicione threads, asyncio ou dependências sem justificar impacto e ciclo de vida;
- nunca deixe teclas ou botões virtuais pressionados após falha, reload, toggle ou desconexão.

Antes de implementar, apresente um plano curto e confirme o comportamento atual com testes ou reprodução. Ao terminar, execute testes específicos, suíte completa, pip check e git diff --check. Diferencie claramente validação simulada de validação em hardware real. Atualize documentação e testes funcionais afetados.
```

## Prompt JOY-031 — coordenador independente por lado

```text
Implemente o Marco 3.1 de docs/project/GESTAO_PROJETO.md: reconexão e ciclo de vida independentes para Joy-Con L e R.

Problema confirmado:
- acquire_inputs conecta L e R sequencialmente e só inicia quando ambos estão prontos;
- timeout de bluetoothctl pode deixar o BlueZ em InProgress;
- o backoff pode continuar dormindo mesmo depois de Connected=yes;
- read_runtime_events usa uma lista fixa e encerra o par quando um lado cai.

Escopo:
1. Modele estado por lado: offline, connecting, bluetooth_ready, evdev_ready e active.
2. Trate timeout/InProgress como conexão pendente e evite chamadas connect concorrentes ou repetidas.
3. Faça a espera reagir rapidamente quando Connected/evdev aparecer.
4. Permita operação degradada com um lado e hot-add do lado ausente.
5. Ao remover um lado, libere apenas as ações originadas nele.
6. Preserve o dispositivo uinput e o mapping do lado ativo.
7. Emita logs de transição por lado em stderr.

Fora do escopo: pairing, tray, systemd, hot reload e troca de perfil.

Critérios de aceite:
- L continua funcionando quando R cai e vice-versa;
- cada lado retorna sem reiniciar o processo;
- não há tecla presa;
- InProgress não causa tempestade de subprocessos;
- testes determinísticos cobrem a máquina de estados e leitores dinâmicos;
- execute prova física desligando/religando L e R separadamente.

Não migre automaticamente para D-Bus. Primeiro compare uma coordenação robusta com bluetoothctl e uma implementação D-Bus, incluindo dependências, latência e ARM64. Registre a decisão se ela alterar a fronteira Bluetooth.
```

## Prompt JOY-032 — toggle desktop/jogo

```text
Implemente o Marco 3.2 de docs/project/GESTAO_PROJETO.md: ativar/desativar o mapping por uma combinação configurável.

Antes de codificar, investigue como os Joy-Cons físicos aparecem para jogos enquanto o JoyIO está ativo. Decida e documente a política de EVIOCGRAB; não trate “desativado” apenas como descarte de saída se isso mantiver eventos duplicados.

Escopo:
- schema YAML versionado para o toggle;
- combinação lado-específica que continua sendo observada quando o mapping está desligado;
- estado enabled/disabled no runtime;
- release_all antes de desativar;
- grab/ungrab opcional conforme decisão registrada;
- dry-run e logs mostrando a transição;
- proteção contra uma configuração sem caminho de reativação.

Fora do escopo: tray, perfis por aplicativo e macros complexas.

Critérios de aceite:
- alternar repetidamente não deixa teclas/cliques presos;
- o modo nativo em jogo corresponde à política documentada;
- a combinação de retorno funciona com mapping desligado;
- YAML inválido é rejeitado com caminho preciso;
- testes funcionais cobrem toggle durante tecla mantida, desconexão e reconexão.
```

## Prompt JOY-033 — pointer boost

```text
Implemente o Marco 3.3 de docs/project/GESTAO_PROJETO.md: pointer boost acionado por botão.

Escopo:
- configuração de um modificador lado-específico;
- fator de boost validado, com limites explícitos;
- modo hold como comportamento principal;
- boost aplicado somente ao ponteiro, não ao scroll;
- teto de velocidade, dead zone, direção e resíduos preservados;
- suporte dry-run e teste funcional no perfil de exemplo, sem impor o recurso ao usuário.

Fora do escopo: aceleração dependente de aplicativo e macros.

Critérios de aceite:
- a velocidade aumenta pelo fator configurado enquanto o botão está mantido;
- soltar restaura a velocidade imediatamente;
- desconexão do lado modificador cancela o boost;
- nenhuma regressão de CPU maior que 5% no benchmark do caminho crítico;
- testes cobrem boost em movimento axial, diagonal e próximo da dead zone.
```

## Prompt JOY-034 — reload atômico e perfis

```text
Implemente o Marco 3.4 de docs/project/GESTAO_PROJETO.md em dois incrementos: primeiro reload atômico, depois múltiplos perfis.

Para reload:
- carregue e valide a nova configuração completamente antes da troca;
- libere ações mantidas cuja semântica mudou;
- em erro, preserve integralmente a configuração anterior;
- forneça um comando de controle explícito, sem depender apenas de monitoramento de arquivo.

Para perfis:
- defina identidade e diretório XDG;
- troque de perfil atomicamente;
- exponha perfil ativo e erros pelo canal de controle.

Antes de escolher o canal, compare socket Unix e D-Bus de sessão. Considere autenticação local, systemd user, tray, formato de mensagens, testes e dependências.

Critérios de aceite:
- nenhum reload parcial;
- perfil anterior continua ativo após YAML inválido;
- teclas não ficam presas durante troca;
- testes cobrem concorrência entre evento, reload e desconexão;
- decisão do canal registrada em ADR.
```

## Prompt JOY-040 — serviço systemd de usuário

```text
Implemente o Marco 4 de docs/project/GESTAO_PROJETO.md como serviço systemd de usuário.

Escopo:
- unidade .service instalada de forma reproduzível;
- configuração e perfis em caminhos XDG;
- logs úteis no journal;
- readiness e shutdown limpo;
- restart apenas para falhas não tratadas;
- comandos documentados para instalar, habilitar, iniciar, diagnosticar e remover;
- permissões mínimas para evdev/uinput sem executar todo o programa como root.

Valide a decisão user service versus system service com Bluetooth, uaccess, sessão GNOME e Wayland. Prefira user service salvo evidência contrária.

Critérios de aceite:
- inicia automaticamente após login;
- encerra liberando entradas;
- reconexão interna não causa restart do serviço;
- instalação limpa funciona em ARM64;
- journal permite diagnosticar cada lado;
- testes de unidade e systemd-analyze verify passam.
```

## Prompt JOY-050 — ícone de bandeja

```text
Implemente o Marco 5 de docs/project/GESTAO_PROJETO.md como processo cliente separado do runtime.

Antes de escolher toolkit/protocolo de tray, compare suporte GNOME/AppIndicator, Wayland, ARM64, empacotamento, memória residente e manutenção. Não coloque GTK/Qt no processo de captura.

Menu mínimo:
- estado do Joy-Con L e R;
- estado degradado;
- mapping on/off;
- perfil ativo/troca de perfil;
- reload/validação;
- abrir configuração no editor padrão;
- abrir logs;
- reconectar lado;
- autostart;
- sair.

Critérios de aceite:
- fechar/reiniciar o tray não interrompe o runtime;
- ausência do serviço é exibida claramente;
- ações usam o canal de controle documentado;
- configuração inválida gera feedback sem derrubar o perfil ativo;
- consumo de memória e dependências são registrados;
- comportamento é validado no GNOME usado pelo projeto.
```

## Prompt JOY-060 — hardening e release

```text
Prepare o Marco 6 de docs/project/GESTAO_PROJETO.md sem adicionar recursos novos.

Escopo:
- instalação reproduzível em Linux ARM64 limpo;
- testes prolongados e matriz de falhas;
- checklist de X11/Wayland, login/logout, sleep/wake e Bluetooth;
- revisão de udev/uinput e superfície de segurança;
- changelog, versionamento e procedimento de rollback;
- pacote/instalador e desinstalação;
- documentação de suporte e limitações.

Critérios de aceite:
- suíte automatizada limpa;
- teste funcional completo no par real;
- 8 horas de operação sem crescimento contínuo de memória ou CPU;
- 20 ciclos de desconexão por lado sem entrada presa;
- instalação e remoção reproduzidas em uma segunda máquina/ambiente ARM64;
- nenhum resultado de hardware é inferido ou inventado.
```

## Prompt genérico para uma issue

```text
Implemente a issue <ID/TÍTULO> do JoyIO.

Objetivo:
<resultado observável>

Contexto/evidência:
<bug, captura, benchmark ou necessidade do usuário>

Escopo:
- <item>

Fora do escopo:
- <item>

Critérios de aceite:
- <comportamento verificável>

Testes automatizados:
- <casos>

Teste físico:
- <procedimento e resultado esperado>

Restrições:
- preserve as fronteiras descritas em agents.md;
- use o .venv;
- preserve alterações existentes;
- não adicione dependências sem análise ARM64;
- atualize documentos afetados;
- reporte evidência, limitações e próximos riscos.
```
