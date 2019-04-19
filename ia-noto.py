from glob import glob
import json
from pathlib import Path
from hashlib import md5
from shutil import copy
from os import remove

from fontTools.ttLib import TTFont, TTLibError
from internetarchive import upload
from tqdm import tqdm
from internetarchive import upload

try:
    hashdict = json.load(open("hashdict.json"))
except FileNotFoundError:
    hashdict = {}

searchpaths = [
    "noto-fonts/phaseIII_only/unhinted/ttf/**/*.ttf",
    "noto-fonts/phaseIII_only/unhinted/variable-ttf/**/*.ttf",
    "noto-fonts/unhinted/**/*.ttf",
    "noto-fonts/alpha/**/*.ttf",
    "noto-cjk/**/*.otf",
    "noto-emoji/fonts/**/*.ttf"
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
    ttf.flavor = "woff2"
    woff2_path = "upload/" + path.with_suffix(".woff2").name
    try:
        ttf.save(open(woff2_path, "wb"))
        upload_paths.append(woff2_path)
    except TTLibError:
        print("could not convert to woff2")
    ttf.flavor = "woff"
    woff_path = "upload/" + path.with_suffix(".woff").name
    ttf.save(open(woff_path, "wb"))
    upload_paths.append(woff_path)
    r = upload("NotoFonts", files=[*upload_paths, str(path)])
    if all([c.status_code == 200 for c in r]):
        hashdict[filename] = hash
        json.dump(hashdict, open("hashdict.json", "w"))
    for upath in [woff2_path, woff_path]:
        remove(upath)