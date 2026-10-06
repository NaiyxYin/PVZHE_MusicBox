using System.Reflection;

var entry = typeof(MusicBoxMod.MusicBoxEntry);
var reject = entry.GetMethod("DescribeAudioRejection", BindingFlags.NonPublic | BindingFlags.Static);
var detect = entry.GetMethod("DetectAudioExtension", BindingFlags.NonPublic | BindingFlags.Static);
var readHead = entry.GetMethod("ReadFileHead", BindingFlags.NonPublic | BindingFlags.Static);
if (reject == null || detect == null || readHead == null)
{
    Console.WriteLine("NOT FOUND: preflight methods");
    return;
}

string[] roots = Environment.GetCommandLineArgs().Skip(1).ToArray();
if (roots.Length == 0)
{
    Console.WriteLine("用法：dotnet run --project .build/probe -c Release -- <BGM 目录> [额外目录...]");
    return;
}

int ok = 0, blocked = 0, mismatch = 0;
foreach (string root in roots)
{
    if (!Directory.Exists(root))
    {
        Console.WriteLine("NO SUCH DIR: " + root);
        continue;
    }
    foreach (string file in Directory.GetFiles(root, "*", SearchOption.AllDirectories)
                 .OrderBy(path => path, StringComparer.Ordinal))
    {
        string extension = Path.GetExtension(file).ToLowerInvariant();
        if (extension != ".flac" && extension != ".ogg" && extension != ".mp3" && extension != ".wav")
            continue;

        var head = new byte[64];
        int filled = (int)readHead.Invoke(null, new object[] { file, head });
        string real = (string)detect.Invoke(null, new object[] { head, Math.Max(0, filled), extension });
        if (!real.Equals(extension, StringComparison.OrdinalIgnoreCase))
        {
            mismatch++;
            Console.WriteLine($"MISLABELED {Path.GetFileName(file)}  文件名 {extension} / 内容 {real}");
        }

        string reason = (string)reject.Invoke(null, new object[] { file });
        if (reason == null)
        {
            ok++;
            continue;
        }
        blocked++;
        Console.WriteLine("BLOCKED " + Path.GetFileName(file) + "  ->  " + reason);
    }
}
Console.WriteLine($"total ok={ok} blocked={blocked} mislabeled={mismatch}");
