# Estratégia de gestão do projeto JoyIO

Data-base: 2026-07-02. Estado: versão de desenvolvimento `0.3.0`, Fase 3, 67 testes automatizados.

## Objetivo

Evoluir o JoyIO de uma CLI funcional para um utilitário confiável de desktop, preservando baixo consumo no ARM64, configuração simples e fronteiras claras entre Bluetooth, entrada, mapping e saída.

O projeto deve avançar em incrementos verificáveis. Recursos visuais não devem mascarar fragilidade no runtime; primeiro estabilizamos conexão, estado e controle, depois adicionamos serviço e tray.

## Princípios de execução

1. **Um incremento ativo por vez.** Limite de trabalho em progresso: uma funcionalidade ou correção estrutural.
2. **Hardware real e simulação são evidências distintas.** O relatório deve dizer explicitamente o que foi testado em cada ambiente.
3. **I/O nas bordas.** Bluetooth, evdev e uinput não entram no motor puro de mapping.
4. **Configuração inválida nunca é aplicada parcialmente.** Reloads futuros precisam ser atômicos.
5. **Nenhuma tecla pode ficar presa.** Falha, desconexão, toggle, reload e encerramento devem liberar estado.
6. **Dependências novas precisam justificar custo.** Confirmar ARM64, manutenção, licença, memória e integração com GNOME/Wayland.
7. **O README é para usuários.** Arquitetura, benchmarks e decisões ficam nos documentos técnicos.

## Priorização

Use quatro níveis:

- **P0 — confiabilidade:** perda de controle, entradas presas, reconexão e corrupção de estado;
- **P1 — experiência principal:** recursos usados durante a operação diária;
- **P2 — integração desktop:** serviço, tray, notificações e perfis;
- **P3 — exploração:** sensores, bateria, vibração, LEDs e compatibilidade adicional.

Dentro do mesmo nível, priorize primeiro o item que desbloqueia mais entregas posteriores.

## Roadmap proposto

### Marco 3.1 — coordenador independente de Joy-Cons · P0 · Validação física

Objetivo: permitir que cada lado conecte, desconecte e retorne de forma independente.

Entregas:

- estado por lado: `offline`, `connecting`, `bluetooth_ready`, `evdev_ready` e `active`;
- tratamento de `Connected`, timeout e `org.bluez.Error.InProgress` como estados, não como reinício cego;
- espera curta/interrompível em vez de dormir até 30 segundos depois de o dispositivo retornar;
- runtime degradado com somente um Joy-Con disponível;
- adição e remoção dinâmica de leitores;
- liberação somente das ações originadas pelo lado desconectado;
- logs de transição por lado.

Critérios de aceite:

- desligar o L não interrompe os controles pertencentes ao R, e vice-versa;
- o lado que retorna volta a produzir ações sem reiniciar o processo;
- `InProgress` não inicia uma tempestade de subprocessos `bluetoothctl`;
- nenhuma tecla ou clique fica preso;
- testes automatizados cobrem todas as transições;
- teste físico controlado é executado nos dois lados.

Estado: implementação e validação automatizada concluídas. Resta executar a prova física controlada desligando e religando L e R separadamente.

### Marco 3.2 — controle operacional do mapping · P1 · Próximo

Objetivo: alternar com segurança entre uso desktop e uso nativo em jogos.

Entregas:

- ação YAML para ativar/desativar o mapping por botão ou acorde;
- estado global `enabled/disabled` observável;
- liberação imediata das saídas virtuais ao desativar;
- decisão explícita sobre `EVIOCGRAB`:
  - mapping ativo: opcionalmente impedir eventos duplicados nos jogos;
  - mapping inativo: liberar o grab e deixar os Joy-Cons nativos disponíveis;
- proteção contra desativação sem caminho de retorno.

Critérios de aceite:

- o toggle nunca deixa entradas pressionadas;
- a combinação de retorno funciona mesmo com mapping desativado;
- jogos recebem o comportamento documentado, sem duplicação silenciosa;
- configuração inválida do toggle é rejeitada.

Decisão registrada no incremento atual:

- o mapping é desligado no motor e as saídas virtuais são liberadas imediatamente;
- os leitores de Joy-Con continuam ativos para que o toggle permaneça acessível;
- `EVIOCGRAB` foi adiado nesta etapa. A avaliação de grab fica condicionada a evidência real de eventos duplicados em jogo, para evitar bloquear o controle nativo antes da hora.

### Marco 3.3 — pointer boost · P1 · Próximo

Objetivo: oferecer navegação rápida em telas grandes sem perder precisão no movimento normal.

Entregas:

- ação/modificador configurável para boost;
- multiplicador separado para o ponteiro, sem alterar scroll;
- transições suaves e teto de velocidade preservado;
- suporte a `hold`; `toggle` somente se houver caso de uso validado.

Critérios de aceite:

- pressionar o modificador aumenta a velocidade pelo fator configurado;
- soltar restaura imediatamente a curva normal;
- dead zone, direção e resíduos continuam corretos;
- custo ocioso permanece equivalente ao baseline de [PERFORMANCE.md](../../PERFORMANCE.md).

### Marco 3.4 — reload e perfis · P1/P2

Objetivo: preparar o runtime para ser controlado sem reiniciar.

Entregas:

- reload atômico do YAML;
- rollback quando a nova configuração é inválida;
- troca explícita entre perfis;
- comando/control channel para status, reload e seleção de perfil.

O canal de controle deve ser definido antes do serviço e do tray. Avaliar socket Unix ou D-Bus de sessão; não acoplar a interface diretamente ao processo de captura.

### Marco 4 — serviço de usuário · P2

Objetivo: executar o JoyIO automaticamente na sessão do usuário.

Entregas:

- unidade `systemd --user`;
- localização padrão de configuração em XDG;
- logs no journal;
- shutdown limpo e política de restart;
- instalação, atualização e remoção reproduzíveis.

Preferir serviço de usuário enquanto Bluetooth, sessão gráfica e permissões `uaccess` dependerem do usuário logado.

### Marco 5 — ícone de bandeja · P2

Objetivo: apresentar e controlar o estado do JoyIO sem exigir terminal.

Menu mínimo:

- estado individual do Joy-Con L e R;
- mapping ligado/desligado;
- perfil ativo e troca de perfil;
- reconectar um lado;
- recarregar e validar configuração;
- abrir configuração no editor padrão;
- abrir logs recentes;
- iniciar/parar serviço;
- ativar início automático;
- sair.

Possíveis extensões:

- notificações de desconexão/reconexão;
- indicador de configuração inválida;
- bateria, somente quando houver fonte confiável;
- atalho para documentação e diagnóstico;
- status degradado quando apenas um lado estiver ativo.

O tray deve ser um cliente do canal de controle, nunca o dono do loop evdev.

### Marco 6 — release estável · P1/P2

Objetivo: produzir uma instalação reproduzível e um ciclo de suporte claro.

Entregas:

- checklist ARM64 limpa;
- teste prolongado de conexão e uso;
- documentação de permissões e recuperação;
- versionamento e changelog;
- pacote/instalador definido;
- política explícita para Joy-Cons originais e dispositivos não suportados.

## Itens já concluídos do documento de melhorias

- combinações de teclas: `type: key_chord`;
- scroll vertical e horizontal pelo analógico;
- otimização do caminho crítico a 120 Hz;
- mapeamento completo dos dois Joy-Cons.

Esses itens permanecem na suíte de regressão, não no backlog ativo.

## Fluxo de uma tarefa

### Definition of Ready

Uma tarefa só entra em execução quando possui:

- problema e resultado esperado;
- escopo e itens explicitamente fora do escopo;
- dependências e decisões abertas;
- critérios de aceite observáveis;
- estratégia de testes automatizados e físicos;
- impacto esperado em YAML, CLI e compatibilidade.

### Execução

1. Ler `agents.md` e os documentos da fase atual.
2. Inspecionar worktree e preservar alterações existentes.
3. Medir ou reproduzir antes de alterar comportamento.
4. Implementar o menor incremento completo.
5. Rodar testes específicos durante o desenvolvimento.
6. Rodar suíte completa e `git diff --check` no fechamento.
7. Fazer prova física proporcional ao risco.
8. Atualizar README somente se o usuário precisar conhecer a mudança.
9. Atualizar fase, handoff e ADR quando houver decisão estrutural.

### Definition of Done

- critérios de aceite atendidos;
- testes automatizados passando no `.venv`;
- nenhum warning ou erro de configuração novo;
- comportamento de desconexão e encerramento seguro verificado;
- resultado físico e simulado distinguidos no relatório;
- documentação coerente;
- benchmark comparativo para mudanças no caminho crítico;
- worktree revisado e commit coeso quando solicitado.

## Gestão do backlog

Cada item deve usar um identificador estável, por exemplo `JOY-031`, e conter:

```text
Título:
Prioridade: P0 | P1 | P2 | P3
Área: bluetooth | evdev | mapping | output | runtime | config | desktop | docs
Objetivo:
Contexto/evidência:
Escopo:
Fora do escopo:
Critérios de aceite:
Testes automatizados:
Teste físico:
Riscos/dependências:
Documentos afetados:
```

Estados recomendados:

```text
Backlog -> Ready -> Em andamento -> Validação física -> Concluído
```

Mantenha no máximo um item em `Em andamento`. Uma tarefa bloqueada volta para `Ready` com o bloqueio documentado, em vez de acumular implementação parcial.

## Cadência e releases

- fechar um incremento funcional antes de iniciar outro;
- criar uma versão minor para novos recursos e patch para correções;
- manter commits pequenos por contrato: config, runtime, output, docs;
- produzir uma nota curta por marco: resultado, testes, limitações e próximo passo;
- não anunciar suporte estável antes do Marco 6.

## Riscos principais

| Risco | Mitigação |
|---|---|
| BlueZ mantém conexão `InProgress` após timeout | Coordenador por estado e observação de propriedades |
| Apenas um Joy-Con retorna | Runtime degradado e leitores dinâmicos |
| Toggle deixa tecla presa | `release_all` obrigatório antes da mudança de estado |
| Jogo recebe Joy-Con e uinput simultaneamente | Política explícita e testada de `EVIOCGRAB` |
| Tray aumenta dependências e memória | Processo separado e cliente leve do runtime |
| Reload aplica perfil parcial | Validar completamente e trocar configuração atomicamente |
| Serviço perde acesso por `uaccess` | Preferir serviço de usuário e testar sessão real |
| Drift gera saída involuntária | Dead zones medidas e perfil configurável |
