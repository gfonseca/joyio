# Fase 3 — robustez e reconexão

Data de início: 2026-07-02.

## Primeiro incremento

O comando `joyio run` agora é supervisionado. Falhas transitórias de Bluetooth ou do leitor evdev encerram a sessão atual pelo caminho seguro, liberam todas as teclas e botões virtuais e iniciam uma nova aquisição do par Joy-Con.

O supervisor usa backoff exponencial configurável, limitado por um intervalo máximo. Uma aquisição completa reinicia a contagem de falhas; se qualquer lado cair novamente, uma nova sequência começa no atraso inicial.

## Configuração

```yaml
reconnect:
  enabled: true
  initial_delay: 1.0
  max_delay: 30.0
  multiplier: 2.0
  max_attempts: null
```

`max_attempts: null` mantém o processo tentando indefinidamente. `--no-reconnect` sobrescreve o YAML para testes de sessão única.

## Fronteiras preservadas

- o leitor evdev apenas detecta e relata a desconexão;
- `run_mapping` continua responsável por liberar e fechar uma sessão;
- o supervisor não conhece YAML, Bluetooth ou `uinput`; recebe callbacks e uma política tipada;
- a CLI monta as dependências e mantém logs operacionais em `stderr`.

## Próximos incrementos

- repetir a prova física controlada nos Joy-Cons L e R com o novo coordenador;
- tempo desde a última conexão e métricas estruturadas;
- hot reload do perfil;
- preparação para execução como serviço `systemd`.

## Segundo incremento — JOY-031

O runtime agora mantém uma única sessão de mapping e saída virtual enquanto os leitores de L e R entram e saem dinamicamente. A queda de um lado libera somente seus holds e zera somente seu analógico; o outro lado continua operacional. O retorno é identificado pelo endereço Bluetooth mesmo quando o kernel cria um novo caminho `event*`.

As tentativas `bluetoothctl connect` são subprocessos curtos, independentes por lado e consultados sem bloquear o loop evdev. Timeout e `org.bluez.Error.InProgress` são tratados como estados pendentes. A solução preserva a fronteira existente e não adiciona uma dependência D-Bus nesta etapa.

A validação simulada possui 67 testes, incluindo queda unilateral, hot-add em outro caminho, referência compartilhada de saídas e transições do BlueZ. A prova física separada de L e R permanece pendente e não deve ser confundida com esses testes automatizados.

## Revisão de performance

O caminho crítico foi revisado no ARM64. A taxa de 120 Hz foi mantida, enquanto consultas `ioctl`, cálculos analógicos e sincronizações redundantes foram removidos. Os resultados e parâmetros reais do `hid_nintendo` estão em [PERFORMANCE.md](../../PERFORMANCE.md).

## Prova física do primeiro incremento

O Joy-Con R foi desconectado pelo BlueZ durante um `joyio run --dry-run`. O leitor detectou `ENODEV`, encerrou a sessão e iniciou os intervalos de 1, 2, 4, 8, 16 e 30 segundos, respeitando o teto configurado.

Após o controle voltar a ficar acessível, o mesmo processo encontrou o Joy-Con L em `/dev/input/event12`, o Joy-Con R no novo `/dev/input/event8` e retomou o pipeline. O encerramento posterior com `Ctrl+C` liberou as entradas normalmente.

O adaptador reporta `WakeAllowed: no` para o Joy-Con. Portanto, depois de um desligamento explícito, pode ser necessário pressionar um botão para acordar o controle; o supervisor mantém as tentativas até ele ficar acessível.

## Terceiro incremento — JOY-032

O runtime passou a suportar um estado global `runtime.enabled` e um botão de `type: toggle` no YAML. Quando o mapping é desativado, o motor libera imediatamente as saídas virtuais mantidas, preserva a observação dos Joy-Cons e permite reativação pelo mesmo canal físico sem reiniciar o processo.

A política de `EVIOCGRAB` foi adiada nesta etapa. O runtime atual apenas controla a emissão para uinput; a retenção do dispositivo físico só deve entrar se a validação em jogo mostrar duplicação real ou conflito observável com o fluxo nativo.
