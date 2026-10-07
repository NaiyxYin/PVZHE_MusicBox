import json, re, os, zipfile, hashlib, pathlib, sys

flags = [a for a in sys.argv[1:] if a.startswith("--")]
args = [a for a in sys.argv[1:] if not a.startswith("--")]
no_install = "--no-install" in flags

proj = pathlib.Path(args[0]) if args else pathlib.Path(__file__).resolve().parents[1]
man_path = proj / "mod.json"
man = json.loads(man_path.read_text(encoding="utf-8"))
man["runtimeAssembly"] = "Runtime/ModAssembly.dll"


# 版本号只有一个来源：mod.json 的 version，严格 semver（主.次.补丁，内测再带 -alpha.1 / -beta.1 / -rc.1）。
# 它由作者定版时手写，打包**一个字节都不改它**；写成四段、或者把构建号塞进来，直接拦下不出包。
# 构建号已取消：同一个版反复出包就是覆盖同一个包名，游戏只按 Mod ID 认重复，所以每次出包
# 都要把同前缀的旧包删掉（见 retire_stale），留着会被判「存在重复的已安装 Mod ID」整批拒载。
SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
                    r"(-[0-9A-Za-z-]+(\.[0-9A-Za-z-]+)*)?"
                    r"(\+[0-9A-Za-z-]+(\.[0-9A-Za-z-]+)*)?$")

declared = str(man.get("version") or "").strip()
if not SEMVER.match(declared):
    sys.exit("mod.json 的 version 不是严格 semver：%r（正式版写 1.2.3，内测写 1.2.3-beta.1）" % declared)
if "+" in declared:
    sys.exit("mod.json 的 version 不该带 +构建元数据：%r，构建号已经取消" % declared)
print("VERSION:", declared)

# 包名只用「模组 ID + 版本号」，不带 ID 哈希那串后缀：正式发布的包是要发给玩家的，
# `MusicBox-1.2.3-637EA846.pmod` 里那八个字符对玩家没有意义，防撞靠的是 mod.json 里的 `id`，不是文件名。
mid = man["id"]
norm = "".join(c if (c.isalnum() or c in "._-") else "_" for c in mid.strip()).strip(". ") or "mod"
fname = f"{norm}-{declared}.pmod"


# 换版本时旧包名会留在 dist/ 和存档 Mods\ 里，游戏见到两个相同 ID 的包会整批拒载，所以只保留当前这一个。
def retire_stale(directory, keep):
    if not directory.is_dir():
        return []
    gone = [p.name for p in directory.glob(f"{norm}-*.pmod") if p.resolve() != keep.resolve()]
    for name in gone:
        (directory / name).unlink()
    return gone


binDir = proj / ".build" / "bin" / "Release"
out_dir = proj / "dist"
out_dir.mkdir(exist_ok=True)
out = out_dir / fname
gone = retire_stale(out_dir, out)
if gone:
    print("DIST_RETIRED:", ", ".join(gone))

with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
    z.writestr("mod.json", json.dumps(man, ensure_ascii=False, indent=2))
    z.write(binDir / "ModAssembly.dll", "Runtime/ModAssembly.dll")
    if (binDir / "ModAssembly.pdb").exists():
        z.write(binDir / "ModAssembly.pdb", "Runtime/ModAssembly.pdb")
    for rel in man.get("resources", []):
        rel_n = rel.replace("\\", "/")
        src = proj / rel_n
        if src.is_file() and rel_n != "mod.json":
            z.write(src, rel_n)
        else:
            print("MISSING RESOURCE:", rel_n)

print("PKG_FILE:", fname)
print("PKG_PATH:", out)
print("SIZE:", out.stat().st_size)

# 打包后必做：装到游戏存档目录并核对字节一致（只留在 dist/ 里等于没发布）。--no-install 时跳过。
mods_dir = pathlib.Path(os.environ["APPDATA"]) / "Godot" / "app_userdata" / "植物大战僵尸杂交版" / "Mods"
if no_install:
    print("INSTALL SKIPPED: --no-install，包只在 dist/ 里，游戏读到的仍是 Mods/ 里的旧包")
elif mods_dir.is_dir():
    target = mods_dir / fname
    data = out.read_bytes()
    target.write_bytes(data)
    same = target.read_bytes() == data
    gone = retire_stale(mods_dir, target)
    if gone:
        print("MODS_RETIRED:", ", ".join(gone), "（同 ID 的旧包留着会被游戏整批拒载）")
    print("INSTALLED:", target)
    print("SHA256:", hashlib.sha256(data).hexdigest()[:16], "MATCH" if same else "MISMATCH")
else:
    print("INSTALL SKIPPED: no Mods dir at", mods_dir)
