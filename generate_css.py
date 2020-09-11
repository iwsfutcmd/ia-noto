from collections import defaultdict, namedtuple
from sys import maxunicode
import subprocess

import unicodedataplus as unicodedata
from more_itertools import consecutive_groups
from fontTools.ttLib import TTFont
from tqdm import tqdm

from ia_noto import pathset

family_fixer = {
    "Noto Sans MeeteiMayek": "Noto Sans Meetei Mayek",
    "Noto Sans PauCinHau": "Noto Sans Pau Cin Hau",
    "NotoSerifTamilSlanted": "Noto Serif Tamil Slanted",
    "Noto Serif Hmong Nyiakeng": "Noto Serif Nyiakeng Puachue Hmong",
}


def build_fallbacks(fallbacks_filename):
    fallbacks = set()

    with open(fallbacks_filename) as f:
        for line in f.read().replace("\n", " > ").split(";"):
            fallback = line.strip().replace("  ", " ").split(" > ")
            fallbacks.add(frozenset(fallback))

    return fallbacks


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
    try:
        family = family_fixer[family]
    except KeyError:
        pass
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
            Font(stem, suffix, family, style, variable, weight, width, italic, cmap,)
        )
    return fontlist


# def prepare_nonunique(panfont_cmap, fallbacks):
#     nonunique = []
#     for k, v in panfont_cmap.items():
#         if len(v) == 1:
#             continue
#         families = {f[0] for f in v}
#         found = False
#         for fallback in fallbacks:
#             if families <= fallback:
#                 found = True
#         if not found:
#             nonunique.append((unicodedata.name(chr(k), ""), k, families))
#     nonunique = sorted(nonunique, key=lambda x: x[1])
#     return nonunique


def build_unicode_range(cp_set):
    groups = []
    for group in consecutive_groups(sorted(cp_set)):
        g = list(group)
        if len(g) == 1:
            groups.append(f"U+{g[0]:X}")
        else:
            groups.append(f"U+{g[0]:X}-{g[-1]:X}")
    return ", ".join(groups)


def build_font_face(font, family_name="Noto Sans", no_woff=False):
    if no_woff:
        src = [
            f'url("https://archive.org/cors/NotoFonts/{font.stem + font.suffix}") format("{"opentype" if font.suffix == ".otf" else "truetype"}")'
        ]
    else:
        src = [
            f'url("https://archive.org/cors/NotoFonts/{font.stem}.woff2") format("woff2")'
        ]
    # if all_formats:
    #     src.append(
    #         f'url("https://archive.org/cors/NotoFonts/{font.stem}.woff") format("woff")'
    #     )
    #     src.append(
    #         f'url("https://archive.org/cors/NotoFonts/{font.stem + font.suffix}") format("{"opentype" if font.suffix == ".otf" else "truetype"}")'
    #     )
    src_css = ",\n       ".join(src) + ";"
    font_properties = []
    if font.italic:
        font_properties.append("font-style: italic;")
    if not font.variable:
        if font.weight != 400:
            font_properties.append(f"font-weight: {font.weight};")
        if font.width != "normal":
            font_properties.append(f"font-stretch: {font.width};")
    font_properties_css = "\n  ".join(font_properties)

    return f"""
@font-face {{
  font-family: "{family_name}";
  src: {src_css}
  unicode-range: {build_unicode_range(font.cmap)};
  {font_properties_css}
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


def overlaps(families, family_cmap):
    overlap = set.intersection(*[family_cmap[family] for family in families])
    return [(f"U+{cp:02X}", unicodedata.name(chr(cp), "")) for cp in sorted(overlap)]


ecg_exclusions = {
    cp
    for cp in range(maxunicode + 1)
    if unicodedata.grapheme_cluster_break(chr(cp))
    in {"Extend", "ZWJ", "SpacingMark", "Prepend"}
}


def prune_fontlist(fontlist, family_cmap, variable=False, minimal=False):
    if variable:
        variable_families = {font.family for font in fontlist if font.variable}
    pruned_fontlist = []
    covered_cps = set()
    uncovered_cps_groups = consecutive_groups(
            sorted(
                set(range(maxunicode + 1))
                - set.union(*[font.cmap for font in fontlist])
            )
        )
    pruned_family_cmap = {}
    for font in tqdm(fontlist):
        if not variable and font.variable:
            continue
        if variable and font.family in variable_families and not font.variable:
            continue
        if minimal and variable and font.variable and not font.italic:
            pass
        elif minimal and (font.weight != 400 or font.width != "normal" or font.italic):
            continue
        try:
            pruned_cmap = pruned_family_cmap[font.family]
        except KeyError:
            pruned_cmap = family_cmap[font.family] - covered_cps
            if not pruned_cmap:
                continue
            new_uncovered_cps_groups = []
            for group in uncovered_cps_groups:
                cmap = list(group)
                if cmap[0] - 1 in pruned_cmap and cmap[-1] + 1 in pruned_cmap:
                    pruned_cmap = pruned_cmap | set(cmap)
                else:
                    new_uncovered_cps_groups.append(cmap)
            uncovered_cps_groups = new_uncovered_cps_groups[:]
            pruned_cmap = pruned_cmap | (family_cmap[font.family] & ecg_exclusions)
            pruned_family_cmap[font.family] = pruned_cmap
            covered_cps.update(family_cmap[font.family])
        if not pruned_cmap:
            continue
        temp_font = font._asdict()
        temp_font["cmap"] = pruned_cmap
        pruned_fontlist.append(Font(**temp_font))
    # if spans:
    #     uncovered_cps = set(range(maxunicode + 1)) - covered_cps
    #     for group in consecutive_groups(sorted(uncovered_cps)):
    #         cmap = list(group)
    #         for i, font in enumerate(pruned_fontlist):
    #             if cmap[0] - 1 in font.cmap and cmap[-1] + 1 in font.cmap:
    #                 temp_font = font._asdict()
    #                 temp_font["cmap"] = font.cmap | set(cmap)
    #                 pruned_fontlist[i] = Font(**temp_font)
    return pruned_fontlist


def build_css(fontlist, family_name="Noto Sans", no_woff=False):
    output = []
    for font in fontlist:
        output.append(build_font_face(font, family_name=family_name, no_woff=no_woff))
    output = output[::-1]
    return "\n\n".join(output)


def build_css_file(fontlist, style="sans", script=""):
    family_name = "Noto " + style.capitalize()
    suffix = f"-{style}"
    if script:
        suffix += f"-{script}"
    fallback = build_fallback(f"fallback{suffix}.txt")
    family_cmap = build_family_cmap(fontlist)

    for variable in [True, False]:
        for minimal in [True, False]:
            for no_woff in [True, False]:
                subset = ""
                if variable:
                    subset += "-variable"
                if minimal:
                    subset += "-minimal"
                if no_woff:
                    subset += "-no_woff"
                print(f"building noto{suffix}{subset}.css ...")
                pruned_fontlist = prune_fontlist(
                    sort_fontlist(fontlist, fallback),
                    family_cmap,
                    variable=variable,
                    minimal=minimal,
                )
                css = build_css(pruned_fontlist, family_name, no_woff=no_woff)
                with open(f"noto{suffix}{subset}.css", "w") as file:
                    file.write(css)
                subprocess.run(
                    [
                        "csso",
                        f"noto{suffix}{subset}.css",
                        "-o",
                        f"noto{suffix}{subset}.min.css",
                    ]
                )


def build_all_css():
    fontlist = prepare_fontlist()
    build_css_file(fontlist)
    build_css_file(fontlist, style="serif")


if __name__ == "__main__":
    build_all_css()
