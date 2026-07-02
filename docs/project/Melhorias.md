# Backlog do produto

Este arquivo é a visão curta do backlog. Estratégia, dependências e critérios de aceite estão em [GESTAO_PROJETO.md](GESTAO_PROJETO.md); prompts prontos para execução estão em [PROMPTS_ROADMAP.md](PROMPTS_ROADMAP.md).

## Agora · P0

- **JOY-031 — validação física da reconexão por lado:** implementação e testes automatizados concluídos; falta desligar/religar L e R separadamente em hardware.

## Em andamento · P1

- **JOY-034a — hot reload com inotify:** recarregar YAML automaticamente ao detectar mudança no arquivo de configuração, validar antes de aplicar e preservar estado em erro.

## Próximo · P1

- **JOY-034b — múltiplos perfis:** troca explícita entre perfis com canal de controle.

## Depois · P1/P2

- **JOY-040 — serviço de usuário:** ✅ concluído — `joyio service install|uninstall|status`, unidade `systemd --user`, configuração XDG e logs no journal.
- **JOY-050 — tray icon:** estado L/R, modo degradado, on/off, perfis, reload, abrir configuração/logs, reconectar e autostart.
- **JOY-060 — hardening/release:** instalação reproduzível, soak tests, matriz de falhas e documentação de suporte.

## Concluído

- combinações de teclas (`key_chord`);
- scroll vertical e horizontal pelo analógico;
- mouse, cliques e mapeamento completo dos dois Joy-Cons;
- otimizações do caminho crítico e perfil medido no ARM64;
- **JOY-032 — toggle mapping:** ativar/desativar com liberação de holds;
- **JOY-033 — pointer boost:** botão modificador com fator configurável.

## Fora do horizonte imediato

- giroscópio, acelerômetro, IR e NFC;
- vibração HD e LEDs avançados;
- suporte multiplataforma;
- clones e controles de terceiros sem validação dedicada.
