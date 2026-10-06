import json, pathlib, zipfile, hashlib

proj = pathlib.Path(__file__).resolve().parents[1]
pkg = next((proj / "dist").glob("*.pmod"))
out = []
with zipfile.ZipFile(pkg) as z:
    bad = z.testzip()
    names = z.namelist()
    man_raw = z.read("mod.json")
    man = json.loads(man_raw.decode("utf-8"))
    dll = z.read("Runtime/ModAssembly.dll")

body = (proj / "config" / "changelog.txt").read_text(encoding="utf-8")
lines = body.split("\n")
lines[0] = ""
body = "\n".join(l.rstrip() for l in lines).strip()

changelog_item = next(s for s in man["settings"] if s["key"] == "aboutChangelog")
seed = changelog_item["text"] if "text" in changelog_item else changelog_item.get("content", "")

block_121 = body.split("v1.2.1")[1].split("v1.2.0")[0]
block_120 = body.split("v1.2.0")[1].split("v1.1.0")[0]
old_name = "CF音乐".encode("utf-8")
out.append("ZIP_OK: %s" % (bad is None))
out.append("NAMES: %s" % ", ".join(names))
out.append("SIZE_PKG: %d  DLL: %d" % (pkg.stat().st_size, len(dll)))
out.append("VERSION: %s" % man["version"])
out.append("SETTINGS: %d" % len(man["settings"]))
out.append("DLL_HAS_PREFLIGHT: %s" % (b"DescribeAudioRejection" in dll and b"DescribeFlacRejection" in dll
                                      and b"_blockedSlots" in dll and b"UnscannedAudioExtensions" in dll))
out.append("DLL_HAS_RESUME: %s" % (b"OnResumeFrame" in dll and b"ResumeMusicKeys" in dll))
out.append("DLL_HAS_SNIFF: %s" % (b"DetectAudioExtension" in dll and b"ReadFileHead" in dll and b"Matches" in dll))
out.append("ID: %s  NAME: %s" % (man["id"], man["name"]))
out.append("SCRIPTS: %s  ENTRY: %s" % (",".join(man["scripts"]), man["runtimeEntryType"]))
out.append("NO_OLD_NAME: %s" % (old_name not in man_raw and old_name not in body.encode("utf-8")))
out.append("DLL_IS_NEW_TYPE: %s" % (b"MusicBoxMod" in dll and b"CFMusic" not in dll))
# 旧名只允许出现在一处：编译器写进 DLL/PDB 的 pdb 路径（构建时的工作区目录）。
# 这里为 True 就说明包体里混进了玩家可见的旧名文本，或者构建还是在旧目录里跑的——重跑一次打包即可。
out.append("OLD_NAME_ONLY_IN_PDB_PATH: %s" % (old_name in dll and old_name not in man_raw))
out.append("PI_HAS_FORMAT_HINT: %s" % ("16-bit 立体声" in man.get("playInstructions", "")))

out.append("KEYS: %s" % ",".join(s["key"] for s in man["settings"]))
out.append("SEED_MATCHES_BODY: %s" % (seed == body))

# 更新源：模组每次启动拉仓库根目录的 update.txt。发布前这两条必须都 True——
# 占位没填就等于线上永远「已最新」，落后于包体版本就是给全部玩家弹一个下不到的新版。
feed_text = (proj / "update.txt").read_text(encoding="utf-8")
feed_url = ""
for src_line in (proj / "Scripts" / "MusicBoxEntry.cs").read_text(encoding="utf-8").splitlines():
    if "raw.githubusercontent.com" in src_line and '";' in src_line:
        feed_url = src_line.split('"')[1]
        break
feed_version = ""
for feed_line in feed_text.splitlines():
    feed_line = feed_line.strip()
    if feed_line.startswith("v="):
        feed_version = feed_line.split("|")[0][2:].strip()
        break
mod_v3 = tuple(int(x) for x in man["version"].strip().split(".")[:3])
feed_v3 = tuple(int(x) for x in feed_version.split(".")[:3] + ["0", "0"]) if feed_version else ()
out.append("FEED_URL: %s" % feed_url)
out.append("FEED_URL_NO_PLACEHOLDER: %s" % (bool(feed_url) and not any(
    token in feed_url for token in ("OWNER", "REPO", "<", " "))))
out.append("FEED_VERSION: %s  (mod %s)" % (feed_version, ".".join(map(str, mod_v3))))
out.append("FEED_NOT_BEHIND_PACKAGE: %s" % (bool(feed_v3) and feed_v3 >= mod_v3))

out.append("PLAY_INSTRUCTIONS_LEN: %d" % len(man.get("playInstructions", "")))
out.append("RESUME_LINE_IN_121_BLOCK: %s" % ("修复：从载入界面" in block_121))
out.append("SNIFF_LINE_IN_121_BLOCK: %s" % ("文件名和歌曲实际格式" in block_121))
out.append("RESUME_LINE_IN_120_BLOCK: %s" % ("修复：从载入界面" in block_120))
out.append("SHA16: %s" % hashlib.sha256(pkg.read_bytes()).hexdigest()[:16])
(proj / ".build/TEMP/verify.txt").write_text("\n".join(out), encoding="utf-8")
print("WROTE")
