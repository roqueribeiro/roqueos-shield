#!/usr/bin/env python3
"""Gera banner.en.jpg / banner.pt.jpg no padrão aidlc, tema RoqueShield.

Uso:
  python gen.py                      # arte desenhada em SVG (padrão, on-brand)
  python gen.py --art arte-scan.jpg  # usa a arte fotoreal gerada no ChatGPT
                                     # (ver PROMPT.md) no lugar do motivo SVG,
                                     # mantendo o mesmo overlay de texto.
  python gen.py --out <dir>          # onde salvar (padrão: aqui)

O overlay de texto (eyebrow, wordmark, lema, descritor, chips) não muda; só
a arte à direita. É o mesmo processo do aidlc-harness: arte + overlay."""
import argparse, base64, mimetypes, pathlib, sys
from playwright.sync_api import sync_playwright

HERE = pathlib.Path(__file__).parent
FON = HERE / "fontes"

def b64(p):
    return base64.b64encode(p.read_bytes()).decode()

INTER = b64(FON / "InterTight.ttf")
GEIST = b64(FON / "GeistMono.ttf")

TXT = {
    "en": {
        "eyebrow": "OPEN SOURCE · APACHE 2.0 · SECURITY",
        "m1": "A scan that didn&#8217;t run is not a clean scan.",
        "m2": "Zero findings has to prove it ran.",
        "desc": "Continuous security testing for regulated environments, from scan to AI fix.",
        "chips": "15 SCANNERS&nbsp;&nbsp;·&nbsp;&nbsp;AI TRIAGE&nbsp;&nbsp;·&nbsp;&nbsp;ONE COMMAND&nbsp;&nbsp;·&nbsp;&nbsp;v0.5.0",
    },
    "pt": {
        "eyebrow": "CÓDIGO ABERTO · APACHE 2.0 · SEGURANÇA",
        "m1": "Scan que não rodou não é scan limpo.",
        "m2": "Zero achado tem que provar que rodou.",
        "desc": "Teste de segurança contínuo para ambientes regulados, do scan ao fix por IA.",
        "chips": "15 SCANNERS&nbsp;&nbsp;·&nbsp;&nbsp;TRIAGEM IA&nbsp;&nbsp;·&nbsp;&nbsp;UM COMANDO&nbsp;&nbsp;·&nbsp;&nbsp;v0.5.0",
    },
}

# Arte à direita: escudo com anéis de varredura e feixe de luz.
ARTE = """
<g id="arte" transform="translate(2140,560)">
  <!-- feixe horizontal de dados -->
  <g opacity="0.95">
    <rect x="-820" y="-5" width="1040" height="10" fill="url(#beam)"/>
    <g fill="#7fb6ff">
      <rect x="-760" y="-3" width="26" height="6" opacity=".9"/>
      <rect x="-690" y="-9" width="10" height="10" opacity=".7"/>
      <rect x="-610" y="-2" width="34" height="5" opacity=".9"/>
      <rect x="-540" y="-11" width="12" height="12" opacity=".6"/>
      <rect x="-470" y="-3" width="20" height="6" opacity=".85"/>
    </g>
  </g>
  <!-- chão reflexivo -->
  <ellipse cx="0" cy="470" rx="620" ry="70" fill="url(#floor)"/>
  <!-- escudo -->
  <g filter="url(#glow)">
    <path d="M0,-440 L300,-330 L300,10 C300,230 170,380 0,470 C-170,380 -300,230 -300,10 L-300,-330 Z"
          fill="url(#glass)" stroke="#2a3a5a" stroke-width="3"/>
    <path d="M0,-440 L300,-330 L300,10 C300,230 170,380 0,470 C-170,380 -300,230 -300,10 L-300,-330 Z"
          fill="none" stroke="#4d9fff" stroke-width="2.5" opacity="0.55"/>
  </g>
  <!-- anéis de varredura -->
  <g fill="none" stroke="#4d9fff" opacity="0.9">
    <circle r="90" stroke-width="7"/>
    <circle r="165" stroke-width="3.5" opacity="0.55"/>
    <circle r="240" stroke-width="2.5" opacity="0.32"/>
  </g>
  <circle r="30" fill="#8fc2ff"/>
</g>
"""

def arte_raster(art_path):
    """Arte fotoreal do ChatGPT ocupando a metade direita, com fade pra esquerda."""
    p = pathlib.Path(art_path)
    mime = mimetypes.guess_type(p.name)[0] or "image/jpeg"
    data = base64.b64encode(p.read_bytes()).decode()
    return f"""
<g id="arte">
  <defs>
    <linearGradient id="fade" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="#07090f" stop-opacity="1"/>
      <stop offset="0.28" stop-color="#07090f" stop-opacity="0"/>
    </linearGradient>
  </defs>
  <image href="data:{mime};base64,{data}" x="1360" y="0" width="1840" height="1120"
         preserveAspectRatio="xMidYMid slice"/>
  <rect x="1360" y="0" width="1840" height="1120" fill="url(#fade)"/>
</g>
"""

def svg(lang, art):
    t = TXT[lang]
    arte = arte_raster(art) if art else ARTE
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="3200" height="1120" viewBox="0 0 3200 1120">
  <defs>
    <style>
      @font-face {{ font-family:'Inter Tight'; src:url(data:font/ttf;base64,{INTER}) format('truetype'); }}
      @font-face {{ font-family:'Geist Mono'; src:url(data:font/ttf;base64,{GEIST}) format('truetype'); }}
      .eye {{ font-family:'Geist Mono'; font-size:30px; letter-spacing:7px; fill:#4d9fff; }}
      .wm  {{ font-family:'Inter Tight'; font-weight:800; font-size:132px; }}
      .m   {{ font-family:'Inter Tight'; font-weight:700; font-size:66px; }}
      .desc{{ font-family:'Inter Tight'; font-weight:400; font-size:34px; fill:#8b97a6; }}
      .chip{{ font-family:'Geist Mono'; font-size:28px; letter-spacing:4px; fill:#6e7c8a; }}
    </style>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#0a0d13"/><stop offset="0.55" stop-color="#0b1018"/><stop offset="1" stop-color="#07090f"/>
    </linearGradient>
    <radialGradient id="halo" cx="0.68" cy="0.5" r="0.5">
      <stop offset="0" stop-color="#143055" stop-opacity="0.7"/><stop offset="1" stop-color="#143055" stop-opacity="0"/>
    </radialGradient>
    <linearGradient id="glass" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#12203a" stop-opacity="0.85"/><stop offset="1" stop-color="#0b1424" stop-opacity="0.6"/>
    </linearGradient>
    <linearGradient id="beam" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="#4d9fff" stop-opacity="0"/><stop offset="0.5" stop-color="#8fc2ff" stop-opacity="1"/><stop offset="1" stop-color="#4d9fff" stop-opacity="0.9"/>
    </linearGradient>
    <radialGradient id="floor" cx="0.5" cy="0.5" r="0.5">
      <stop offset="0" stop-color="#2060c0" stop-opacity="0.5"/><stop offset="1" stop-color="#2060c0" stop-opacity="0"/>
    </radialGradient>
    <filter id="glow" x="-50%" y="-50%" width="200%" height="200%">
      <feGaussianBlur stdDeviation="9" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
    <!-- marca: escudo pequeno do wordmark -->
    <g id="mark">
      <path d="M0,-6 L34,6 L34,44 C34,70 19,90 0,102 C-19,90 -34,70 -34,44 L-34,6 Z" fill="none" stroke="#007aff" stroke-width="7"/>
      <path d="M-15,44 L-3,60 L20,28" fill="none" stroke="#4d9fff" stroke-width="7" stroke-linecap="round" stroke-linejoin="round"/>
    </g>
  </defs>

  <rect width="3200" height="1120" fill="url(#bg)"/>
  <rect width="3200" height="1120" fill="url(#halo)"/>
  {arte}

  <!-- coluna esquerda -->
  <g transform="translate(170,300)">
    <line x1="0" y1="-14" x2="54" y2="-14" stroke="#007aff" stroke-width="4"/>
    <text class="eye" x="74" y="-2">{t['eyebrow']}</text>

    <g transform="translate(6,70)"><use href="#mark" transform="translate(0,2) scale(1.15)"/></g>
    <text class="wm" x="92" y="168"><tspan fill="#e9eef5">Roque</tspan><tspan fill="#2f8bff">Shield</tspan></text>

    <text class="m" x="2" y="300" fill="#e9eef5">{t['m1']}</text>
    <text class="m" x="2" y="378" fill="#9aa7b4">{t['m2']}</text>

    <text class="desc" x="2" y="452">{t['desc']}</text>

    <text class="chip" x="2" y="604">{t['chips']}</text>
  </g>
</svg>"""

def render(lang, outdir, art):
    html = f"<!doctype html><html><head><meta charset='utf-8'><style>html,body{{margin:0}}</style></head><body>{svg(lang, art)}</body></html>"
    hp = HERE / f"_banner.{lang}.html"
    hp.write_text(html, encoding="utf-8")
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width":3200,"height":1120}, device_scale_factor=1)
        pg.goto(hp.as_uri())
        pg.wait_for_timeout(400)
        png = HERE / f"banner.{lang}.png"
        pg.screenshot(path=str(png), clip={"x":0,"y":0,"width":3200,"height":1120})
        b.close()
    # PNG -> JPG qualidade alta
    from PIL import Image
    im = Image.open(png).convert("RGB")
    jpg = pathlib.Path(outdir) / f"banner.{lang}.jpg"
    im.save(jpg, "JPEG", quality=88, optimize=True, progressive=True)
    print(f"{jpg} {jpg.stat().st_size//1024}K {im.size}")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--art", help="arte raster (ex.: arte-scan.jpg gerada no ChatGPT)")
    ap.add_argument("--out", default=str(HERE), help="diretório de saída")
    a = ap.parse_args()
    for lang in ("en","pt"):
        render(lang, a.out, a.art)
