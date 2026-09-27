#!/usr/bin/env python3
"""Worker curto de Pillow/Pilmoji + meme_maker para renderização no Railway."""
import json
import sys
import meme_maker


def main():
    with open(sys.argv[1], "r", encoding="utf-8") as f:
        p = json.load(f)

    entrada = str(p.get("entrada") or "")
    saida = str(p.get("saida") or "")
    legenda = str(p.get("legenda") or "")
    brand = p.get("brand") or None
    uniqueness = p.get("uniqueness") or {}
    crop = p.get("crop")

    if isinstance(crop, dict) and all(k in crop for k in ("x", "y", "w", "h")):
        regiao = (int(crop["x"]), int(crop["y"]), int(crop["w"]), int(crop["h"]))
        meme_maker.make_post_from_crop(
            entrada, legenda, saida, regiao,
            brand=brand, uniqueness=uniqueness,
        )
    else:
        meme_maker.make_post(
            entrada, legenda, saida,
            brand=brand, uniqueness=uniqueness,
        )

    print(json.dumps({"ok": True}, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"ok": False, "erro": str(exc)}, ensure_ascii=False))
        raise SystemExit(1)
