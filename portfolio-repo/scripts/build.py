#!/usr/bin/env python3
"""
build.py — the one script you run after editing anything in /data.

What it does:
  1. Reads data/theme.yaml           -> writes site/css/theme-vars.css
                                      -> writes latex/shared/theme.sty
  2. Reads data/title.yaml           -> writes site/data/title.json
                                      -> writes latex/shared/title.tex
  3. Reads data/main.yaml            -> writes site/data/main.json
                                         (homepage hero/about copy, optional
                                         highlight bullets, category order)
  4. Reads data/projects/<category>/*.yaml
                                      -> writes site/data/projects.json
                                         (grouped by category)
                                      -> writes latex/portfolio/sections/projects.tex
                                         (one \\section*{...} per category)
  5. Reads data/resume.yaml          -> writes latex/resume/sections/resume_content.tex
  6. Reads data/coverletter.yaml     -> writes latex/coverletter/sections/coverletter_content.tex
  7. Reads data/design-team.yaml and data/internships.yaml (if present)
                                      -> writes site/data/{design-team,internships}.json
                                      -> writes latex/portfolio/sections/{design-team,internships}.tex

Usage:
    python scripts/build.py            # regenerate everything
    python scripts/build.py --pdf      # also compile resume/portfolio/coverletter to PDF

PDF compilation calls `xelatex` directly (twice, for cross-references),
not latexmk — so it has no dependency on Perl, only a TeX Live/MacTeX
install that provides the `xelatex` binary on PATH.

Nothing in site/data/*.json or latex/*/sections/*.tex should be
hand-edited — they're regenerated every run and your edits will be lost.
"""

import argparse
import json
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SITE = ROOT / "site"
LATEX = ROOT / "latex"
PROJECT_TEMPLATES = LATEX / "portfolio" / "templates"
RESUME_TEMPLATES = LATEX / "resume" / "templates"
COVERLETTER_TEMPLATES = LATEX / "coverletter" / "templates"

VALID_BLOCK_TYPES = {"text", "photo", "gallery", "carousel", "video", "stl"}
VALID_VIDEO_PLAY_TYPES = {"automatic", "boomerang", "button", "once"}


def make_tex_env(template_dir: Path) -> Environment:
    """
    Jinja2 env with delimiters that don't collide with LaTeX's { } syntax.
    In .tex.j2 templates use:  (((variable)))   ((* for/if *))   ((= comment =))
    """
    env = Environment(
        loader=FileSystemLoader(str(template_dir)),
        block_start_string="((*",
        block_end_string="*))",
        variable_start_string="(((",
        variable_end_string=")))",
        comment_start_string="((=",
        comment_end_string="=))",
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["tex"] = escape_tex
    return env


def load_yaml(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def escape_tex(s) -> str:
    """Minimal LaTeX special-character escaping for plain text fields."""
    if s is None:
        return ""
    s = str(s)
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    out = []
    for ch in s:
        out.append(replacements.get(ch, ch))
    return "".join(out)


# ------------------------------------------------------------
# 1. THEME
# ------------------------------------------------------------

def build_theme():
    theme = load_yaml(DATA / "theme.yaml")
    colors = theme["colors"]
    fonts = theme["fonts"]
    layout = theme["layout"]
    radius = theme["radius"]
    type_scale = theme.get("type_scale", {})
    line_height = theme.get("line_height", {})
    media = theme.get("media", {})
    interaction = theme.get("interaction", {})

    def color_ref(name: str) -> str:
        return colors.get(name, name)

    css_lines = [":root {"]
    for name, hexval in colors.items():
        css_lines.append(f"  --color-{name}: {hexval};")
    css_lines.append(f"  --font-display: '{fonts['display']['family']}', sans-serif;")
    css_lines.append(f"  --font-body: '{fonts['body']['family']}', sans-serif;")
    css_lines.append(f"  --font-mono: '{fonts['mono']['family']}', monospace;")
    css_lines.append(f"  --content-max-width: {layout['content_max_width']};")
    css_lines.append(f"  --grid-unit: {layout['grid_unit']};")
    css_lines.append(f"  --radius-base: {radius['base']};")
    for key, sizes in type_scale.items():
        css_lines.append(f"  --text-{key.replace('_', '-')}: {sizes['site']};")
    css_lines.append(f"  --line-height-heading: {line_height.get('heading', 1.15)};")
    css_lines.append(f"  --line-height-body: {line_height.get('body', 1.6)};")
    border_enabled = media.get("border_enabled", False)
    border_color_hex = color_ref(media.get("border_color", "steel-700"))
    border_width = media.get("border_width", "1px")
    css_lines.append(f"  --media-frame-bg: {color_ref(media.get('frame_bg', 'paper'))};")
    css_lines.append(f"  --media-max-height: {media.get('max_height', '70vh')};")
    css_lines.append(f"  --media-border-color: {border_color_hex};")
    css_lines.append(f"  --media-border-width: {border_width};")
    css_lines.append(f"  --media-border-default: {border_width + ' solid ' + border_color_hex if border_enabled else 'none'};")
    css_lines.append(f"  --glow-color: {color_ref(interaction.get('glow_color', 'blueprint-500'))};")
    css_lines.append(f"  --glow-strength: {interaction.get('glow_strength', '0 0 0 3px')};")
    css_lines.append(f"  --hover-lift: {interaction.get('lift', '-3px')};")
    css_lines.append(f"  --hover-transition: {interaction.get('transition', '160ms ease')};")
    css_lines.append("}")
    css_out = SITE / "css" / "theme-vars.css"
    css_out.parent.mkdir(parents=True, exist_ok=True)
    css_out.write_text("\n".join(css_lines) + "\n", encoding="utf-8")
    print(f"  wrote {css_out.relative_to(ROOT)}")

    def hex_to_rgb(hexval: str):
        h = hexval.lstrip("#")
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))

    tex_lines = [
        "% AUTO-GENERATED by scripts/build.py from data/theme.yaml — do not hand-edit.",
        r"\NeedsTeXFormat{LaTeX2e}",
        r"\ProvidesPackage{theme}",
        r"\RequirePackage{xcolor}",
        r"\RequirePackage{fontspec}",
        "",
    ]
    for name, hexval in colors.items():
        r, g, b = hex_to_rgb(hexval)
        texname = name.replace("-", "")
        tex_lines.append(f"\\definecolor{{{texname}}}{{RGB}}{{{r},{g},{b}}}")
    tex_lines += [
        "",
        "% --- fonts: fall back to a widely-installed substitute if the",
        "% theme font isn't installed on this machine, so text is never",
        "% silently rendered invisible (fontspec's default failure mode).",
        "% Install the real fonts for the intended look — see README.md.",
        f"\\IfFontExistsTF{{{fonts['display']['family']}}}"
        f"{{\\newfontfamily\\displayfont{{{fonts['display']['family']}}}}}"
        f"{{\\newfontfamily\\displayfont{{DejaVu Sans}}\\ClassWarning{{theme}}"
        f"{{'{fonts['display']['family']}' not found, falling back to DejaVu Sans}}}}",
        f"\\IfFontExistsTF{{{fonts['mono']['family']}}}"
        f"{{\\newfontfamily\\monofont{{{fonts['mono']['family']}}}}}"
        f"{{\\newfontfamily\\monofont{{DejaVu Sans Mono}}\\ClassWarning{{theme}}"
        f"{{'{fonts['mono']['family']}' not found, falling back to DejaVu Sans Mono}}}}",
        f"\\IfFontExistsTF{{{fonts['body']['family']}}}"
        f"{{\\setmainfont{{{fonts['body']['family']}}}}}"
        f"{{\\setmainfont{{DejaVu Sans}}\\ClassWarning{{theme}}"
        f"{{'{fonts['body']['family']}' not found, falling back to DejaVu Sans}}}}",
        "",
        "% --- type scale (from data/theme.yaml type_scale:) — LaTeX size commands ---",
    ]
    for key, sizes in type_scale.items():
        camel = "".join(w.capitalize() for w in key.split("_"))
        tex_lines.append(f"\\newcommand{{\\text{camel}}}{{{sizes['pdf']}}}")

    tex_lines += [
        "",
        "% --- media framing (from data/theme.yaml media:) — computed here",
        "% so portfolio-macros.sty needs no runtime conditionals for the",
        "% border_enabled on/off toggle. Per-block background/border",
        "% overrides are a website-only feature (see README); the PDF",
        "% always uses these theme-wide defaults.",
    ]
    frame_color_name = media.get("frame_bg", "paper").replace("-", "")
    border_color_name = media.get("border_color", "steel-700").replace("-", "")
    tex_lines.append(f"\\newcommand{{\\mediaFrameColor}}{{{frame_color_name}}}")
    if border_enabled:
        tex_lines.append(f"\\newcommand{{\\mediaBorderColor}}{{{border_color_name}}}")
        tex_lines.append(r"\newcommand{\mediaBorderWidthVal}{0.6pt}")
    else:
        tex_lines.append(f"\\newcommand{{\\mediaBorderColor}}{{{frame_color_name}}}")
        tex_lines.append(r"\newcommand{\mediaBorderWidthVal}{0pt}")

    pdf_cfg = theme.get("pdf", {}) or {}
    pdf_bg_name = pdf_cfg.get("background", "paper").replace("-", "")
    pdf_text_name = pdf_cfg.get("text_color", "graphite-900").replace("-", "")
    tex_lines += [
        "",
        "% --- portfolio PDF page background / default text color (from",
        "% data/theme.yaml's pdf: block) — resume.tex and coverletter.tex",
        "% intentionally don't use these; they stay plain white. ---",
        f"\\newcommand{{\\pdfPageBgColor}}{{{pdf_bg_name}}}",
        f"\\newcommand{{\\pdfTextColor}}{{{pdf_text_name}}}",
    ]

    sty_out = LATEX / "shared" / "theme.sty"
    sty_out.parent.mkdir(parents=True, exist_ok=True)
    sty_out.write_text("\n".join(tex_lines) + "\n", encoding="utf-8")
    print(f"  wrote {sty_out.relative_to(ROOT)}")


# ------------------------------------------------------------
# 2. TITLE / CONTACT INFO
# ------------------------------------------------------------

def build_title():
    path = DATA / "title.yaml"
    if not path.exists():
        return
    title = load_yaml(path)

    json_out = SITE / "data" / "title.json"
    json_out.parent.mkdir(parents=True, exist_ok=True)
    json_out.write_text(json.dumps(title, indent=2), encoding="utf-8")
    print(f"  wrote {json_out.relative_to(ROOT)}")

    links = title.get("links", {})
    tex_lines = [
        "% AUTO-GENERATED by scripts/build.py from data/title.yaml — do not hand-edit.",
        r"\newcommand{\myName}{" + escape_tex(title.get("name", "")) + "}",
        r"\newcommand{\myTagline}{" + escape_tex(title.get("tagline", "")) + "}",
        r"\newcommand{\myLocation}{" + escape_tex(title.get("location", "")) + "}",
        r"\newcommand{\myEmail}{" + escape_tex(title.get("email", "")) + "}",
        r"\newcommand{\myPhone}{" + escape_tex(title.get("phone", "")) + "}",
        r"\newcommand{\myGithub}{" + escape_tex(links.get("github", "")) + "}",
        r"\newcommand{\myLinkedin}{" + escape_tex(links.get("linkedin", "")) + "}",
        r"\newcommand{\myWebsite}{" + escape_tex(links.get("website", "")) + "}",
    ]
    tex_out = LATEX / "shared" / "title.tex"
    tex_out.write_text("\n".join(tex_lines) + "\n", encoding="utf-8")
    print(f"  wrote {tex_out.relative_to(ROOT)}")


# ------------------------------------------------------------
# 3. MAIN PAGE CONFIG (data/main.yaml -> site/data/main.json)
# ------------------------------------------------------------

def load_main_config() -> dict:
    path = DATA / "main.yaml"
    if not path.exists():
        return {}
    return load_yaml(path) or {}


def build_main(main_cfg: dict, title: dict):
    if not (DATA / "main.yaml").exists():
        return

    hero = main_cfg.get("hero", {}) or {}
    lede = hero.get("lede", "") or ""
    lede = lede.replace("{location}", title.get("location", ""))

    highlights = main_cfg.get("highlights") or []
    if not isinstance(highlights, list):
        sys.exit("ERROR: data/main.yaml 'highlights' must be a list of short strings.")

    out = {
        "hero_lede": lede,
        "about_text": (main_cfg.get("about", {}) or {}).get("text", "") or "",
        "highlights": highlights,
    }
    json_out = SITE / "data" / "main.json"
    json_out.parent.mkdir(parents=True, exist_ok=True)
    json_out.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"  wrote {json_out.relative_to(ROOT)} ({len(highlights)} highlight(s))")


# ------------------------------------------------------------
# 4. PROJECTS — grouped by category subfolder
# ------------------------------------------------------------

def validate_project(proj: dict, path: Path):
    required = ["slug", "title", "short_description"]
    for key in required:
        if key not in proj:
            sys.exit(f"ERROR: {path.name} is missing required field '{key}'")
    blocks = proj.get("blocks", [])
    if not isinstance(blocks, list):
        sys.exit(f"ERROR: {path.name} 'blocks' must be a list (each entry starting with '-').")
    for block in blocks:
        if not isinstance(block, dict):
            sys.exit(f"ERROR: {path.name} has a blocks: entry that isn't a mapping — check its indentation.")
        if block.get("type") not in VALID_BLOCK_TYPES:
            sys.exit(
                f"ERROR: {path.name} has block type '{block.get('type')}' — "
                f"must be one of {sorted(VALID_BLOCK_TYPES)}"
            )
        if block["type"] in ("gallery", "carousel") and "items" not in block:
            sys.exit(f"ERROR: {path.name} {block['type']} block is missing 'items'")
        if block["type"] == "video" and "play_type" in block:
            if block["play_type"] not in VALID_VIDEO_PLAY_TYPES:
                sys.exit(
                    f"ERROR: {path.name} video block has play_type '{block['play_type']}' — "
                    f"must be one of {sorted(VALID_VIDEO_PLAY_TYPES)}"
                )
    preview = proj.get("preview_image")
    if preview is not None and not isinstance(preview, dict):
        sys.exit(
            f"ERROR: {path.name} 'preview_image' must be a single mapping, not a list — "
            f"check for a stray '-' under preview_image: (it holds exactly one image, "
            f"with at least a 'src')."
        )
    if preview is not None and "src" not in preview:
        sys.exit(f"ERROR: {path.name} 'preview_image' is missing 'src'")

    extra_fields = proj.get("extra_fields")
    if extra_fields is not None:
        if not isinstance(extra_fields, list):
            sys.exit(f"ERROR: {path.name} 'extra_fields' must be a list of {{label, value}} entries.")
        for f in extra_fields:
            if not isinstance(f, dict) or "label" not in f or "value" not in f:
                sys.exit(f"ERROR: {path.name} each extra_fields entry needs both 'label' and 'value'.")


def default_category_label(slug: str) -> str:
    return slug.replace("-", " ").replace("_", " ").title()


def load_portfolio_pdf_config() -> dict:
    path = DATA / "portfolio-pdf.yaml"
    if not path.exists():
        return {}
    return load_yaml(path) or {}


BIG_MEDIA_TYPES = ("photo", "video", "stl")
# Relative "how much vertical space does this block tend to take"
# weights, used only to size the *big* (photo/video/stl) blocks in a
# project sensibly around whatever else is already on the page — a
# gallery/carousel takes real space too even though it isn't resized
# itself (it's already a fixed small grid), so it still has to count
# against the big blocks' shared allotment or they end up oversized
# and spill onto a near-empty extra page.
SIZING_WEIGHTS = {"photo": 1.0, "video": 1.0, "stl": 1.0, "gallery": 0.5, "carousel": 0.5}


def annotate_project_pdf_sizing(proj: dict, sizing_cfg: dict):
    """
    Computes a `pdf_height` (a literal LaTeX length string, e.g.
    "0.450\\textheight") for every photo/video/stl block in a project,
    and for its preview_image, writing it directly onto each block dict
    so the Jinja template can drop it straight into \\projectPhoto /
    \\projectInteractiveFallback without doing any math itself.

    In "dynamic" mode, a project with only one big block and nothing
    else space-hungry gets close to the full max_height_frac allotment
    (so it fills the page instead of leaving whitespace before the next
    project's forced page break); a project with several big blocks —
    or a gallery/carousel alongside a big block — splits the allotment
    down, floored at min_height_frac, so the extra content has room and
    doesn't push a block onto its own near-empty overflow page.
    "fixed" mode always uses max_height_frac. A block's own
    `pdf_height_frac` (if set in its YAML) always wins over either.
    """
    mode = sizing_cfg.get("mode", "dynamic")
    max_frac = float(sizing_cfg.get("max_height_frac", 0.62))
    min_frac = float(sizing_cfg.get("min_height_frac", 0.28))

    blocks = proj.get("blocks", []) or []
    weight = sum(SIZING_WEIGHTS.get(b.get("type"), 0) for b in blocks)
    weight = max(1.0, weight)

    if mode == "fixed" or weight <= 1.0:
        computed_frac = max_frac
    else:
        computed_frac = max(min_frac, max_frac / weight)

    def sized(block_type: str, explicit_frac):
        # Scales width down along with height (most placeholder/demo
        # photos are landscape, where a fixed 0.85\linewidth width was
        # actually the binding constraint regardless of the height cap
        # — so capping height alone did nothing for those; the image
        # just spilled onto its own mostly-empty page instead of
        # shrinking). Scaling width by the same ratio makes the height
        # cap actually take effect.
        frac = explicit_frac if explicit_frac is not None else computed_frac
        ratio = (float(frac) / max_frac) if max_frac else 1.0
        base_width = 0.85 if block_type == "photo" else 0.70
        min_width = 0.40 if block_type == "photo" else 0.35
        width_frac = max(min_width, base_width * ratio)
        return f"{float(frac):.3f}\\textheight", f"{width_frac:.3f}\\linewidth"

    for b in blocks:
        if b.get("type") in BIG_MEDIA_TYPES:
            height, width = sized(b["type"], b.get("pdf_height_frac"))
            b["pdf_height"] = height
            b["pdf_width"] = width

    preview = proj.get("preview_image")
    if preview:
        height, width = sized("photo", preview.get("pdf_height_frac", max_frac))
        preview["pdf_height"] = height
        preview["pdf_width"] = width

    # Gallery/carousel items all use the SAME fixed height (unlike the
    # dynamic photo/video/stl sizing above) so a portrait photo next to
    # landscape ones doesn't tower over the rest of the row — every
    # tile in a gallery is a uniform, letterboxed box. needspace gets a
    # little extra padding for the heading + caption lines so the whole
    # row moves to a fresh page together instead of splitting mid-row.
    gallery_frac = float(sizing_cfg.get("gallery_item_height_frac", 0.16))
    gallery_height = f"{gallery_frac:.3f}\\textheight"
    gallery_needspace = f"\\dimexpr {gallery_frac:.3f}\\textheight+3\\baselineskip\\relax"
    for b in blocks:
        if b.get("type") in ("gallery", "carousel"):
            b["gallery_item_height"] = gallery_height
            b["gallery_needspace"] = gallery_needspace


def project_site_url(slug: str, website_base: str) -> str:
    if not website_base:
        return ""
    return f"{website_base.rstrip('/')}/project.html?slug={slug}"


def build_projects(main_cfg: dict, pdf_cfg: dict, title: dict):
    proj_root = DATA / "projects"
    if not proj_root.exists():
        sys.exit("ERROR: data/projects/ is missing.")

    category_cfg = main_cfg.get("project_categories", {}) or {}
    order = category_cfg.get("order") or []
    labels = category_cfg.get("labels") or {}
    project_order = category_cfg.get("project_order") or {}

    category_dirs = [d for d in proj_root.iterdir() if d.is_dir()]
    if not category_dirs:
        sys.exit(
            "ERROR: data/projects/ has no category subfolders. Projects now live under "
            "data/projects/<category>/<slug>.yaml — e.g. data/projects/professional/my-project.yaml. "
            "See README.md."
        )

    def sort_key(d: Path):
        if d.name in order:
            return (0, order.index(d.name))
        return (1, d.name)

    category_dirs.sort(key=sort_key)

    def order_projects(cat_name: str, projects: list) -> list:
        wanted = project_order.get(cat_name)
        if not wanted:
            return projects  # already alphabetical-by-filename from the glob below
        by_slug = {p["slug"]: p for p in projects}
        ordered = [by_slug.pop(slug) for slug in wanted if slug in by_slug]
        # anything not explicitly listed is appended afterward, alphabetically
        ordered += sorted(by_slug.values(), key=lambda p: p["slug"])
        return ordered

    website_base = ((title.get("links") or {}).get("website") or "").strip()
    sizing_cfg = (pdf_cfg.get("layout", {}) or {}).get("image_sizing", {}) or {}
    new_page_per_project = (pdf_cfg.get("layout", {}) or {}).get("new_page_per_project", True)

    categories = []
    for cat_dir in category_dirs:
        label = labels.get(cat_dir.name, default_category_label(cat_dir.name))
        projects = []
        for yml_path in sorted(cat_dir.glob("*.yaml")):
            proj = load_yaml(yml_path)
            validate_project(proj, yml_path)
            proj["pdf_url"] = project_site_url(proj["slug"], website_base)
            annotate_project_pdf_sizing(proj, sizing_cfg)
            projects.append(proj)
        projects = order_projects(cat_dir.name, projects)
        categories.append({"slug": cat_dir.name, "label": label, "projects": projects})

    # --- site JSON: list of {slug, label, projects: [...]} groups, in order ---
    # (pdf_url / pdf_height are PDF-only concerns — strip them back out so
    # they don't leak into the website's data file.)
    PDF_ONLY_KEYS = ("pdf_height", "pdf_width", "gallery_item_height", "gallery_needspace")

    def strip_pdf_fields(proj: dict) -> dict:
        clean = {k: v for k, v in proj.items() if k != "pdf_url"}
        if clean.get("preview_image"):
            clean["preview_image"] = {
                k: v for k, v in clean["preview_image"].items() if k not in PDF_ONLY_KEYS
            }
        clean["blocks"] = [
            {k: v for k, v in b.items() if k not in PDF_ONLY_KEYS} for b in clean.get("blocks", [])
        ]
        return clean

    json_out = SITE / "data" / "projects.json"
    json_out.parent.mkdir(parents=True, exist_ok=True)
    site_categories = [
        {"slug": c["slug"], "label": c["label"], "projects": [strip_pdf_fields(p) for p in c["projects"]]}
        for c in categories
    ]
    json_out.write_text(json.dumps(site_categories, indent=2), encoding="utf-8")
    total = sum(len(c["projects"]) for c in categories)
    print(f"  wrote {json_out.relative_to(ROOT)} ({total} project(s) across {len(categories)} categor{'y' if len(categories) == 1 else 'ies'})")

    # --- LaTeX projects.tex: one \section*{label} per non-empty category,
    # followed by that category's project blocks in order. Each category
    # after the first, and each project after the first in its category,
    # starts on its own page when new_page_per_project is true. ---
    env = make_tex_env(PROJECT_TEMPLATES)
    template = env.get_template("project_block.tex.j2")

    nonempty = [c for c in categories if c["projects"]]
    category_chunks = []
    for cat_idx, cat in enumerate(nonempty):
        project_chunks = []
        for proj_idx, p in enumerate(cat["projects"]):
            chunk = template.render(p=p)
            if new_page_per_project and proj_idx > 0:
                chunk = "\\newpage\n" + chunk
            project_chunks.append(chunk)
        cat_block = f"\\section*{{{escape_tex(cat['label'])}}}\n" + "\n".join(project_chunks)
        if new_page_per_project and cat_idx > 0:
            cat_block = "\\newpage\n" + cat_block
        category_chunks.append(cat_block)
    rendered = "\n\n".join(category_chunks)

    tex_out = LATEX / "portfolio" / "sections" / "projects.tex"
    tex_out.parent.mkdir(parents=True, exist_ok=True)
    header = (
        "% AUTO-GENERATED by scripts/build.py from data/projects/<category>/*.yaml\n"
        "% Do not hand-edit — edit the YAML files instead and re-run the build.\n\n"
    )
    tex_out.write_text(header + rendered + "\n", encoding="utf-8")
    print(f"  wrote {tex_out.relative_to(ROOT)}")


# ------------------------------------------------------------
# 4b. PORTFOLIO PDF TITLE PAGE
# ------------------------------------------------------------

def build_title_page(pdf_cfg: dict, main_cfg: dict, title: dict):
    title_page_cfg = pdf_cfg.get("title_page", {}) or {}
    show_hero = title_page_cfg.get("show_hero", True)
    hero_image = title_page_cfg.get("hero_image") if show_hero else None

    hero_lede = title_page_cfg.get("hero_lede") if show_hero else None
    if show_hero and not hero_lede:
        raw = (main_cfg.get("hero", {}) or {}).get("lede", "") or ""
        hero_lede = raw.replace("{location}", title.get("location", "")) if raw else None

    show_highlights = show_hero and title_page_cfg.get("show_highlights", True)
    highlights = (main_cfg.get("highlights") or []) if show_highlights else []

    env = make_tex_env(PROJECT_TEMPLATES)
    template = env.get_template("title_page.tex.j2")
    rendered = template.render(
        show_hero=show_hero,
        hero_image=hero_image,
        hero_lede=hero_lede,
        highlights=highlights,
    )
    tex_out = LATEX / "portfolio" / "sections" / "title-page.tex"
    tex_out.parent.mkdir(parents=True, exist_ok=True)
    header = (
        "% AUTO-GENERATED by scripts/build.py from data/portfolio-pdf.yaml + data/main.yaml\n"
        "% Do not hand-edit — edit the YAML instead and re-run the build.\n\n"
    )
    tex_out.write_text(header + rendered + "\n", encoding="utf-8")
    print(f"  wrote {tex_out.relative_to(ROOT)} (hero {'on' if show_hero else 'off'})")


# ------------------------------------------------------------
# 5. OPTIONAL SECTIONS (design team / internships)
# ------------------------------------------------------------

def build_simple_section(data_file: str, template_name: str, tex_out_name: str, json_out_name: str):
    path = DATA / data_file
    if not path.exists():
        return
    entries = load_yaml(path)

    json_out = SITE / "data" / json_out_name
    json_out.write_text(json.dumps(entries, indent=2), encoding="utf-8")
    print(f"  wrote {json_out.relative_to(ROOT)}")

    env = make_tex_env(PROJECT_TEMPLATES)
    template = env.get_template(template_name)
    rendered = template.render(entries=entries)
    tex_out = LATEX / "portfolio" / "sections" / tex_out_name
    header = f"% AUTO-GENERATED by scripts/build.py from data/{data_file} — do not hand-edit.\n\n"
    tex_out.write_text(header + rendered + "\n", encoding="utf-8")
    print(f"  wrote {tex_out.relative_to(ROOT)}")


def build_media():
    """
    Copies media/ -> site/media/ so the site always has a real, working
    copy of your media regardless of how the repo was obtained.
    """
    src = ROOT / "media"
    dst = SITE / "media"
    if not src.exists():
        return
    if dst.is_symlink() or dst.is_file():
        dst.unlink()
    elif dst.is_dir():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    print(f"  copied {src.relative_to(ROOT)} -> {dst.relative_to(ROOT)}")


# ------------------------------------------------------------
# 6. RESUME
# ------------------------------------------------------------

def build_resume():
    path = DATA / "resume.yaml"
    if not path.exists():
        return
    resume = load_yaml(path)
    config = resume.get("config", {})
    sections = resume.get("sections", [])

    json_out = SITE / "data" / "resume.json"
    json_out.parent.mkdir(parents=True, exist_ok=True)
    json_out.write_text(json.dumps(resume, indent=2), encoding="utf-8")
    print(f"  wrote {json_out.relative_to(ROOT)}")

    env = make_tex_env(RESUME_TEMPLATES)
    template = env.get_template("resume_content.tex.j2")
    rendered = template.render(sections=sections, config=config)
    tex_out = LATEX / "resume" / "sections" / "resume_content.tex"
    tex_out.parent.mkdir(parents=True, exist_ok=True)
    header = (
        "% AUTO-GENERATED by scripts/build.py from data/resume.yaml\n"
        "% Do not hand-edit — edit the YAML instead and re-run the build.\n\n"
    )
    tex_out.write_text(header + rendered + "\n", encoding="utf-8")
    print(f"  wrote {tex_out.relative_to(ROOT)}")


# ------------------------------------------------------------
# 7. COVER LETTER
# ------------------------------------------------------------

def build_coverletter():
    path = DATA / "coverletter.yaml"
    if not path.exists():
        return
    cl = load_yaml(path)

    date_str = cl.get("date", "auto")
    if date_str == "auto":
        d = date.today()
        date_str = f"{d:%B} {d.day}, {d.year}"

    env = make_tex_env(COVERLETTER_TEMPLATES)
    template = env.get_template("coverletter_content.tex.j2")
    rendered = template.render(
        recipient=cl.get("recipient", {}) or {},
        date=date_str,
        body=cl.get("body", []) or [],
        closing=cl.get("closing", "Sincerely,"),
    )
    tex_out = LATEX / "coverletter" / "sections" / "coverletter_content.tex"
    tex_out.parent.mkdir(parents=True, exist_ok=True)
    header = (
        "% AUTO-GENERATED by scripts/build.py from data/coverletter.yaml\n"
        "% Do not hand-edit — edit the YAML instead and re-run the build.\n\n"
    )
    tex_out.write_text(header + rendered + "\n", encoding="utf-8")
    print(f"  wrote {tex_out.relative_to(ROOT)}")


# ------------------------------------------------------------
# 8. PDF COMPILATION — xelatex directly, no latexmk/Perl dependency
# ------------------------------------------------------------

def compile_pdf(tex_path: Path, passes: int = 2):
    """
    Compiles tex_path to PDF by invoking `xelatex` directly, `passes`
    times in a row (two is enough to resolve hyperref cross-references
    and the titlerule spacing in these documents; there's no TOC or
    bibliography here that would need a third pass).

    Deliberately does NOT use latexmk: latexmk is a Perl script, and on
    some machines (locked-down corporate laptops, some CI images) Perl
    isn't available or is a hassle to add even though a TeX Live
    install already provides `xelatex`. Calling xelatex straight avoids
    that dependency entirely.
    """
    if shutil.which("xelatex") is None:
        sys.exit(
            "ERROR: 'xelatex' not found on PATH. Install TeX Live or MacTeX "
            "(see README.md) — no other tool is required to build the PDFs."
        )
    workdir = tex_path.parent
    for i in range(passes):
        result = subprocess.run(
            ["xelatex", "-interaction=nonstopmode", "-halt-on-error", tex_path.name],
            cwd=workdir,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            tail = "\n".join(result.stdout.splitlines()[-40:])
            sys.exit(
                f"ERROR: xelatex failed compiling {tex_path.name} "
                f"(pass {i + 1}/{passes}):\n{tail}"
            )
    pdf_path = tex_path.with_suffix(".pdf")
    print(f"  compiled {tex_path.relative_to(ROOT)} -> {pdf_path.relative_to(ROOT)}")


def sync_pdfs_to_site():
    """
    Copies whichever compiled PDFs already exist (from any previous
    --pdf run) into site/, so the site's Resume/Portfolio nav links
    (site/js/site-chrome.js, reading title.yaml's resume_pdf /
    portfolio_pdf) point at real files. Runs on every build, not just
    --pdf ones, so a plain `python scripts/build.py` after editing
    content still refreshes the copies already sitting in latex/.
    """
    mapping = {
        LATEX / "resume" / "resume.pdf": SITE / "resume.pdf",
        LATEX / "portfolio" / "portfolio.pdf": SITE / "portfolio.pdf",
    }
    for src, dst in mapping.items():
        if src.exists():
            shutil.copy2(src, dst)
            print(f"  copied {src.relative_to(ROOT)} -> {dst.relative_to(ROOT)}")


def build_pdfs():
    print("Compiling PDFs (xelatex, no Perl required)...")
    for tex_rel in (
        "resume/resume.tex",
        "portfolio/portfolio.tex",
        "coverletter/coverletter.tex",
    ):
        tex_path = LATEX / tex_rel
        if tex_path.exists():
            compile_pdf(tex_path)
        else:
            print(f"  skipping {tex_rel} (not found)")


# ------------------------------------------------------------
# MAIN
# ------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--pdf", action="store_true",
        help="also compile resume.tex, portfolio.tex, and coverletter.tex to PDF via xelatex",
    )
    args = parser.parse_args()

    print("Building theme...")
    build_theme()

    print("Building title/contact info...")
    build_title()
    title = load_yaml(DATA / "title.yaml") if (DATA / "title.yaml").exists() else {}

    print("Building main page config...")
    main_cfg = load_main_config()
    build_main(main_cfg, title)

    print("Loading portfolio PDF config...")
    pdf_cfg = load_portfolio_pdf_config()

    print("Building portfolio PDF title page...")
    build_title_page(pdf_cfg, main_cfg, title)

    print("Building projects...")
    build_projects(main_cfg, pdf_cfg, title)

    print("Building resume...")
    build_resume()

    print("Building cover letter...")
    build_coverletter()

    print("Syncing media...")
    build_media()

    print("Building optional sections...")
    build_simple_section("design-team.yaml", "simple_entry_block.tex.j2", "design-team.tex", "design-team.json")
    build_simple_section("internships.yaml", "simple_entry_block.tex.j2", "internships.tex", "internships.json")

    if args.pdf:
        build_pdfs()

    print("Syncing compiled PDFs to site/...")
    sync_pdfs_to_site()

    print("Done.")


if __name__ == "__main__":
    main()
