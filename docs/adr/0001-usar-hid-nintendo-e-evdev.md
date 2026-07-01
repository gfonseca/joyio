# ADR 0001 — Usar hid-nintendo e evdev como caminho principal

- Status: aceito para a Fase 0
- Data: 2026-07-01

## Contexto

Joy-Cons usam relatórios HID e subcomandos específicos. O projeto precisa capturar botões e analógicos em Linux ARM64, com baixo custo de manutenção e uma rota futura para saída virtual via `uinput`.

## Decisão

Usar o driver `hid_nintendo` do kernel para conexão HID, protocolo, calibração e exposição dos controles como dispositivos evdev. Usar `python-evdev` na borda Python para leitura agora e, na Fase 2, escrita por `uinput`.

O gerenciamento de descoberta, pareamento e conexão permanece em uma fronteira BlueZ separada. Na Fase 0 essa fronteira usa `bluetoothctl`; ela poderá ser substituída por D-Bus sem alterar o leitor de eventos.

## Motivos

- o kernel instalado fornece `CONFIG_HID_NINTENDO=m` para aarch64;
- o driver oficial suporta Joy-Con L/R por Bluetooth e lê calibração de fábrica;
- botões e eixos chegam por uma API Linux estável, sem expor bytes HID ao restante do projeto;
- `python-evdev` cobre tanto entrada evdev quanto a futura saída `uinput`;
- reduz a quantidade de protocolo específico que o projeto teria de testar e manter.

## Alternativa mantida

Usar HIDAPI com backend `hidraw`, inicializar o Joy-Con e interpretar relatórios diretamente em Python. Isso oferece controle sobre subcomandos e recursos não expostos pelo kernel, mas exige regras para `/dev/hidraw`, calibração, tratamento do protocolo, disputa de posse com o driver do kernel e uma superfície de testes maior.

Essa alternativa só deve ser adotada para uma capacidade comprovadamente ausente em `hid_nintendo`; não deve coexistir com o caminho evdev para o mesmo controle sem uma política explícita.

## Consequências

- o suporte mínimo de kernel passa a ser um requisito do produto;
- clones com IDs ou descritores diferentes ficam fora do escopo inicial;
- nomes evdev precisam ser traduzidos para nomes canônicos do JoyIO na Fase 1;
- acesso a `/dev/input/event*` requer política udev/ACL;
- a Fase 1 deve capturar fixtures evdev reais de Joy-Con L e R.

## Fontes primárias

- [Driver hid-nintendo no kernel Linux](https://github.com/torvalds/linux/blob/master/drivers/hid/hid-nintendo.c)
- [Opção HID_NINTENDO no Kconfig do kernel](https://github.com/torvalds/linux/blob/master/drivers/hid/Kconfig)
- [Documentação oficial do python-evdev](https://python-evdev.readthedocs.io/en/stable/)
- [HIDAPI oficial](https://github.com/libusb/hidapi)
- [API Device1 oficial do BlueZ](https://github.com/bluez/bluez/blob/master/doc/org.bluez.Device.rst)
