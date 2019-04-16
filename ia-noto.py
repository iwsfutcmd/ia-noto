from glob import glob
import json
from pathlib import Path
from hashlib import md5
from shutil import copy

from fontTools.ttLib import TTFont
from internetarchive import upload
from tqdm import tqdm
from internetarchive import upload

try:
    hashdict = json.load(open("hashdict.json"))
except FileNotFoundError:
    hashdict = {}

searchpaths = [
    "noto-fonts/phaseIII_only/unhinted/ttf/**/*.ttf",
    "noto-fonts/unhinted/**/*.ttf",
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

for path in tqdm(pathset):
    filename = path.name
    print(filename)
    file = open(path, "rb").read()
    hash = md5(file).hexdigest()
    try:
        if hashdict[filename] == hash:
            continue
    except KeyError:
        pass
    ttf = TTFont(path)
    ttf.flavor = "woff2"
    woff2_path = "upload/" + path.with_suffix(".woff2").name
    ttf.save(open(woff2_path, "wb"))
    ttf.flavor = "woff"
    woff_path = "upload/" + path.with_suffix(".woff").name
    ttf.save(open(woff_path, "wb"))
    ttf_path = "upload/" + path.name
    copy(path, "upload")
    r = upload("NotoFonts", files=[woff2_path, woff_path, ttf_path])
    if all([c.status_code == 200 for c in r]):
        hashdict[filename] = hash
    json.dump(hashdict, open("hashdict.json", "w"))

