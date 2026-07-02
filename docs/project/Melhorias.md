# Backlog do produto

Este arquivo é a visão curta do backlog. Estratégia, dependências e critérios de aceite estão em [GESTAO_PROJETO.md](GESTAO_PROJETO.md); prompts prontos para execução estão em [PROMPTS_ROADMAP.md](PROMPTS_ROADMAP.md).

## Agora · P0

- **JOY-031 — validação física da reconexão por lado:** implementação e testes automatizados concluídos; falta desligar/religar L e R separadamente em hardware.

## Em andamento · P1

- **JOY-032 — ativar/desativar mapping:** alternar com segurança entre controle de desktop e uso nativo em jogos, incluindo decisão sobre `EVIOCGRAB`.

Decisão atual: o toggle desliga apenas a emissão de uinput e preserva a observação dos controles. `EVIOCGRAB` fica fora desta primeira entrega do toggle e só entra se a validação em jogo mostrar duplicação real ou conflito de foco.

## Próximo · P1

- **JOY-033 — pointer boost:** botão modificador para acelerar temporariamente o ponteiro em telas grandes.

## Depois · P1/P2

- **JOY-034 — reload e perfis:** recarregar YAML atomicamente, preservar a configuração anterior em erro e trocar perfis.
- **JOY-040 — serviço de usuário:** execução automática via `systemd --user`, configuração XDG e logs no journal.
- **JOY-050 — tray icon:** estado L/R, modo degradado, on/off, perfis, reload, abrir configuração/logs, reconectar e autostart.
- **JOY-060 — hardening/release:** instalação reproduzível, soak tests, matriz de falhas e documentação de suporte.

## Concluído

- combinações de teclas (`key_chord`);
- scroll vertical e horizontal pelo analógico;
- mouse, cliques e mapeamento completo dos dois Joy-Cons;
- otimizações do caminho crítico e perfil medido no ARM64.

## Fora do horizonte imediato

- giroscópio, acelerômetro, IR e NFC;
- vibração HD e LEDs avançados;
- suporte multiplataforma;
- clones e controles de terceiros sem validação dedicada.
