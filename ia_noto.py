from glob import glob
from pathlib import Path
from hashlib import md5
from shutil import copy
from os import remove, mkdir
from collections import defaultdict
from sys import argv

from fontTools.ttLib import TTFont, TTLibError
from internetarchive import upload, get_item, get_session
from requests.exceptions import HTTPError
from tqdm import tqdm

try:
    mkdir("upload")
except FileExistsError:
    pass

NOTO_PATH = Path("..")

manual_override = [
    # "noto-source/instance_ttf/NotoSansAdlam-*.ttf",
    # "noto-source/variable_ttf/NotoSansAdlam-VF.ttf",
    # "noto-source/instance_ttf/NotoSansOriya*.ttf",
    # "noto-source/variable_ttf/NotoSansOriya*-VF.ttf",
]

# searchpaths = [
#     "noto-fonts/unhinted/ttf/**/*.ttf",
#     "noto-fonts/unhinted/variable-ttf/*.ttf",
#     "noto-cjk/**/*.otf",
#     "noto-emoji/fonts/**/*.ttf",
#     "noto-source/instance_ttf/**/*.ttf"
#     "noto-source/variable_ttf/**/*.ttf",
# ]

searchpaths = [
    NOTO_PATH / "noto-fonts" / "unhinted" / "ttf" / "**" / "*.ttf",
    NOTO_PATH / "noto-fonts" / "unhinted" / "variable-ttf" / "*.ttf",
    NOTO_PATH / "noto-cjk" / "**" / "*.ttf",
    NOTO_PATH / "noto-emoji" / "fonts" / "**" / "*.ttf",
    NOTO_PATH / "noto-source" / "instance_ttf" / "**" / "*.ttf",
    NOTO_PATH / "noto-source" / "variable_ttf" / "**" / "*.ttf",

]

fileset = set()
pathset = set()
for searchpath in manual_override + searchpaths:
    for filepath in glob(str(searchpath), recursive=True):
        path = Path(filepath)
        filename = path.name
        if filename in fileset:
            continue
        else:
            pathset.add(path)
            fileset.add(filename)


def upload_to_ia(force=set()):
    s = get_session()
    item = s.get_item("NotoFonts")
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
        r = item.upload(files=[*upload_paths, str(path)], retries=100)
        for upath in [woff2_path, woff_path]:
            remove(upath)
    if "css" in force or fonts_modified:
        from generate_css import build_all_css

        print("  GENERATING CSS...")
        build_all_css()
        css_files = glob("*.css")
        for path in [Path(p) for p in sorted(css_files)]:
            filename = path.name
            file = open(path, "rb").read()
            hash = md5(file).hexdigest()
            # if "css" not in force:
            try:
                if hashdict[filename] == hash:
                    print("SKIPPING: " + filename)
                    continue
            except KeyError:
                pass
            print("  UPLOADING " + filename)
            r = item.upload(files=css_files, retries=100)

if __name__ == "__main__":
    upload_to_ia(force=set(argv[1:]))
