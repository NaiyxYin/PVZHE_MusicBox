"""对实际源码中的纯托管逻辑做回归；不启动 Godot，不修改游戏存档。"""
import json
import os
import pathlib
import subprocess
import sys
import uuid
import zipfile

proj = pathlib.Path(__file__).resolve().parents[1]
source = (proj / "Scripts/MusicBoxEntry.cs").read_text(encoding="utf-8")
player_source = (proj / "Scripts/MusicBoxPlayer.cs").read_text(encoding="utf-8")
work = proj / ".build/TEMP/runtime-regression"
work.mkdir(parents=True, exist_ok=True)


def region(start, end):
    a = source.index(start)
    return source[a:source.index(end, a)]


body = "\n".join([
    region("        private static readonly (string Setting, string Screen)[] ScreenSettings", "        private enum ScreenMode"),
    region("        private static IEnumerable<string> EnumerateFiles", "        // 能不能被游戏读出来"),
    region("        private static string MusicStamp()", "        // ---------- 面板选项 -> 音频 ----------"),
    region("        private bool ReadStoredValues", "        private static string StorageHash"),
    region("        private static bool SameOptionValues", "        private string FindOwnPackage"),
    region("        private static string DetectAudioExtension", "        // FLAC 的头"),
    region("        private static string DescribeFlacRejection", "        // 同一首歌的同一句提示"),
])
lookup_start = player_source.index("        private static int FindTrackIndex")
lookup_end = player_source.index("        private sealed partial class MenuPlayer", lookup_start)
body += player_source[lookup_start:lookup_end]
order_source = (proj / "Scripts/MusicBoxPlaybackOrder.cs").read_text(encoding="utf-8")
body += order_source[order_source.index("        private static int PlaylistNext"):order_source.index("        private sealed partial class MenuPlayer")]
# Exercise actual transport methods with a synchronous settings-save/rebind callback.
def method(text, signature):
    start = text.index(signature)
    opening = text.index("{", start)
    depth = 1
    end = opening + 1
    while depth:
        depth += (text[end] == "{") - (text[end] == "}")
        end += 1
    return text[start:end]

transport = r'''
    sealed class Transport
    {
        public readonly PlaybackHistory playbackHistory = new();
        public string[] library = { "A", "B", "C" };
        public string choice = "A", libraryStamp = "v1";
        public bool updating = false, paused, blocked, startRequested, playlistEnded;
        public float resumePosition;
        public readonly Context context = new();
        public readonly Owner owner;
        readonly Control tracks = new(), status = new(), hint = new();
        readonly Player player = new();
        bool OwnsPlayback => false;
        public Transport() { owner = new Owner(this); }
        bool CanInteract() => true;
        bool Available() => true;
        void Release() { }
        void RefreshLibrary() { choice = owner.current; libraryStamp = owner.stamp; }
        void Tick() => RefreshLibrary();
        public void Next() => Step(1);
        public void Previous() => Step(-1);
        public void Finish() => AdvancePlaylist();
        public bool Select(int index) => TrySelectTrack(index, false);
        public sealed class Context { public string Setting = "menu"; }
        sealed class Control { public string Text; public void Select(long index) { } }
        sealed class Player { public bool Playing = false, StreamPaused; public void Play(float position) { } }
        public sealed class Owner
        {
            readonly Transport _menuPlayer;
            public string current = "A", stamp = "v1", mode = "shuffle";
            public bool failSave;
            public Owner(Transport player) { _menuPlayer = player; }
            public string ReadPlaybackOrder() => mode;
            public void WarnOnce(string key, string message) { }
            public bool TrySaveMenuTrack(string song, out string message, string setting)
            {
                message = "saved";
                if (failSave) return false;
                current = song;
                Rebind();
                return true;
            }
            public void Rebind() { __REBIND__ }
        }
__METHODS__
    }
'''
# Use the actual rebind statement from ApplyRegistrations, not a test-only reset policy.
rebind = source[source.index("        private void ApplyRegistrations"):].split("_menuPlayer?", 1)[1].split(";", 1)[0]
transport = transport.replace("__REBIND__", "_menuPlayer?" + rebind + ";")
transport = transport.replace("__METHODS__", "\n".join([
    method(player_source, "            public void ResetPlayback"),
    method(player_source, "            private bool TrySelectTrack"),
    method(player_source, "            private void Step"),
    method(order_source, "            private void AdvancePlaylist"),
]))
body += transport
body += method(source, "        private static string BgmRootPath")
if "--legacy-rebind" in sys.argv:
    body = body.replace("_menuPlayer?.ResetPlayback(resetHistory: false);", "_menuPlayer?.ResetPlayback();")
program = r'''
using System;
using System.IO;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;

static class GD
{
    static readonly Random random = new(131);
    public static uint Randi() => (uint)random.Next();
}
static class ProjectSettings
{
    public static string Root;
    public static string GlobalizePath(string path) => Root;
}
static class OS { public static string Name = "Windows"; public static string GetName() => Name; }
struct Variant { }
sealed class JavaValue
{
    readonly object value;
    public JavaValue(object value) { this.value = value; }
    public object AsGodotObject() => value;
    public string AsString() => value as string;
}
sealed class JavaObject
{
    public JavaValue Call(string method, params Variant[] args)
        => new(method == "getAbsolutePath" ? Engine.DataRoot : Engine.MissingDirectory && method == "getExternalFilesDir" ? null : new JavaObject());
}
static class Engine
{
    public static bool Available = true, MissingDirectory;
    public static string DataRoot = "/storage/emulated/0/Android/data/example.game";
    public static bool HasSingleton(string name) => Available;
    public static JavaObject GetSingleton(string name) => new();
}
class Regression
{
    const string BgmRootVirtualPath = "user://MusicBox", OffOption = "off";
    private static string _androidBgmRoot;
    const string MenuGroupSwitch = "enableMenuGroup", LevelGroupSwitch = "enableLevelGroup";
    const long MaxFlacDecodedPcmBytes = 128L * 1024 * 1024;
    static readonly string[] AudioExtensions = { ".wav", ".ogg", ".mp3", ".flac" };
    readonly Dictionary<string, string> _panelScalar = new(StringComparer.Ordinal);
    readonly Dictionary<string, bool> _panelBool = new(StringComparer.Ordinal);
    sealed class FakeContext { public string ModId = "musicbox"; }
    readonly FakeContext _context = new();
    void WarnOnce(string identity, string message) { }
__BODY__
    static void Require(bool condition) { if (!condition) throw new Exception("assertion failed"); }
    static int Main(string[] args)
    {
        int bad = 0, count = 0;
        void Test(string name, Action check)
        {
            count++;
            try { check(); }
            catch (Exception e) { bad++; Console.WriteLine("FAIL " + name + ": " + e.Message); }
        }
        var subject = new Regression();
        string root = Path.Combine(args[0], "fixtures-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        string config = Path.Combine(root, "settings.json");
        void Read(string json)
        {
            var record = JsonNode.Parse(json)!.AsObject();
            record["version"] = 1; record["modId"] = "musicbox";
            File.WriteAllText(config, record.ToJsonString()); Require(subject.ReadStoredValues(config));
        }
        Test("valid-config", () => {
            Read("{\"values\":{\"menuMainMenu\":\"song\",\"enableMenuGroup\":true}}");
            Require(subject._panelScalar["menuMainMenu"] == "song" && subject._panelBool[MenuGroupSwitch]);
        });
        Test("broken-json-keeps-state", () => {
            File.WriteAllText(config, "{");
            Require(!subject.ReadStoredValues(config));
            Require(subject._panelScalar["menuMainMenu"] == "song" && subject._panelBool[MenuGroupSwitch]);
        });
        Test("invalid-root-keeps-state", () => {
            File.WriteAllText(config, "[]");
            Require(!subject.ReadStoredValues(config) && subject._panelScalar["menuMainMenu"] == "song");
        });
        Test("invalid-values-keeps-state", () => {
            File.WriteAllText(config, "{\"values\":[]}");
            Require(!subject.ReadStoredValues(config) && subject._panelScalar["menuMainMenu"] == "song");
        });
        Test("wrong-owner-keeps-state", () => {
            File.WriteAllText(config, "{\"version\":1,\"modId\":\"other\",\"values\":{}}");
            Require(!subject.ReadStoredValues(config) && subject._panelScalar["menuMainMenu"] == "song");
        });
        Test("unknown-off-not-a-valid-option", () => Require(!subject.IsKnownOption("unknown", "off")));
        Test("false-and-trim", () => {
            Read("{\"values\":{\"menuMainMenu\":\" new song \",\"enableMenuGroup\":false}}");
            Require(subject._panelScalar["menuMainMenu"] == "new song" && !subject._panelBool[MenuGroupSwitch]);
        });
        Test("removed-values-clear-old-copy", () => {
            Read("{\"values\":{\"unknown\":\"song\"}}");
            Require(subject._panelScalar.Count == 0 && subject._panelBool.Count == 0);
        });
        ProjectSettings.Root = root;
        string song = Path.Combine(root, "song.mp3");
        File.WriteAllBytes(song, new byte[] { 1 });
        DateTime stamp = File.GetLastWriteTimeUtc(song);
        Test("fingerprint-includes-size", () => {
            string before = MusicStamp();
            File.WriteAllBytes(song, new byte[] { 1, 2 }); File.SetLastWriteTimeUtc(song, stamp);
            Require(before != MusicStamp());
        });
        Test("fingerprint-includes-relative-location", () => {
            string before = MusicStamp();
            string sub = Path.Combine(root, "sub"); Directory.CreateDirectory(sub);
            File.Move(song, Path.Combine(sub, "song.mp3"));
            Require(before != MusicStamp());
        });
        Test("fingerprint-stable-and-ignores-nonaudio", () => {
            string before = MusicStamp(); File.WriteAllText(Path.Combine(root, "notes.txt"), "ignored");
            Require(before == MusicStamp());
        });
        Test("labels-are-part-of-options", () => {
            var a = JsonNode.Parse("[{\"value\":\"song\",\"label\":\"old\"}]")!.AsArray();
            var b = JsonNode.Parse("[{\"value\":\"song\",\"label\":\"new\"}]")!.AsArray();
            Require(!SameOptionValues(a, b) && SameOptionValues(a, a));
        });
        Test("sniff-mislabeled-flac", () => Require(DetectAudioExtension(Encoding.ASCII.GetBytes("fLaC"), 4, ".mp3") == ".flac"));
        Test("sniff-short-header", () => Require(DetectAudioExtension(new byte[] { 0xff }, 1, ".wav") == ".wav"));
        Test("reject-incomplete-flac", () => Require(DescribeFlacRejection(new byte[64], 8) != null));
        Test("track-lookup-empty", () => Require(FindTrackIndex(Array.Empty<string>(), "x") == -1));
        Test("track-lookup-missing", () => Require(FindTrackIndex(new[] { "one", "two" }, "missing") == -1));
        Test("track-lookup-first", () => Require(FindTrackIndex(new[] { "one", "two" }, "one") == 0));
        Test("track-lookup-last", () => Require(FindTrackIndex(new[] { "one", "two" }, "two") == 1));
        Test("track-lookup-null-selection", () => Require(FindTrackIndex(new[] { "one" }, null) == -1));
        Test("player-visibility-false", () => { Read("{\"values\":{\"showMenuPlayer\":false}}"); Require(subject._panelBool["showMenuPlayer"] == false); });
        Test("player-visibility-true", () => { Read("{\"values\":{\"showMenuPlayer\":true}}"); Require(subject._panelBool["showMenuPlayer"]); });
        Test("single-repeat-natural-finish", () => Require(FinishedTrack(3, 1, "loop") == 1));
        Test("single-repeat-manual-navigation", () => Require(PlaylistNext(3, 1, "loop", 1) == 2 && PlaylistNext(3, 1, "loop", -1) == 0));
        Test("single-repeat-manual-wrap", () => Require(PlaylistNext(3, 2, "loop", 1) == 0 && PlaylistNext(3, 0, "loop", -1) == 2));
        Test("ordered-finish-boundaries", () => Require(FinishedTrack(3, 2, "sequence") == -1 && FinishedTrack(3, 0, "reverse") == -1));
        Test("empty-playlist", () => Require(FinishedTrack(0, -1, "loop") == -1 && PlaylistNext(0, -1, "shuffle", 1) == -1));
        Test("shuffle-history-roundtrip", () => {
            var h = new PlaybackHistory(); string[] songs = { "A", "B", "C" }; string current = "A";
            var visited = new List<string> { current };
            for (int i = 0; i < 12; i++) {
                int n = h.Next(songs, current, "shuffle", 1, "menu", "v1");
                Require(songs[n] != current); current = songs[n]; h.Commit(current); visited.Add(current);
            }
            for (int i = visited.Count - 2; i >= 0; i--) {
                int n = h.Next(songs, current, "shuffle", -1, "menu", "v1");
                Require(songs[n] == visited[i]); current = songs[n]; h.Commit(current);
            }
            Require(h.Next(songs, current, "shuffle", -1, "menu", "v1") == -1);
            for (int i = 1; i < visited.Count; i++) {
                int n = h.Next(songs, current, "shuffle", 1, "menu", "v1");
                Require(songs[n] == visited[i]); current = songs[n]; h.Commit(current);
            }
        });
        Test("shuffle-failed-save-does-not-move-history", () => {
            var h = new PlaybackHistory(); string[] songs = { "A", "B", "C" };
            int n = h.Next(songs, "A", "shuffle", 1, "menu", "v1"); h.Commit(songs[n]); string current = songs[n];
            Require(h.Next(songs, current, "shuffle", -1, "menu", "v1") == 0);
            Require(h.Next(songs, current, "shuffle", -1, "menu", "v1") == 0);
            h.Commit("A"); Require(songs[h.Next(songs, "A", "shuffle", 1, "menu", "v1")] == current);
        });
        Test("shuffle-reset-on-library-context-mode-or-external-selection", () => {
            string[] songs = { "A", "B", "C" };
            foreach (string change in new[] { "library", "context", "mode", "selection", "reset" }) {
                var h = new PlaybackHistory(); int n = h.Next(songs, "A", "shuffle", 1, "menu", "v1"); h.Commit(songs[n]);
                string current = songs[n];
                if (change == "mode") { h.Next(songs, current, "sequence", 1, "menu", "v1"); }
                if (change == "reset") h.Reset();
                Require(h.Next(songs, change == "selection" ? "A" : current, "shuffle", -1,
                    change == "context" ? "shop" : "menu", change == "library" ? "v2" : "v1") == -1);
            }
        });
        Test("shuffle-single-track", () => {
            var h = new PlaybackHistory(); string[] songs = { "A" };
            Require(h.Next(songs, "A", "shuffle", 1, "menu", "v1") == 0); h.Commit("A");
            Require(h.Next(songs, "A", "shuffle", -1, "menu", "v1") == -1);
        });
        Test("transport-manual-shuffle-save-rebind-roundtrip", () => {
            var t = new Transport(); var visited = new List<string> { t.choice };
            for (int i = 0; i < 12; i++) { t.Next(); Require(t.choice != visited.Last()); visited.Add(t.choice); }
            for (int i = visited.Count - 2; i >= 0; i--) { t.Previous(); Require(t.choice == visited[i]); }
            for (int i = 1; i < visited.Count; i++) { t.Next(); Require(t.choice == visited[i]); }
        });
        Test("transport-natural-shuffle-save-rebind-roundtrip", () => {
            var t = new Transport(); t.Finish(); string next = t.choice; Require(next != "A");
            t.Previous(); Require(t.choice == "A"); t.Next(); Require(t.choice == next);
        });
        Test("transport-save-failure-keeps-history", () => {
            var t = new Transport(); t.Next(); string next = t.choice;
            t.owner.failSave = true; t.Previous(); Require(t.choice == next);
            t.owner.failSave = false; t.Previous(); Require(t.choice == "A");
        });
        Test("transport-direct-selection-resets-history", () => {
            var t = new Transport(); t.Next(); Require(t.Select(3)); t.Previous(); Require(t.choice == "C");
        });
        Test("transport-context-reset-clears-history", () => {
            var t = new Transport(); t.Next(); string next = t.choice;
            t.ResetPlayback(); t.Previous(); Require(t.choice == next);
        });
        Test("transport-library-mode-external-selection-invalidate-history", () => {
            foreach (string change in new[] { "library", "mode", "selection" }) {
                var t = new Transport(); t.Next(); string next = t.choice;
                if (change == "library") t.owner.stamp = "v2";
                if (change == "mode") { t.owner.mode = "sequence"; t.Next(); t.owner.mode = "shuffle"; next = t.choice; }
                if (change == "selection") { t.owner.current = "A"; next = "A"; }
                t.Previous(); Require(t.choice == next);
            }
        });
        Test("desktop-musicbox-root", () => { Require(BgmRootVirtualPath == "user://MusicBox" && BgmRootPath() == root); });
        Test("android-app-data-musicbox-root-and-cache", () => {
            OS.Name = "Android"; _androidBgmRoot = null;
            Require(BgmRootPath() == Path.Combine(Engine.DataRoot, "MusicBox"));
            Engine.Available = false; Require(BgmRootPath() == Path.Combine(Engine.DataRoot, "MusicBox"));
            Engine.Available = true; OS.Name = "Windows"; _androidBgmRoot = null;
        });
        Test("android-unavailable-runtime-does-not-fallback", () => {
            OS.Name = "Android"; Engine.Available = false; _androidBgmRoot = null;
            bool rejected = false; try { BgmRootPath(); } catch (IOException) { rejected = true; }
            OS.Name = "Windows"; Engine.Available = true; Require(rejected);
        });
        Test("android-unavailable-storage-does-not-fallback", () => {
            OS.Name = "Android"; Engine.MissingDirectory = true; _androidBgmRoot = null;
            bool rejected = false; try { BgmRootPath(); } catch (IOException) { rejected = true; }
            OS.Name = "Windows"; Engine.MissingDirectory = false; Require(rejected);
        });
        Console.WriteLine($"Managed regression: {count - bad}/{count} PASS");
        return bad == 0 ? 0 : 1;
    }
}
'''.replace("__BODY__", body)
(work / "Program.cs").write_text(program, encoding="utf-8")
(work / "Regression.csproj").write_text(
    '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType>'
    '<TargetFramework>net9.0</TargetFramework><Nullable>disable</Nullable><EnableDefaultCompileItems>false</EnableDefaultCompileItems>'
    '</PropertyGroup><ItemGroup><Compile Include="Program.cs" /></ItemGroup></Project>', encoding="utf-8")
env = dict(os.environ)
env.update(DOTNET_CLI_HOME=str(proj / ".build/tmp"), NUGET_PACKAGES=str(proj / ".build/tmp/nuget"),
           TEMP=str(proj / ".build/TEMP"), TMP=str(proj / ".build/TEMP"))
subprocess.run(["dotnet", "run", "--project", str(work), "-c", "Release",
                "-p:UseSharedCompilation=false", "--", str(work)], env=env, check=True)

# 在隔离的项目副本里验证退出码，不破坏真实发布包。
fixture = work / ("package-" + uuid.uuid4().hex)
for folder in (".build/TEMP", "Scripts", "dist"):
    (fixture / folder).mkdir(parents=True, exist_ok=True)
verify = (proj / ".build/verify.py").read_text(encoding="utf-8")
(fixture / ".build/verify.py").write_text(verify, encoding="utf-8")
for name in ("mod.json", "changelog.txt", "Scripts/MusicBoxEntry.cs", "Scripts/MusicBoxUpdate.cs", "Scripts/MusicBoxPlayer.cs"):
    (fixture / name).write_bytes((proj / name).read_bytes())
manifest = json.loads((proj / "mod.json").read_text(encoding="utf-8"))
pkg = fixture / "dist" / (manifest["id"] + "-" + manifest["version"] + ".pmod")
dll = (proj / ".build/bin/Release/ModAssembly.dll").read_bytes()


def package(record):
    with zipfile.ZipFile(pkg, "w") as z:
        z.writestr("mod.json", json.dumps(record, ensure_ascii=False))
        z.writestr("Runtime/ModAssembly.dll", dll)
        z.writestr("Assets/ui-layout.json", (proj / "Assets/ui-layout.json").read_bytes())


def verify_code(expected):
    result = subprocess.run([sys.executable, str(fixture / ".build/verify.py")],
                            capture_output=True, text=True, encoding="utf-8")
    if result.returncode != expected:
        raise AssertionError("package gate returned %s, expected %s: %s%s" % (
            result.returncode, expected, result.stdout, result.stderr))
    return result.stdout


package(manifest)
verify_code(0)
manifest["playInstructions"] = ""
package(manifest)
assert "PI_HAS_FORMAT_HINT" in verify_code(1)
print("Package gate regression: valid=0, invalid=1 PASS")
