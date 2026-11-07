#!/usr/bin/env bash
# Refaz as capturas de tela da documentação (docs/assets/screens/{en-US,pt-BR}/*.webp).
#
#   SHIELD_URL=http://127.0.0.1:8080 E2E_EMAIL=admin@... E2E_SENHA=... \
#   [SETUP_URL=http://127.0.0.1:8081] scripts/doc_capturas.sh
#
# SHIELD_URL: um shield standalone já configurado e com pelo menos um scan terminado.
# SETUP_URL (opcional): um container NOVO, ainda no primeiro uso, para a tela de setup.
# Precisa de Python 3 com Pillow (WebP) e das dependências da web (yarn install).
#
# Por que script e não print à mão: captura feita à mão envelhece calada quando a tela
# muda. Com o script, refazer é um comando, e o diff das imagens aparece no PR.
set -euo pipefail

raiz="$(cd "$(dirname "$0")/.." && pwd)"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

for idioma in en-US pt-BR; do
  echo "==> capturas em ${idioma}"
  (cd "$raiz/web" && CAPTURA_IDIOMA="$idioma" CAPTURA_SAIDA="$tmp/$idioma" node e2e/capturas.mjs)
  if [ -n "${SETUP_URL:-}" ]; then
    (cd "$raiz/web" && SHIELD_URL="$SETUP_URL" CAPTURA_PRIMEIRO_USO=1 \
      CAPTURA_IDIOMA="$idioma" CAPTURA_SAIDA="$tmp/$idioma" node e2e/capturas.mjs)
  fi
done

python3 - "$tmp" "$raiz/docs/assets/screens" <<'EOF'
# PNG 2x -> WebP: desktop com 1600 px de largura, celular com 780; qualidade 82.
import sys
from pathlib import Path
from PIL import Image

origem, destino = Path(sys.argv[1]), Path(sys.argv[2])
total = 0
for png in sorted(origem.glob("*/*.png")):
    alvo = destino / png.parent.name / (png.stem + ".webp")
    alvo.parent.mkdir(parents=True, exist_ok=True)
    im = Image.open(png).convert("RGB")
    largura = 780 if png.stem.startswith("2") else 1600
    if im.width > largura:
        im = im.resize((largura, round(im.height * largura / im.width)), Image.LANCZOS)
    im.save(alvo, "WEBP", quality=82, method=6)
    total += alvo.stat().st_size
    print(f"    {alvo.relative_to(destino.parent.parent.parent)}  {alvo.stat().st_size // 1024} KB")
print(f"==> {total // 1024} KB no total")
EOF
