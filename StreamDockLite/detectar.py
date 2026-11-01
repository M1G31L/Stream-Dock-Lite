"""
detectar.py - Diagnóstico rápido: busca tu Stream Dock (N3E_1B05) y
prueba que responde. No necesita la interfaz gráfica.

Uso:  python detectar.py           -> lista y prueba
      python detectar.py --todos   -> lista todos los HID del equipo
Guarda un informe en informe_deteccion.txt (pégalo si necesitas ayuda).
"""

import sys
import time

import dock

lines = []


def out(s=""):
    print(s)
    lines.append(s)


def main():
    if dock.hid is None:
        out("ERROR: falta el paquete 'hidapi'. Reinstala Stream Dock Lite")
        return 1
    show_all = "--todos" in sys.argv
    out("=== Stream Dock Lite · diagnóstico ===")
    out(f"Python {sys.version.split()[0]} en {sys.platform}\n")

    infos = dock.list_hid()
    out(f"Dispositivos HID encontrados: {len(infos)}")
    for info in infos:
        s, reason, name, proto = dock.score_device(info)
        if s or show_all:
            out(f"  {'>>' if s else '  '} {info['vendor_id']:04X}:{info['product_id']:04X} "
                f"usage=0x{info.get('usage_page', 0):04X} if={info.get('interface_number')} "
                f"'{info.get('product_string')}' / '{info.get('manufacturer_string')}'"
                + (f"  -> {name}: {reason} (protocolo v{proto}, puntaje {s})" if s else ""))

    cands = dock.find_candidates()
    if not cands:
        out("\nNo se encontró ningún Stream Dock.")
        out("  • Revisa el cable USB (usa uno de datos, no solo de carga) y otro puerto.")
        out("  • Ejecuta 'python detectar.py --todos' y busca una línea con 1B05.")
        return 2

    c = cands[0]
    out(f"\nMejor candidato: {c.name} [{c.vidpid}] — {c.reason}")
    try:
        d = dock.DockDevice(c)
    except Exception as e:
        out(f"No se pudo abrir: {e}")
        out("  -> Cierra por completo el software oficial Stream Dock (también en la bandeja) y reintenta.")
        return 3
    out(f"Abierto OK. Protocolo v{d.protocol}, paquete {d.packet} bytes, imagen {d.image_size}px")
    d.set_brightness(80)
    from PIL import Image, ImageDraw
    for i in range(dock.KEY_COUNT):
        img = Image.new("RGB", (128, 128), (30 + i * 35, 120, 220 - i * 30))
        ImageDraw.Draw(img).text((50, 55), str(i + 1), fill="white")
        d.set_key_image(i, img, flush=False)
    d.flush()
    out("Se dibujaron números 1–6 en las teclas. Pulsa teclas/gira perillas durante 10 s…")
    t0 = time.time()
    while time.time() - t0 < 10:
        data = d.read(200)
        if data:
            evs = dock.parse_input(data, d.both_states)
            out(f"  raw={data[:12].hex(' ')} -> " +
                ", ".join(f"{e.kind}#{e.index + 1}={e.value}" if e.kind != "raw" else e.text or "raw"
                          for e in evs))
    d.clear()
    d.close()
    out("\nListo. Si los números salen girados o no aparecen, en la app usa Ajustes → Protocolo 2 o 3.")
    return 0


if __name__ == "__main__":
    code = main()
    try:
        with open("informe_deteccion.txt", "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        print("\nInforme guardado en informe_deteccion.txt")
    except Exception:
        pass
    if sys.platform == "win32":
        input("\nPulsa Enter para salir…")
    sys.exit(code)
