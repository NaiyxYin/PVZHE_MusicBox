import json, pathlib

proj = pathlib.Path(__file__).resolve().parents[1]
man_path = proj / "mod.json"
data = json.loads(man_path.read_text(encoding="utf-8"))

lines = (proj / "config" / "changelog.txt").read_text(encoding="utf-8").replace("\r\n", "\n").split("\n")
end = len(lines)
while end > 1 and lines[end - 1].strip() == "":
    end -= 1
body = "\n".join(line.rstrip() for line in lines[1:end]).strip("\n")

keys = [s.get("key") for s in data["settings"]]
data["settings"] = [s for s in data["settings"] if s.get("key") != "aboutUsage"]
seeded = False
for s in data["settings"]:
    if s.get("key") == "aboutChangelog":
        s["content"] = body
        seeded = True

man_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

after = [s.get("key") for s in data["settings"]]
print("BEFORE:", len(keys), "AFTER:", len(after))
print("KEYS:", ",".join(after))
print("SEED_CHANGED:", seeded, "BODY_LEN:", len(body))
print("HAS_PLAY_INSTRUCTIONS:", "playInstructions" in data, "PI_LEN:", len(data.get("playInstructions", "")))
print("VERSION:", data["version"])
