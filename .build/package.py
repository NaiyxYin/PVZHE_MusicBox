import json, re, os, zipfile, hashlib, pathlib, sys

flags = [a for a in sys.argv[1:] if a.startswith("--")]
args = [a for a in sys.argv[1:] if not a.startswith("--")]
no_install = "--no-install" in flags

proj = pathlib.Path(args[0]) if args else pathlib.Path(__file__).resolve().parents[1]
man_path = proj / "mod.json"
man = json.loads(man_path.read_text(encoding="utf-8"))
man["runtimeAssembly"] = "Runtime/ModAssembly.dll"


# 版本号 4 段：前三段是模组版本（只在用户要求时改），第四段是构建号，每次打包 +1。
def next_build(version):
    parts = str(version or "1.0.0").strip().split(".")
    while len(parts) < 3:
        parts.append("0")
    if len(parts) == 3:
        return ".".join(parts) + ".1"
    digits = re.sub(r"\D", "", parts[3]) or "0"
    return ".".join(parts[:3]) + "." + str(int(digits) + 1)


previous_version = str(man.get("version") or "")
man["version"] = next_build(previous_version)
if man["version"] != previous_version:
    man_path.write_text(json.dumps(man, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("VERSION:", previous_version, "->", man["version"])

mid = man["id"]
norm = "".join(c if (c.isalnum() or c in "._-") else "_" for c in mid.strip()).strip(". ") or "mod"
suffix = hashlib.sha256(mid.encode("utf-8")).hexdigest().upper()[:8]
fname = f"{norm}-{suffix}.pmod"

out_dir = proj / "dist"
out_dir.mkdir(exist_ok=True)
out = out_dir / fname

binDir = proj / ".build" / "bin" / "Release"
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
    print("INSTALLED:", target)
    print("SHA256:", hashlib.sha256(data).hexdigest()[:16], "MATCH" if same else "MISMATCH")
else:
    print("INSTALL SKIPPED: no Mods dir at", mods_dir)
