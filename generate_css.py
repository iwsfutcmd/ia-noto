from collections import defaultdict, namedtuple
from sys import maxunicode
import subprocess

import unicodedataplus as unicodedata
from more_itertools import consecutive_groups
from fontTools.ttLib import TTFont
from tqdm import tqdm

from ia_noto import pathset


# def build_fallbacks():
#     fallbacks = set()

#     with open("fallback") as f:
#         for line in f.read().replace("\n", " > ").split(";"):
#             fallback = line.strip().replace("  ", " ").split(" > ")
#             fallbacks.add(frozenset(fallback))

#     return fallbacks


def build_fallback(fallback_filename):
    with open(fallback_filename) as f:
        fallback = [l.strip() for l in f.readlines()]
    return fallback


def extract_family_and_style(name_table):
    family = style = backup_family = backup_style = ""
    for record in name_table:
        if record.nameID == 1:
            backup_family = record.toUnicode()
        elif record.nameID == 2:
            backup_style = record.toUnicode()
        elif record.nameID == 16:
            family = record.toUnicode()
        elif record.nameID == 17:
            style = record.toUnicode()
        if family and style:
            break
    if not family:
        family = backup_family
    if not style:
        style = backup_style
    return (family, style)


Font = namedtuple(
    "Font",
    [
        "stem",
        "suffix",
        "family",
        "style",
        "variable",
        "weight",
        "width",
        "italic",
        "cmap",
    ],
)

width_conv = [
    "",
    "ultra-condensed",
    "extra-condensed",
    "condensed",
    "semi-condensed",
    "normal",
    "semi-expanded",
    "expanded",
    "extra-expanded",
    "ultra-expanded",
]

def prepare_fontlist():
    fontlist = []
    for path in tqdm(pathset):
        ttf = TTFont(path)
        stem = path.stem
        suffix = path.suffix
        family, style = extract_family_and_style(ttf["name"].names)
        variable = "-VF" in stem
        weight = ttf["OS/2"].usWeightClass
        width = width_conv[ttf["OS/2"].usWidthClass]
        italic = ttf["OS/2"].fsSelection >> 0 & 1
        cmap = set(ttf.getBestCmap().keys())
        fontlist.append(
            Font(
                stem, suffix, family, style, variable, weight, width, italic, cmap,
            )
        )
    return fontlist

def prepare_nonunique(panfont_cmap, fallbacks):
    nonunique = []
    for k, v in panfont_cmap.items():
        if len(v) == 1:
            continue
        families = {f[0] for f in v}
        found = False
        for fallback in fallbacks:
            if families <= fallback:
                found = True
        if not found:
            nonunique.append((unicodedata.name(chr(k), ""), k, families))
    nonunique = sorted(nonunique, key=lambda x: x[1])
    return nonunique

def build_unicode_range(cp_set):
    groups = []
    for group in consecutive_groups(sorted(cp_set)):
        g = list(group)
        if len(g) == 1:
            groups.append(f"U+{g[0]:X}")
        else:
            groups.append(f"U+{g[0]:X}-{g[-1]:X}")
    return ", ".join(groups)

def build_font_face(font, var=False):
    return f"""
@font-face {{
  font-family: "Noto";
  src: url("https://archive.org/cors/NotoFonts/{font.stem}.woff2") format("woff2"),
       url("https://archive.org/cors/NotoFonts/{font.stem}.woff") format("woff"),
       url("https://archive.org/cors/NotoFonts/{font.stem + font.suffix}") format("{"opentype" if font.suffix == ".otf" else "truetype"}");
  unicode-range: {f"var(--{font.family.replace(' ', '')})" if var else build_unicode_range(font.cmap)};
  {"font-style: italic;" if font.italic else ""}
  {f"font-weight: {font.weight};" if (not font.variable) and font.weight != 400 else ""}
  {f"font-stretch: {font.width};" if (not font.variable) and font.width != "normal" else ""}
}}
""".strip()

def sort_fontlist(fontlist, fallback):
    sorted_fontlist = sorted([(fallback.index(font.family), font) for font in fontlist])
    return [font for i, font in sorted_fontlist]

def build_family_cmap(fontlist):
    family_cmap = defaultdict(set)
    for font in fontlist:
        family_cmap[font.family].update(font.cmap)
    return dict(family_cmap)

def prune_fontlist_and_cmap(fontlist, family_cmap, variable=False, minimal=False):
    if variable:
        variable_families = {font.family for font in fontlist if font.variable}
    pruned_fontlist = []
    covered_cps = set()
    pruned_family_cmap = {}
    for font in fontlist:
        if not variable and font.variable:
            continue
        if variable and font.family in variable_families and not font.variable:
            continue
        if minimal and (font.weight != 400 or font.width != "normal" or font.italic):
            continue
        try:
            pruned_cmap = pruned_family_cmap[font.family]
        except KeyError:
            pruned_cmap = family_cmap[font.family] - covered_cps
            pruned_family_cmap[font.family] = pruned_cmap
            covered_cps.update(family_cmap[font.family])
        if not pruned_cmap:
            continue
        temp_font = font._asdict()
        temp_font["cmap"] = pruned_cmap
        pruned_fontlist.append(Font(**temp_font))
    return pruned_fontlist, pruned_family_cmap

def build_range_variables(family_cmap):
    output = ":root {\n"
    for family, cp_set in family_cmap.items():
        if cp_set:
            output += f"  --{family.replace(' ', '')}: {build_unicode_range(cp_set)};\n"
    output += "}"
    return output

def build_css(fontlist, var=False, family_cmap=None):
    output = []
    for font in fontlist:
        output.append(build_font_face(font, var))
    output = output[::-1]
    if var:
        output = [build_range_variables(family_cmap)] + output
    return "\n\n".join(output)

def build_all_css(style="", script=""):
    if style or script:
        if style and script:
            suffix = "-" + "-".join([style, script])
        elif style:
            suffix = "-" + style
        else:
            suffix = "-" + script
    else:
        suffix = ""
    fallback = build_fallback(f"fallback{suffix}.txt")
    fontlist = prepare_fontlist()
    family_cmap = build_family_cmap(fontlist)
    pruned_fontlist, pruned_cmap = prune_fontlist_and_cmap(sort_fontlist(fontlist, fallback), family_cmap)
    css = build_css(pruned_fontlist)
    with open(f"noto-fonts{suffix}.css", "w") as file:
        file.write(css)
    subprocess.run(["csso", f"noto-fonts{suffix}.css", "-o", f"noto-fonts{suffix}.min.css"])
    pruned_variable_fontlist, pruned_variable_cmap = prune_fontlist_and_cmap(sort_fontlist(fontlist, fallback), family_cmap, variable=True)
    variable_css = build_css(pruned_variable_fontlist, var=False, family_cmap=pruned_variable_cmap)
    with open(f"noto-fonts-variable{suffix}.css", "w") as file:
        file.write(variable_css)
    subprocess.run(["csso", f"noto-fonts-variable{suffix}.css", "-o", f"noto-fonts-variable{suffix}.min.css"])
    pruned_min_fontlist, pruned_min_cmap = prune_fontlist_and_cmap(sort_fontlist(fontlist, fallback), family_cmap, minimal=True)
    min_css = build_css(pruned_min_fontlist)
    with open(f"noto-fonts-minimal{suffix}.css", "w") as file:
        file.write(min_css)
    subprocess.run(["csso", f"noto-fonts-minimal{suffix}.css", "-o", f"noto-fonts-minimal{suffix}.min.css"])

if __name__ == "__main__":
    # fallback = build_fallback("fallback-sans.txt")
    # fontlist = prepare_fontlist()
    # family_cmap = build_family_cmap(fontlist)
    # pruned_fontlist, pruned_cmap = prune_fontlist_and_cmap(sort_fontlist(fontlist, fallback), family_cmap)
    # css = build_css(pruned_fontlist)
    # with open("noto-fonts.css", "w") as file:
    #     file.write(css)
    # subprocess.run(["csso", "noto-fonts.css", "-o", "noto-fonts.min.css"])
    # pruned_variable_fontlist, pruned_variable_cmap = prune_fontlist_and_cmap(sort_fontlist(fontlist, fallback), family_cmap, variable=True)
    # variable_css = build_css(pruned_variable_fontlist, var=False, family_cmap=pruned_variable_cmap)
    # with open("noto-fonts-variable.css", "w") as file:
    #     file.write(variable_css)
    # subprocess.run(["csso", "noto-fonts-variable.css", "-o", "noto-fonts-variable.min.css"])
    # pruned_min_fontlist, pruned_min_cmap = prune_fontlist_and_cmap(sort_fontlist(fontlist, fallback), family_cmap, minimal=True)
    # min_css = build_css(pruned_min_fontlist)
    # with open("noto-fonts-minimal.css", "w") as file:
    #     file.write(min_css)
    # subprocess.run(["csso", "noto-fonts-minimal.css", "-o", "noto-fonts-minimal.min.css"])
    build_all_css()
    build_all_css("serif")