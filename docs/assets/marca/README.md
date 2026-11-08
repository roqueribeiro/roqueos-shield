# Marca do RoqueShield

Identidade visual do repositório, no mesmo padrão do `aidlc-harness`.

- `banner.en.jpg`, `banner.pt.jpg` — herói do README (3200×1120). Gerados por
  `gen.py`: arte à direita + overlay de texto à esquerda.
- `gen.py` — compositor. `python gen.py` desenha a arte em SVG; `python gen.py
  --art arte-scan.jpg` usa a arte fotoreal do ChatGPT (ver `PROMPT.md`).
- `carimbo.json` — chips e lema, em EN e PT, fonte única desses textos.
- `fontes/` — Inter Tight (títulos) e Geist Mono (mono), OFL, com as licenças.
- `PROMPT.md` — como gerar a arte fotoreal e trocar sem mexer no texto.

Paleta: fundo `#07090f`–`#0b1018`, azul de destaque `#2f8bff` / `#007aff`,
texto `#e9eef5`, apagado `#9aa7b4`. A mesma dos diagramas em `docs/assets/diagrams`.
