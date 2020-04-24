from glob import glob
from pathlib import Path
from hashlib import md5
from shutil import copy
from os import remove, mkdir
from collections import defaultdict

from fontTools.ttLib import TTFont, TTLibError
from internetarchive import upload, download, get_item
from requests.exceptions import HTTPError
from tqdm import tqdm

try:
    mkdir("upload")
except FileExistsError:
    pass

searchpaths = [
    "noto-fonts/phaseIII_only/unhinted/ttf/**/*.ttf",
    "noto-fonts/phaseIII_only/unhinted/variable-ttf/**/*.ttf",
    "noto-fonts/unhinted/**/*.ttf",
    "noto-fonts/alpha/**/*.ttf",
    "noto-cjk/**/*.otf",
    "noto-emoji/fonts/**/*.ttf",
    "noto-source/variable-ttf/**/*.ttf",
]

fileset = set()
pathset = set()
for searchpath in searchpaths:
    for filepath in glob(searchpath, recursive=True):
        path = Path(filepath)
        filename = path.name
        if filename in fileset:
            continue
        else:
            pathset.add(path)
            fileset.add(filename)

def upload_to_ia():
    item = get_item("NotoFonts")
    hashdict = {f["name"]: f["md5"] for f in item.files}

    for path in tqdm(sorted(pathset)):
        filename = path.name
        file = open(path, "rb").read()
        hash = md5(file).hexdigest()
        try:
            if hashdict[filename] == hash:
                print("SKIPPING: " + filename)
                continue
        except KeyError:
            pass
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


if __name__ == "__main__":
    upload_to_ia()