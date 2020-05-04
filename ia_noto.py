from glob import glob
from pathlib import Path
from hashlib import md5
from shutil import copy
from os import remove, mkdir
from collections import defaultdict
from sys import argv

from fontTools.ttLib import TTFont, TTLibError
from internetarchive import upload, download, get_item
from requests.exceptions import HTTPError
from tqdm import tqdm

try:
    mkdir("upload")
except FileExistsError:
    pass

manual_override = [
    "noto-source/instance_ttf/NotoSansAdlam-*.ttf",
    "noto-fonts/unhinted/NotoSansOriya**/*.ttf",
]

searchpaths = [
    "noto-fonts/phaseIII_only/unhinted/ttf/**/*.ttf",
    "noto-fonts/phaseIII_only/unhinted/variable-ttf/**/*.ttf",
    "noto-fonts/unhinted/**/*.ttf",
    "noto-fonts/alpha/**/*.ttf",
    "noto-cjk/**/*.otf",
    "noto-emoji/fonts/**/*.ttf",
    "noto-source/instance_ttf/**/*.ttf"
    "noto-source/variable_ttf/**/*.ttf",
]

fileset = set()
pathset = set()
for searchpath in manual_override + searchpaths:
    for filepath in glob(searchpath, recursive=True):
        path = Path(filepath)
        filename = path.name
        if filename in fileset:
            continue
        else:
            pathset.add(path)
            fileset.add(filename)


def upload_to_ia(force=set()):
    item = get_item("NotoFonts")
    hashdict = {f["name"]: f["md5"] for f in item.files}

    fonts_modified = False
    for path in tqdm(sorted(pathset)):
        filename = path.name
        file = open(path, "rb").read()
        hash = md5(file).hexdigest()
        if "fonts" not in force:
            try:
                if hashdict[filename] == hash:
                    print("SKIPPING: " + filename)
                    continue
            except KeyError:
                pass
        fonts_modified = True
        print("WORKING: " + filename)
        upload_paths = []
        ttf = TTFont(path)
        print("  CONVERTING TO woff2...")
        ttf.flavor = "woff2"
        woff2_path = "upload/" + path.with_suffix(".woff2").name
        try:
            ttf.save(open(woff2_path, "wb"))
            upload_paths.append(woff2_path)
        except TTLibError:
            print("could not convert to woff2")
        print("  CONVERTING TO woff...")
        ttf.flavor = "woff"
        woff_path = "upload/" + path.with_suffix(".woff").name
        ttf.save(open(woff_path, "wb"))
        upload_paths.append(woff_path)
        print("  UPLOADING...")
        try:
            r = upload("NotoFonts", files=[*upload_paths, str(path)])
        except HTTPError:
            print("  UPLOAD FAILED. TRYING AGAIN...")
            r = upload("NotoFonts", files=[*upload_paths, str(path)])
        for upath in [woff2_path, woff_path]:
            remove(upath)
    if "css" in force or fonts_modified:
        from generate_css import build_all_css

        print("  GENERATING CSS...")
        build_all_css()
        css_files = glob("*.css")
        print("  UPLOADING...")
        try:
            r = upload("NotoFonts", files=css_files)
        except HTTPError:
            print("  UPLOAD FAILED. TRYING AGAIN...")
            r = upload("NotoFonts", files=css_files)


if __name__ == "__main__":
    upload_to_ia(force=set(argv[1:]))
