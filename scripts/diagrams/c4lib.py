"""
c4lib — primitivas de desenho C4 em SVG puro, na identidade RoqueOS.

Por que SVG escrito à mão e não graphviz/mermaid: diagrama de arquitetura que vale
a pena olhar tem posição pensada. Layout automático empurra caixa para onde couber,
e o leitor perde a única coisa que o desenho tinha para dar — a forma do sistema.
Aqui a posição é declarada, o estilo é um só, e o arquivo é regenerável.
"""

from __future__ import annotations

import html
import json as _json
import math
import os
from dataclasses import dataclass, field
from functools import lru_cache

# ---------------------------------------------------------------- temas

FONT = "Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"
MONO = "'SF Mono', 'JetBrains Mono', 'DejaVu Sans Mono', ui-monospace, Menlo, Consolas, monospace"

PALETTE = {
    "accent": "#007aff",  # RoqueOS --ros-accent
    "violet": "#5856d6",  # fim do gradiente da marca
    "rose": "#e11d48",  # cor do app RoqueShield no Launchpad
    "green": "#3fb950",  # --ros-success, escurecido para separar do teal do Kali
    "amber": "#f59e0b",  # --ros-warning
    "red": "#ff3b30",  # --ros-danger
    "cyan": "#22d3ee",
    "kali": "#00b3a4",
    "gray": "#8b949e",
}

DARK = {
    "name": "dark",
    "bg": "#0d1117",
    "bg_alt": "#111721",
    "ink": "#e6edf3",
    "ink_soft": "#9aa7b4",
    "ink_faint": "#6e7c8a",
    "node_fill": "#161b25",
    "node_stroke": "#2a3240",
    "boundary_fill": "#1b2130",
    "boundary_stroke": "#39414f",
    "edge": "#7d8996",
    "shadow": "0 0 0 rgba(0,0,0,0)",
    "shadow_op": 0.55,
    "pill_fill": "#1f2733",
}

LIGHT = {
    "name": "light",
    "bg": "#ffffff",
    "bg_alt": "#f6f8fa",
    "ink": "#1f2328",
    "ink_soft": "#57606a",
    "ink_faint": "#8c959f",
    "node_fill": "#ffffff",
    "node_stroke": "#d0d7de",
    "boundary_fill": "#f2f5f9",
    "boundary_stroke": "#c3cbd4",
    "edge": "#6e7781",
    "shadow_op": 0.10,
    "pill_fill": "#eef1f5",
}

# ---------------------------------------------------------------- texto

# Medida de texto por TABELA, não por fonte instalada.
#
# Duas versões anteriores erraram aqui, e as duas em silêncio:
#  1. estimativa por balde de caractere errava ~7% para baixo e o texto vazava a
#     caixa no render — defeito que só aparece olhando o PNG;
#  2. medir com PIL na fonte instalada consertou o vazamento e trouxe outro
#     problema: a mesma entrada gera SVG diferente em máquina sem a Inter, e aí
#     `--check` reprova por causa da máquina, não por causa do desenho.
#
# A tabela abaixo tem o avanço de cada caractere em unidades de 1000/em,
# extraído das fontes reais uma vez e versionado junto. Medida vira aritmética:
# determinística em qualquer máquina, e o gerador não depende de nada além da
# biblioteca padrão.
_AQUI = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(_AQUI, "metrics.json"), encoding="utf-8") as _f:
    _METRICS = _json.load(_f)
_UPM = _METRICS["upm"]
_FACES = _METRICS["faces"]
_FALLBACK = 520.0  # avanço de um caractere desconhecido; ~ a média da Inter


def _face(weight: int, mono: bool) -> dict:
    if mono:
        return _FACES["B" if weight >= 600 else "M"]
    if weight >= 700:
        return _FACES["b"]
    if weight >= 600:
        return _FACES["s"]
    if weight >= 500:
        return _FACES["m"]
    return _FACES["r"]


@lru_cache(maxsize=4096)
def _avanco(s: str, weight: int, mono: bool) -> float:
    f = _face(weight, mono)
    return sum(f.get(ch, _FALLBACK) for ch in s)


def text_width(
    s: str, size: float, spacing: float = 0.0, weight: int = 400, mono: bool = False
) -> float:
    if not s:
        return 0.0
    return _avanco(s, weight, mono) * size / _UPM + spacing * max(len(s) - 1, 0)


def wrap(s: str, size: float, max_w: float, weight: int = 400, mono: bool = False) -> list[str]:
    """Quebra por palavra respeitando a largura medida. Linha em branco sobrevive."""
    out: list[str] = []
    for para in s.split("\n"):
        if not para.strip():
            out.append("")
            continue
        line = ""
        for w in para.split():
            cand = f"{line} {w}".strip()
            if text_width(cand, size, weight=weight, mono=mono) <= max_w or not line:
                line = cand
            else:
                out.append(line)
                line = w
        out.append(line)
    while out and out[-1] == "":
        out.pop()
    return out or [""]


def esc(s: str) -> str:
    return html.escape(s, quote=True)


# ---------------------------------------------------------------- canvas


@dataclass
class Canvas:
    w: int
    h: int
    theme: dict
    body: list[str] = field(default_factory=list)
    defs: list[str] = field(default_factory=list)
    _grad: int = 0

    # -- infra -------------------------------------------------------
    def add(self, s: str) -> None:
        self.body.append(s)

    def slot(self) -> int:
        """Reserva uma posição na ordem de pintura.

        Fronteira precisa ficar ATRÁS das caixas, mas sua altura só é conhecida
        depois que as caixas foram colocadas. Sem isto, ou a fronteira sobra
        espaço vazio embaixo, ou é pintada por cima do conteúdo.
        """
        self.body.append("")
        return len(self.body) - 1

    def into(self, idx: int, fn, *a, **k):
        keep = self.body
        self.body = []
        out = fn(self, *a, **k)
        drawn, self.body = self.body, keep
        self.body[idx] = "".join(drawn)
        return out

    def gradient(self, c1: str, c2: str, x1=0, y1=0, x2=1, y2=1) -> str:
        self._grad += 1
        gid = f"g{self._grad}"
        self.defs.append(
            f'<linearGradient id="{gid}" x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}">'
            f'<stop offset="0%" stop-color="{c1}"/><stop offset="100%" stop-color="{c2}"/>'
            f"</linearGradient>"
        )
        return f"url(#{gid})"

    def render(self) -> str:
        t = self.theme
        head = (
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'xmlns:xlink="http://www.w3.org/1999/xlink" '
            f'width="{self.w}" height="{self.h}" viewBox="0 0 {self.w} {self.h}" '
            f'font-family="{FONT}">'
        )
        defs = (
            "<defs>"
            + "".join(self.defs)
            + f'<filter id="sh" x="-30%" y="-30%" width="160%" height="160%">'
            f'<feDropShadow dx="0" dy="2" stdDeviation="4" flood-color="#000" '
            f'flood-opacity="{t["shadow_op"]}"/></filter>'
            f'<marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" '
            f'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
            f'<path d="M 0 0 L 10 5 L 0 10 z" fill="{t["edge"]}"/></marker>'
            f'<marker id="arrowA" viewBox="0 0 10 10" refX="9" refY="5" '
            f'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
            f'<path d="M 0 0 L 10 5 L 0 10 z" fill="{PALETTE["accent"]}"/></marker>'
            f'<marker id="arrowR" viewBox="0 0 10 10" refX="9" refY="5" '
            f'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
            f'<path d="M 0 0 L 10 5 L 0 10 z" fill="{PALETTE["rose"]}"/></marker>'
            f'<marker id="arrowG" viewBox="0 0 10 10" refX="9" refY="5" '
            f'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
            f'<path d="M 0 0 L 10 5 L 0 10 z" fill="{PALETTE["green"]}"/></marker>'
            "</defs>"
        )
        bg = f'<rect width="{self.w}" height="{self.h}" fill="{t["bg"]}"/>'
        return head + defs + bg + "".join(self.body) + "</svg>"

    # -- texto -------------------------------------------------------
    def text(
        self,
        x,
        y,
        s,
        size=13,
        fill=None,
        weight=400,
        anchor="start",
        family=FONT,
        opacity=1.0,
        spacing=0.0,
    ):
        fill = fill or self.theme["ink"]
        ls = f' letter-spacing="{spacing}"' if spacing else ""
        op = f' opacity="{opacity}"' if opacity != 1.0 else ""
        self.add(
            f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" fill="{fill}" '
            f'font-weight="{weight}" text-anchor="{anchor}" font-family="{family}"'
            f"{ls}{op}>{esc(s)}</text>"
        )

    def para(
        self,
        x,
        y,
        s,
        size=12,
        fill=None,
        max_w=200,
        lh=1.45,
        anchor="start",
        weight=400,
        opacity=1.0,
    ) -> float:
        lines = wrap(s, size, max_w, weight=weight)
        for i, line in enumerate(lines):
            if not line:
                continue
            self.text(
                x,
                y + i * size * lh,
                line,
                size=size,
                fill=fill,
                weight=weight,
                anchor=anchor,
                opacity=opacity,
            )
        return y + (len(lines) - 1) * size * lh

    # -- formas ------------------------------------------------------
    def rect(
        self,
        x,
        y,
        w,
        h,
        r=10,
        fill="none",
        stroke="none",
        sw=1,
        dash=None,
        shadow=False,
        opacity=1.0,
    ):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        f = ' filter="url(#sh)"' if shadow else ""
        op = f' opacity="{opacity}"' if opacity != 1.0 else ""
        self.add(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{r}" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{d}{f}{op}/>'
        )

    def line(self, x1, y1, x2, y2, stroke=None, sw=1.5, dash=None, marker=None, opacity=1.0):
        stroke = stroke or self.theme["edge"]
        d = f' stroke-dasharray="{dash}"' if dash else ""
        m = f' marker-end="url(#{marker})"' if marker else ""
        op = f' opacity="{opacity}"' if opacity != 1.0 else ""
        self.add(
            f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
            f'stroke="{stroke}" stroke-width="{sw}" stroke-linecap="round"{d}{m}{op}/>'
        )

    def path(self, d, stroke=None, sw=1.5, fill="none", dash=None, marker=None, opacity=1.0):
        stroke = stroke or self.theme["edge"]
        da = f' stroke-dasharray="{dash}"' if dash else ""
        m = f' marker-end="url(#{marker})"' if marker else ""
        op = f' opacity="{opacity}"' if opacity != 1.0 else ""
        self.add(
            f'<path d="{d}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}" '
            f'stroke-linecap="round" stroke-linejoin="round"{da}{m}{op}/>'
        )

    def circle(self, cx, cy, r, fill="none", stroke="none", sw=1):
        self.add(
            f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" fill="{fill}" '
            f'stroke="{stroke}" stroke-width="{sw}"/>'
        )

    def pill(self, x, y, label, color, size=10, pad=12, h=20, filled=False):
        w = text_width(label, size, weight=600, mono=True) + pad * 2
        if filled:
            self.rect(x, y, w, h, r=h / 2, fill=color, opacity=0.16)
            self.rect(x, y, w, h, r=h / 2, fill="none", stroke=color, sw=1, opacity=0.5)
        else:
            self.rect(x, y, w, h, r=h / 2, fill=self.theme["pill_fill"])
        self.text(
            x + pad, y + h / 2 + size * 0.36, label, size=size, fill=color, weight=600, family=MONO
        )
        return w


# ---------------------------------------------------------------- C4


@dataclass
class Box:
    x: float
    y: float
    w: float
    h: float

    @property
    def cx(self):
        return self.x + self.w / 2

    @property
    def cy(self):
        return self.y + self.h / 2

    @property
    def top(self):
        return (self.cx, self.y)

    @property
    def bottom(self):
        return (self.cx, self.y + self.h)

    @property
    def left(self):
        return (self.x, self.cy)

    @property
    def right(self):
        return (self.x + self.w, self.cy)

    def pt(self, side: str, t: float = 0.5):
        if side == "top":
            return (self.x + self.w * t, self.y)
        if side == "bottom":
            return (self.x + self.w * t, self.y + self.h)
        if side == "left":
            return (self.x, self.y + self.h * t)
        if side == "right":
            return (self.x + self.w, self.y + self.h * t)
        raise ValueError(side)


def node_height(w, title, tech=None, desc=None, kind="container", r=12, pad_bottom=20) -> float:
    """Altura exata que o conteúdo pede. Caixa com rodapé vazio parece bug."""
    inner = w - (r + 14) - 18 - (24 if kind == "person" else 0)
    h = 24 + (len(wrap(title, 14.5, inner, weight=650)) - 1) * 19
    if tech:
        h += 17
    if desc:
        lines = wrap(desc, 11, inner)
        h += 18 + (len(lines) - 1) * 11 * 1.4 + 4
    return h + pad_bottom


def node(
    c: Canvas,
    x,
    y,
    w,
    h,
    title,
    tech=None,
    desc=None,
    color=None,
    kind="container",
    icon=None,
    r=12,
) -> Box:
    """Caixa C4: faixa de cor, nome, [tecnologia], descrição.

    h=None calcula a altura pelo conteúdo. h numérico é piso, nunca teto: se o
    texto pedir mais, a caixa cresce em vez de vazar.
    """
    t = c.theme
    color = color or PALETTE["accent"]
    need = node_height(w, title, tech, desc, kind, r)
    h = need if h is None else max(h, need)
    c.rect(x, y, w, h, r=r, fill=t["node_fill"], stroke=t["node_stroke"], sw=1, shadow=True)
    c.add(
        f'<path d="M {x:.1f} {y + r:.1f} A {r} {r} 0 0 1 {x + r:.1f} {y:.1f} '
        f'L {x + r:.1f} {y + h:.1f} A {r} {r} 0 0 1 {x:.1f} {y + h - r:.1f} Z" '
        f'fill="{color}" opacity="0.9"/>'
    )
    px = x + r + 14
    inner = w - (r + 14) - 18
    ty = y + 24
    if kind == "person":
        c.circle(px + 7, ty - 5, 6, fill=color, stroke="none")
        c.path(f"M {px} {ty + 7} q 7 -9 14 0", stroke=color, sw=2.4)
        px += 24
        inner -= 24
    lines = wrap(title, 14.5, inner, weight=650)
    for i, ln in enumerate(lines):
        c.text(px, ty + i * 19, ln, size=14.5, weight=650, fill=t["ink"])
    ty += (len(lines) - 1) * 19
    if tech:
        ty += 17
        c.text(px, ty, f"[{tech}]", size=10.5, fill=color, weight=600, family=MONO)
    if desc:
        ty += 18
        c.para(px, ty, desc, size=11, fill=t["ink_soft"], max_w=inner, lh=1.4)
    return Box(x, y, w, h)


def boundary(c: Canvas, x, y, w, h, label, sublabel=None, color=None, r=16):
    t = c.theme
    color = color or t["boundary_stroke"]
    c.rect(x, y, w, h, r=r, fill=t["boundary_fill"], stroke=color, sw=1.4, dash="7 6", opacity=0.95)
    c.text(
        x + 18,
        y + 24,
        label.upper(),
        size=10.5,
        weight=700,
        fill=color if color != t["boundary_stroke"] else t["ink_faint"],
        spacing=1.1,
        family=MONO,
    )
    if sublabel:
        c.text(
            x + w - 18, y + 24, sublabel, size=10.5, fill=t["ink_faint"], weight=400, anchor="end"
        )
    return Box(x, y, w, h)


def edge(
    c: Canvas,
    p1,
    p2,
    label=None,
    tech=None,
    color=None,
    dash=None,
    mid=None,
    label_side="above",
    marker="arrow",
    label_dx=0,
    label_dy=0,
):
    """Aresta reta ou em cotovelo. `mid` = lista de waypoints."""
    t = c.theme
    stroke = color or t["edge"]
    pts = [p1] + (mid or []) + [p2]
    d = f"M {pts[0][0]:.1f} {pts[0][1]:.1f} " + " ".join(
        f"L {p[0]:.1f} {p[1]:.1f}" for p in pts[1:]
    )
    c.path(d, stroke=stroke, sw=1.6, dash=dash, marker=marker)
    if label:
        a, b = (pts[len(pts) // 2 - 1], pts[len(pts) // 2]) if len(pts) > 2 else (p1, p2)
        mx, my = (a[0] + b[0]) / 2 + label_dx, (a[1] + b[1]) / 2 + label_dy
        size = 10.5
        lines = [label] + ([tech] if tech else [])
        wmax = max(
            [text_width(lines[0], size, weight=500)]
            + ([text_width(tech, 9.5, mono=True)] if tech else [])
        )
        bh = 16 + (13 if tech else 0)
        c.rect(mx - wmax / 2 - 7, my - bh / 2, wmax + 14, bh, r=5, fill=t["bg"], stroke="none")
        yy = my + (size * 0.36 if not tech else -1)
        c.text(mx, yy, label, size=size, fill=t["ink_soft"], anchor="middle", weight=500)
        if tech:
            c.text(mx, yy + 13, tech, size=9.5, fill=t["ink_faint"], anchor="middle", family=MONO)


def title_block(c: Canvas, title, subtitle=None, level=None, x=48, y=52):
    t = c.theme
    if level:
        w = c.pill(x, y - 30, level, PALETTE["rose"], size=10, h=20, filled=True)
        c.text(x, y + 26, title, size=25, weight=700, fill=t["ink"])
    else:
        c.text(x, y, title, size=25, weight=700, fill=t["ink"])
    if subtitle:
        c.para(
            x,
            y + (52 if level else 26),
            subtitle,
            size=12.5,
            fill=t["ink_soft"],
            max_w=c.w - x * 2 - 260,
        )


def legend(c: Canvas, x, y, items, title="Legenda", cols=1, box_w=250):
    t = c.theme
    rows = math.ceil(len(items) / cols)
    h = 34 + rows * 21 + 10
    c.rect(x, y, box_w, h, r=10, fill=t["bg_alt"], stroke=t["node_stroke"], sw=1)
    c.text(
        x + 14,
        y + 22,
        title.upper(),
        size=9.5,
        weight=700,
        fill=t["ink_faint"],
        spacing=1.1,
        family=MONO,
    )
    cw = (box_w - 28) / cols
    for i, (color, label) in enumerate(items):
        cxx = x + 14 + (i // rows) * cw
        cyy = y + 41 + (i % rows) * 21
        c.rect(cxx, cyy, 11, 11, r=3, fill=color)
        c.text(cxx + 19, cyy + 9.5, label, size=10.5, fill=t["ink_soft"])
    return h


def footer(c: Canvas, left, right=None, y=None):
    t = c.theme
    y = y or c.h - 22
    c.line(48, y - 18, c.w - 48, y - 18, stroke=t["node_stroke"], sw=1)
    c.text(48, y, left, size=10, fill=t["ink_faint"], family=MONO)
    if right:
        c.text(c.w - 48, y, right, size=10, fill=t["ink_faint"], anchor="end", family=MONO)


def brand(c: Canvas, x=None, y=42, text="RoqueShield"):
    """Marca no canto: gradiente da identidade RoqueOS."""
    t = c.theme
    x = c.w - 48 if x is None else x
    g = c.gradient(PALETTE["accent"], PALETTE["violet"])
    tw = text_width(text, 13)
    bw = tw + 44
    c.rect(x - bw, y - 16, bw, 26, r=13, fill=g, opacity=0.16)
    c.rect(x - bw, y - 16, bw, 26, r=13, fill="none", stroke=PALETTE["violet"], sw=1, opacity=0.45)
    c.circle(x - bw + 16, y - 3, 5.5, fill=g)
    c.text(x - 14, y + 1.5, text, size=13, weight=650, fill=t["ink"], anchor="end")


def row(c: Canvas, x, y, widths, specs, gap=24, align_h=True):
    """Uma linha de caixas com a mesma altura (a maior da linha).

    Alinhar a base evita o degrau que faz o leitor procurar significado numa
    diferença que é só de quantidade de texto.
    """
    hs = [
        node_height(w, s.get("title", ""), s.get("tech"), s.get("desc"), s.get("kind", "container"))
        for w, s in zip(widths, specs, strict=True)
    ]
    h = max(hs) if align_h else None
    boxes, cx = [], x
    for w, s, hh in zip(widths, specs, hs, strict=True):
        boxes.append(
            node(
                c,
                cx,
                y,
                w,
                h if align_h else hh,
                s.get("title", ""),
                s.get("tech"),
                s.get("desc"),
                s.get("color"),
                s.get("kind", "container"),
            )
        )
        cx += w + gap
    return boxes, y + (h if align_h else max(hs)) + gap


def stack_col(c: Canvas, x, y, w, specs, gap=20):
    """Uma coluna de caixas, cada uma com a altura do seu próprio conteúdo."""
    boxes = []
    for s in specs:
        b = node(
            c,
            x,
            y,
            w,
            None,
            s.get("title", ""),
            s.get("tech"),
            s.get("desc"),
            s.get("color"),
            s.get("kind", "container"),
        )
        boxes.append(b)
        y = b.y + b.h + gap
    return boxes, y


# ---------------------------------------------------------------- fluxo


def step(c: Canvas, x, y, w, n, title, desc=None, color=None, h=None, r=10, tone="solid"):
    """Passo numerado de um fluxo."""
    t = c.theme
    color = color or PALETTE["accent"]
    inner = w - 74
    need = 26 + (len(wrap(title, 13.5, inner, weight=650)) - 1) * 18
    if desc:
        need += 16 + (len(wrap(desc, 10.5, inner)) - 1) * 10.5 * 1.42
    need += 18
    h = need if h is None else max(h, need)
    if tone == "ghost":
        c.rect(x, y, w, h, r=r, fill="none", stroke=color, sw=1.3, dash="5 4")
    else:
        c.rect(x, y, w, h, r=r, fill=t["node_fill"], stroke=t["node_stroke"], sw=1, shadow=True)
        c.rect(x, y, 4, h, r=2, fill=color)
    c.circle(x + 30, y + 22, 13, fill=color, stroke="none")
    c.text(
        x + 30,
        y + 26.5,
        str(n),
        size=12,
        weight=700,
        anchor="middle",
        fill="#08111c" if c.theme["name"] == "dark" else "#ffffff",
    )
    ty = y + 26
    for i, ln in enumerate(wrap(title, 13.5, inner, weight=650)):
        c.text(x + 54, ty + i * 18, ln, size=13.5, weight=650, fill=t["ink"])
    ty += (len(wrap(title, 13.5, inner, weight=650)) - 1) * 18
    if desc:
        c.para(x + 54, ty + 16, desc, size=10.5, fill=t["ink_soft"], max_w=inner, lh=1.42)
    return Box(x, y, w, h)


def diamond(c: Canvas, cx, cy, w, h, label, color=None):
    t = c.theme
    color = color or PALETTE["amber"]
    c.path(
        f"M {cx} {cy - h / 2} L {cx + w / 2} {cy} L {cx} {cy + h / 2} L {cx - w / 2} {cy} Z",
        stroke=color,
        sw=1.5,
        fill=t["node_fill"],
    )
    for i, ln in enumerate(wrap(label, 10.5, w - 34)):
        c.text(
            cx,
            cy + 4 + (i - (len(wrap(label, 10.5, w - 34)) - 1) / 2) * 13,
            ln,
            size=10.5,
            anchor="middle",
            fill=t["ink"],
            weight=500,
        )
    return Box(cx - w / 2, cy - h / 2, w, h)


def chip(c: Canvas, x, y, w, label, sub=None, color=None, h=None, state="on"):
    """Fase de uma esteira."""
    t = c.theme
    color = color or PALETTE["accent"]
    h = h or (52 if not sub else 64)
    fill = t["node_fill"]
    c.rect(
        x,
        y,
        w,
        h,
        r=9,
        fill=fill,
        stroke=color if state == "on" else t["node_stroke"],
        sw=1.4 if state == "on" else 1,
        shadow=True,
    )
    c.rect(x, y, w, 3.5, r=2, fill=color)
    c.text(
        x + w / 2,
        y + (28 if sub else 31),
        label,
        size=12,
        weight=650,
        anchor="middle",
        fill=t["ink"],
    )
    if sub:
        c.text(x + w / 2, y + 46, sub, size=9.5, anchor="middle", fill=t["ink_faint"], family=MONO)
    return Box(x, y, w, h)


def table(c: Canvas, x, y, w, headers, rows, colw, color=None, title=None, rowh=None):
    """Tabela: quando a informação é comparação, caixa e seta atrapalham."""
    t = c.theme
    color = color or PALETTE["accent"]
    yy = y
    if title:
        c.text(
            x, yy + 14, title.upper(), size=10.5, weight=700, fill=color, spacing=1.1, family=MONO
        )
        yy += 30
    c.rect(x, yy, w, 30, r=6, fill=t["bg_alt"], stroke="none")
    cx = x + 12
    for hd, cw in zip(headers, colw, strict=True):
        c.text(cx, yy + 20, hd, size=10, weight=700, fill=t["ink_faint"], spacing=0.6, family=MONO)
        cx += cw
    yy += 30
    for i, r in enumerate(rows):
        hs = []
        for cell, cw in zip(r, colw, strict=True):
            hs.append(len(wrap(str(cell), 11, cw - 18)))
        rh = rowh or (12 + max(hs) * 16)
        if i % 2:
            c.rect(x, yy, w, rh, r=0, fill=t["bg_alt"], opacity=0.5)
        cx = x + 12
        for j, (cell, cw) in enumerate(zip(r, colw, strict=True)):
            fill = color if j == 0 else t["ink_soft"]
            wt = 600 if j == 0 else 400
            c.para(cx, yy + 18, str(cell), size=11, fill=fill, max_w=cw - 18, weight=wt, lh=1.42)
            cx += cw
        yy += rh
        c.line(x, yy, x + w, yy, stroke=t["node_stroke"], sw=0.8)
    return yy


# ---------------------------------------------------------------- wireframe


def window(c: Canvas, x, y, w, h, title, subtitle=None, accent=None):
    """Janela do RoqueOS: barra de título com os três botões e o nome do app."""
    t = c.theme
    accent = accent or PALETTE["rose"]
    c.rect(x, y, w, h, r=14, fill=t["bg_alt"], stroke=t["node_stroke"], sw=1.2, shadow=True)
    c.add(
        f'<path d="M {x} {y + 14} A 14 14 0 0 1 {x + 14} {y} L {x + w - 14} {y} '
        f'A 14 14 0 0 1 {x + w} {y + 14} L {x + w} {y + 40} L {x} {y + 40} Z" '
        f'fill="{t["node_fill"]}"/>'
    )
    c.line(x, y + 40, x + w, y + 40, stroke=t["node_stroke"], sw=1)
    for i, col in enumerate(("#ff5f57", "#febc2e", "#28c840")):
        c.circle(x + 20 + i * 17, y + 20, 5.5, fill=col)
    c.text(x + 80, y + 25, title, size=12.5, weight=650, fill=t["ink"])
    if subtitle:
        c.text(
            x + w - 16, y + 25, subtitle, size=10, fill=t["ink_faint"], anchor="end", family=MONO
        )
    return Box(x, y, w, h)


def side_item(c: Canvas, x, y, w, label, color, active=False):
    t = c.theme
    if active:
        c.rect(x, y, w, 30, r=8, fill=color, opacity=0.18)
        c.rect(x, y + 6, 3, 18, r=2, fill=color)
    c.circle(x + 18, y + 15, 4.5, fill=color if active else t["ink_faint"])
    c.text(
        x + 32,
        y + 19,
        label,
        size=11,
        weight=600 if active else 400,
        fill=t["ink"] if active else t["ink_soft"],
    )
    return y + 36


def sevbar(c: Canvas, x, y, w, dist, h=9):
    """Barra de severidade: crítico, alto, médio, baixo, info."""
    cols = [PALETTE["red"], "#ff7a45", PALETTE["amber"], "#8bc34a", PALETTE["gray"]]
    total = sum(dist) or 1
    cx = x
    for v, col in zip(dist, cols, strict=True):
        seg = w * v / total
        if seg > 0:
            c.rect(cx, y, max(seg, 2), h, r=h / 2, fill=col)
        cx += seg
    return y + h


def grade(c: Canvas, cx, cy, r, letter, color):
    c.add(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{color}" opacity="0.16"/>')
    c.circle(cx, cy, r, fill="none", stroke=color, sw=2)
    c.text(cx, cy + r * 0.36, letter, size=r * 1.05, weight=700, anchor="middle", fill=color)


def stepper(c: Canvas, x, y, w, fases, atual):
    t = c.theme
    n = len(fases)
    gap = w / (n - 1)
    c.line(x, y, x + w, y, stroke=t["node_stroke"], sw=2)
    c.line(x, y, x + gap * atual, y, stroke=PALETTE["accent"], sw=2)
    for i, f in enumerate(fases):
        cx = x + gap * i
        done, cur = i < atual, i == atual
        col = PALETTE["accent"] if done or cur else t["node_stroke"]
        c.circle(
            cx, y, 7 if cur else 5, fill=col if (done or cur) else t["bg_alt"], stroke=col, sw=1.6
        )
        if cur:
            c.circle(cx, y, 12, fill="none", stroke=col, sw=1.4)
        c.text(
            cx,
            y + 26,
            f,
            size=8.5,
            anchor="middle",
            family=MONO,
            fill=t["ink"] if cur else t["ink_faint"],
            weight=600 if cur else 400,
        )
    return y + 34


def ui_card(c: Canvas, x, y, w, h, title, body=None, color=None, badge=None):
    t = c.theme
    color = color or PALETTE["accent"]
    c.rect(x, y, w, h, r=10, fill=t["node_fill"], stroke=t["node_stroke"], sw=1)
    c.text(x + 14, y + 22, title, size=11.5, weight=650, fill=t["ink"])
    if badge:
        bw = text_width(badge, 9.5, weight=600, mono=True) + 16
        c.rect(x + w - 14 - bw, y + 9, bw, 18, r=9, fill=color, opacity=0.2)
        c.text(
            x + w - 14 - bw / 2,
            y + 22,
            badge,
            size=9.5,
            anchor="middle",
            fill=color,
            weight=600,
            family=MONO,
        )
    if body:
        c.para(x + 14, y + 42, body, size=10, fill=t["ink_soft"], max_w=w - 28)
    return Box(x, y, w, h)
