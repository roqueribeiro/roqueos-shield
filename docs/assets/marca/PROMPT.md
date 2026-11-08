# Arte do banner (padrão RoqueOS)

O banner do README é **arte + overlay de texto**, o mesmo processo do
`aidlc-harness`. O overlay (eyebrow, wordmark, lema, descritor, chips) é
desenhado por `gen.py`; a arte da direita é a única parte gerada no ChatGPT.

Hoje `gen.py` desenha a arte em SVG (escudo com anéis de varredura e feixe).
Para trocar pela arte fotoreal:

1. Gere a arte no ChatGPT com o prompt abaixo (proporção 3:2, ~1536×1024).
2. Salve como `docs/assets/marca/arte-scan.jpg`.
3. Regere os banners com a arte por baixo e o mesmo texto por cima:

   ```bash
   python docs/assets/marca/gen.py --art docs/assets/marca/arte-scan.jpg \
          --out docs/assets/marca
   ```

Precisa de Python com `playwright` e `Pillow` (o Chromium do playwright já
basta). As fontes ficam em `fontes/` (Inter Tight + Geist Mono, OFL).

## Prompt do ChatGPT (imagem)

> A 3:2 cinematic 3D render for a security product banner, on a near-black
> deep-navy background (#07090f to #0b1018), lit from the right. Center-right:
> a single large translucent glass shield, frosted dark-blue glass with a thin
> glowing azure rim (#2f8bff), standing upright on a dark reflective floor with
> a soft blue reflection beneath it. Through the shield runs a horizontal beam
> of bright azure light made of small glowing data particles, entering from the
> left and converging to a bright focal point at the center of the shield,
> where three concentric glowing scan rings pulse outward. Minimal, premium,
> lots of negative space on the left half (text goes there, keep it empty and
> dark). No text, no logos, no words anywhere in the image. Subtle depth of
> field, clean studio lighting, high detail. Palette: black, deep navy, and a
> single azure blue accent only.

Regras: sem texto na imagem (o texto é overlay), metade esquerda vazia e
escura, só o azul `#2f8bff` como cor de destaque, para casar com os diagramas
e com o `aidlc-harness`.
