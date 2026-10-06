using System.Reflection;
using System.Text.Json;

// 用法：PVZHOSTDIR=<含 PlantsVsZombies.dll 的目录> dotnet run --project .build/validate -c Release -- mod.json
// 只做一件事：把包内 mod.json 反序列化成宿主的 XWModManifest，再反射调用
// XWModSettingsService.ValidateDefinitions，确认 settings 声明（含 visibleWhen/enabledWhen）真的能通过。
string gameBin = Environment.GetEnvironmentVariable("PVZHOSTDIR") ?? "";
string manifestPath = args.Length > 0 ? args[0] : "mod.json";
if (!File.Exists(Path.Combine(gameBin, "PlantsVsZombies.dll")))
{
    Console.WriteLine("FAIL: 未设置 PVZHOSTDIR，或该目录下没有 PlantsVsZombies.dll（取法见 README「构建与打包」）");
    return 2;
}

AppDomain.CurrentDomain.AssemblyResolve += (_, eventArgs) =>
{
    string candidate = Path.Combine(gameBin, new AssemblyName(eventArgs.Name).Name + ".dll");
    return File.Exists(candidate) ? Assembly.LoadFrom(candidate) : null;
};

var assembly = Assembly.LoadFrom(Path.Combine(gameBin, "PlantsVsZombies.dll"));
Type manifestType = assembly.GetType("PVZHE.ModEditor.ModSystem.XWModManifest");
Type serviceType = assembly.GetType("PVZHE.ModEditor.ModSystem.XWModSettingsService");
if (manifestType == null || serviceType == null)
{
    Console.WriteLine("FAIL: 宿主类型取不到（游戏程序集需要重新构建）");
    return 2;
}

object manifest = JsonSerializer.Deserialize(File.ReadAllText(manifestPath), manifestType);
MethodInfo validate = serviceType.GetMethod("ValidateDefinitions", BindingFlags.Public | BindingFlags.Static);
object[] callArgs = { manifest, null };
bool ok = (bool)validate.Invoke(null, callArgs);

Console.WriteLine(ok
    ? $"OK: settings 声明通过校验（{manifestPath}）"
    : $"FAIL: {callArgs[1]}");
return ok ? 0 : 1;
