#!/usr/bin/env python3
"""Demo: cria o VirtualGamepad e simula inputs para teste visual.

Execute e observe a saída. Para ver os eventos raw em outra janela:
    sudo apt install evtest && evtest
    (selecione "JoyIO Virtual Gamepad")
"""

import time
from evdev import InputDevice, list_devices, ecodes
from joyio.output.gamepad import VirtualGamepad


def find_gamepad():
    """Encontra o dispositivo virtual pelo nome."""
    for path in sorted(list_devices()):
        try:
            dev = InputDevice(path)
            if "JoyIO Virtual Gamepad" in dev.name:
                return path, dev
        except PermissionError:
            pass
    return None, None


def main():
    print("=" * 55)
    print("  JoyIO Virtual Gamepad — Demo")
    print("=" * 55)

    gp = VirtualGamepad()

    path, reader = find_gamepad()
    if path is None:
        print("ERRO: dispositivo virtual não encontrado em /dev/input/")
        gp.close()
        return 1

    print(f"\nDispositivo: {path} — {reader.name}")
    print("Pressione Ctrl+C para encerrar.\n")

    events = [
        # (desc, ação)
        ("ANALÓGICO ESQUERDO: cima-esquerda", lambda: (
            gp.emit_joyio_axis("left", "left_stick_x", -0.7),
            gp.emit_joyio_axis("left", "left_stick_y", -0.7),
        )),
        ("ANALÓGICO ESQUERDO: centro", lambda: (
            gp.emit_joyio_axis("left", "left_stick_x", 0.0),
            gp.emit_joyio_axis("left", "left_stick_y", 0.0),
        )),
        ("ANALÓGICO DIREITO: baixo-direita", lambda: (
            gp.emit_joyio_axis("right", "right_stick_x", 0.7),
            gp.emit_joyio_axis("right", "right_stick_y", 0.7),
        )),
        ("ANALÓGICO DIREITO: centro", lambda: (
            gp.emit_joyio_axis("right", "right_stick_x", 0.0),
            gp.emit_joyio_axis("right", "right_stick_y", 0.0),
        )),
        ("BOTÃO A (pressiona e solta)", lambda: (
            gp.emit_joyio_button("right", "a", True),
            time.sleep(0.15),
            gp.emit_joyio_button("right", "a", False),
        )),
        ("BOTÃO B (pressiona e solta)", lambda: (
            gp.emit_joyio_button("right", "b", True),
            time.sleep(0.15),
            gp.emit_joyio_button("right", "b", False),
        )),
        ("BOTÃO X (pressiona e solta)", lambda: (
            gp.emit_joyio_button("right", "x", True),
            time.sleep(0.15),
            gp.emit_joyio_button("right", "x", False),
        )),
        ("BOTÃO Y (pressiona e solta)", lambda: (
            gp.emit_joyio_button("right", "y", True),
            time.sleep(0.15),
            gp.emit_joyio_button("right", "y", False),
        )),
        ("L + R juntos", lambda: (
            gp.emit_joyio_button("left", "l", True),
            gp.emit_joyio_button("right", "r", True),
            time.sleep(0.15),
            gp.emit_joyio_button("left", "l", False),
            gp.emit_joyio_button("right", "r", False),
        )),
        ("ZL + ZR juntos", lambda: (
            gp.emit_joyio_button("left", "zl", True),
            gp.emit_joyio_button("right", "zr", True),
            time.sleep(0.15),
            gp.emit_joyio_button("left", "zl", False),
            gp.emit_joyio_button("right", "zr", False),
        )),
        ("D-PAD: cima", lambda: (
            gp.emit_joyio_button("left", "dpad_up", True),
            time.sleep(0.15),
            gp.emit_joyio_button("left", "dpad_up", False),
        )),
        ("D-PAD: direita", lambda: (
            gp.emit_joyio_button("left", "dpad_right", True),
            time.sleep(0.15),
            gp.emit_joyio_button("left", "dpad_right", False),
        )),
        ("D-PAD: diagonal (cima+direita)", lambda: (
            gp.emit_joyio_button("left", "dpad_up", True),
            gp.emit_joyio_button("left", "dpad_right", True),
            time.sleep(0.15),
            gp.emit_joyio_button("left", "dpad_up", False),
            gp.emit_joyio_button("left", "dpad_right", False),
        )),
        ("START + SELECT", lambda: (
            gp.emit_joyio_button("right", "plus", True),
            gp.emit_joyio_button("left", "minus", True),
            time.sleep(0.15),
            gp.emit_joyio_button("right", "plus", False),
            gp.emit_joyio_button("left", "minus", False),
        )),
        ("STICK PRESS L + R", lambda: (
            gp.emit_joyio_button("left", "left_stick_press", True),
            gp.emit_joyio_button("right", "right_stick_press", True),
            time.sleep(0.15),
            gp.emit_joyio_button("left", "left_stick_press", False),
            gp.emit_joyio_button("right", "right_stick_press", False),
        )),
        ("HOME", lambda: (
            gp.emit_joyio_button("right", "home", True),
            time.sleep(0.15),
            gp.emit_joyio_button("right", "home", False),
        )),
    ]

    try:
        for desc, action in events:
            print(f"  ▶ {desc}")
            action()
            time.sleep(0.25)

        print(f"\n✓ Demo concluído — {len(events)} ações executadas.")
        print(f"  Abra 'evtest' e selecione '{reader.name}' para ver os eventos raw.")

    except KeyboardInterrupt:
        print("\nInterrompido.")

    finally:
        gp.close()
        reader.close()
        print("Gamepad fechado.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
