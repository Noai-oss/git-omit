# 从 `git-omit` 学 Zig CLI 基础

这份文档以当前项目为例，目标不是记住每一行代码，而是理解这些代码为什么这样组织，以及它们对应的 Zig 基础知识。

完成阅读后，你应该能够解释：

- Zig 项目如何构建、添加依赖和组织模块；
- `const`、`var`、数组、切片、指针、枚举和 `switch` 的基本用法；
- `?T`、`!T`、`try`、`catch`、`orelse` 和 `defer` 分别解决什么问题；
- 为什么 Zig 经常显式传递 allocator 和 I/O 上下文；
- `clap` 如何在编译期生成参数解析结果的类型；
- 主命令和子命令为什么可以分两阶段解析同一个参数迭代器；
- 如何启动 Git 子进程、读取文件并管理返回内存；
- 如何把有副作用的代码与容易测试的纯逻辑分开。

## 1. 先认识项目结构

当前源代码被拆成四个模块：

```text
src/
├── main.zig       程序入口和最终退出码
├── cli.zig        参数解析、命令分发和帮助信息
├── git.zig        Git 子进程与 skip-worktree
└── exclude.zig    .git/info/exclude 的读写和编辑
```

依赖方向是：

```text
main.zig
   │
   ▼
cli.zig
   ├──────────────┐
   ▼              ▼
exclude.zig ───► git.zig
```

这个方向没有循环依赖：

- `main.zig` 只认识 CLI；
- `cli.zig` 负责组织功能，不实现 Git 或文件细节；
- `exclude.zig` 为了找到 `.git/info/exclude`，会调用 `git.zig`；
- `git.zig` 不反向依赖其他业务模块。

一次 `git-omit hide "*.log"` 的调用过程是：

```text
main()
  → cli.run()
  → 解析主命令 hide
  → 解析 hide 的剩余参数 "*.log"
  → exclude.hide()
  → git.excludePath()
  → 读取并修改 .git/info/exclude
```

## 2. `build.zig` 和 `build.zig.zon`

### 2.1 `build.zig` 描述如何构建

[build.zig](../build.zig) 是 Zig 写成的构建脚本。

```zig
const root_module = b.createModule(.{
    .root_source_file = b.path("src/main.zig"),
    .target = target,
    .optimize = optimize,
});
```

这里创建了一个以 `src/main.zig` 为入口的模块。

```zig
const exe = b.addExecutable(.{
    .name = "git-omit",
    .root_module = root_module,
});
```

这里把该模块编译为名叫 `git-omit` 的可执行程序。

项目还声明了两个自定义构建步骤：

```sh
zig build run -- --help
zig build test
```

第一个 `--` 属于 `zig build`，表示后面的参数传给 `git-omit`，而不是传给 Zig 构建系统。

### 2.2 `build.zig.zon` 描述包本身

[build.zig.zon](../build.zig.zon) 是包清单，记录包名、版本、最低 Zig 版本和依赖。

```zig
.dependencies = .{
    .clap = .{
        .url = "...",
        .hash = "...",
    },
},
```

`url` 告诉 Zig 去哪里下载依赖，`hash` 则固定依赖内容。即使 URL 上的内容发生变化，只要与 hash 不符，Zig 就不会悄悄接受它。

构建脚本通过依赖名取得 `clap`：

```zig
const clap = b.dependency("clap", .{});
root_module.addImport("clap", clap.module("clap"));
```

之后源代码才能使用：

```zig
const clap = @import("clap");
```

## 3. 模块、导入和可见性

Zig 中一个 `.zig` 文件通常就是一个模块。

```zig
const std = @import("std");
const cli = @import("cli.zig");
```

- `@import("std")` 导入标准库；
- `@import("cli.zig")` 导入相对于当前文件的本地模块；
- `@import("clap")` 导入由 `build.zig` 注册的外部模块。

`pub` 决定声明能否被其他模块访问：

```zig
pub fn run(init: std.process.Init) !void
```

`cli.run` 可以被 `main.zig` 调用，因为它是 `pub`。而 `runPathCommand` 没有 `pub`，只能在 `cli.zig` 内部使用。

这是一种很有用的设计方法：先让声明保持私有，只有确实属于模块 API 的部分才加 `pub`。

## 4. `const`、`var` 和类型推断

### 4.1 `const` 与 `var`

```zig
const command = result.positionals[0] orelse ...;
var iter = try init.minimal.args.iterateAllocator(init.gpa);
```

- `const` 表示绑定之后不能重新赋值；
- `var` 表示变量本身会发生变化。

参数迭代器每次调用 `next()` 都会改变内部位置，所以必须是 `var`。

`const` 不等于“底层所有内容都不可修改”。例如一个 `const` 指针仍可能指向可变对象；它只表示这个局部绑定不能指向另一个值。

### 4.2 类型推断

```zig
const build_options = @import("build_options");
var diag = clap.Diagnostic{};
```

Zig 会根据右侧表达式推断类型，因此这里不必重复写类型。`build_options`
是 `build.zig` 注入的编译期配置模块。

函数参数和公开边界通常仍然显式写类型：

```zig
fn runPathCommand(
    io: std.Io,
    gpa: std.mem.Allocator,
    iter: *std.process.Args.Iterator,
    command: Command,
) !void
```

这样调用者和编译器都能清楚知道函数需要什么。

## 5. 数组、切片、字符串与指针

### 5.1 Zig 字符串是什么

Zig 没有一个自动管理内存的通用 `String` 类。UTF-8 文本通常表示为：

```zig
[]const u8
```

它是一个只读字节切片：

- `[]` 表示长度在运行期确定；
- `const` 表示不能通过这个切片修改字节；
- `u8` 表示每个元素是 8 位无符号整数。

字符串字面量 `"hide"` 可以自动转换成 `[]const u8`。

### 5.2 “字符串列表”的类型

路径参数的类型是：

```zig
[]const []const u8
```

从内向外读：

```text
[]const u8           一个只读字符串
[]const ([]const u8) 一组只读字符串
```

例如：

```text
["config.json", "settings.json"]
```

外层切片本身只读，每个字符串也只读。

### 5.3 数组与切片

```zig
const patterns = [_][]const u8{ "*.log", "build/" };
```

这是一个固定长度数组。`_` 表示让编译器推断长度为 2。

```zig
const first = patterns[0];
const part = patterns[0..1];
```

- `patterns[0]` 取得一个元素；
- `patterns[0..1]` 得到一个切片；
- 切片可以理解为“指针 + 长度”，它通常不拥有底层内存。

### 5.4 `&` 与指针

```zig
&iter
```

取得 `iter` 的地址，类型是：

```zig
*std.process.Args.Iterator
```

主解析器和子命令解析器拿到同一个迭代器指针，因此它们操作的是同一份迭代状态。

另一个常见写法是：

```zig
&.{ "rev-parse", "--git-path", "info/exclude" }
```

`.{ ... }` 创建匿名数组，`&` 取得它的地址，调用时可以按需要转换为切片。

## 6. 枚举、`switch` 和表达式

### 6.1 用枚举表示有限命令集合

```zig
const Command = enum {
    hide,
    unhide,
    freeze,
    unfreeze,
    list,
};
```

与用任意字符串表示命令相比，枚举有两个优点：

- 只有这五个合法值；
- `switch` 可以在编译期检查是否覆盖所有情况。

### 6.2 `switch` 不只是语句

命令分发：

```zig
switch (command) {
    .hide => try exclude.hide(io, gpa, values),
    .unhide => try exclude.unhide(io, gpa, values),
    .freeze => try git.setFrozen(io, gpa, true, values),
    .unfreeze => try git.setFrozen(io, gpa, false, values),
    .list => unreachable,
}
```

这里的 `.hide` 是 `Command.hide` 的简写，因为编译器已经知道被匹配值的类型。

`switch` 也能产生值：

```zig
const succeeded = switch (result.term) {
    .exited => |code| code == 0,
    else => false,
};
```

这段代码把子进程状态转换成一个布尔值。

### 6.3 `if` 也可以产生值

```zig
if (frozen) "--skip-worktree" else "--no-skip-worktree"
```

这不是只能控制流程的语句，而是一个值为字符串的表达式。

### 6.4 `unreachable`

```zig
.list => unreachable,
```

这表示根据前面的控制流，程序不应该到达此分支。如果真的到达，说明代码内部存在逻辑错误。

不要用 `unreachable` 处理正常的用户输入错误。用户错误应该返回可处理的错误值。

## 7. 可选值：`?T`、`orelse` 和捕获

### 7.1 `?T`

`?T` 表示“可能有一个 `T`，也可能没有”，类似其他语言中的 `Option<T>`。

主命令可能缺失：

```zig
result.positionals[0]
```

它的值可能是一个 `Command`，也可能是 `null`。

### 7.2 `orelse`

```zig
const command = result.positionals[0] orelse {
    try printMainHelpTo(init.io, .stderr());
    return error.InvalidUsage;
};
```

如果左侧不是 `null`，就取出里面的 `Command`；否则执行右侧代码块。

简单情况也可以写：

```zig
const value = optional_value orelse default_value;
```

### 7.3 `if` 捕获可选值

exclude 编辑函数返回：

```zig
!?[]u8
```

先忽略最外面的 `!`，其中的 `?[]u8` 表示：

- 有切片：文件内容发生变化，需要写回；
- `null`：内容没有变化，不要重写文件。

调用代码：

```zig
const edited = try addPatterns(gpa, current, patterns);
if (edited) |content| {
    defer gpa.free(content);
    try writeFile(io, path, content);
}
```

`|content|` 会在值非空时把其中的切片取出来。

## 8. 错误联合：`!T`、`try` 和 `catch`

### 8.1 `!T`

```zig
pub fn excludePath(...) ![]u8
```

表示函数可能：

- 成功返回 `[]u8`；
- 失败返回某个错误。

`!void` 表示成功时没有额外返回值，但仍可能失败。

Zig 可以根据函数内部的 `return error.X` 和所调用函数自动推断错误集合。也可以显式声明：

```zig
const MyError = error{
    InvalidUsage,
    GitCommandFailed,
};
```

### 8.2 `try`

```zig
const path = try git.excludePath(io, gpa);
```

它相当于：

```text
成功 → 取得 path 并继续
失败 → 立即把错误返回给当前函数的调用者
```

`try` 不会吞掉错误，也不会自动打印错误。

### 8.3 `catch`

当当前层知道如何处理错误时，使用 `catch`：

```zig
clap.parseEx(...) catch |err| {
    diag.reportToFile(io, .stderr(), err) catch {};
    return error.InvalidUsage;
};
```

这里做了两件事：

1. 用 `clap` 的诊断信息告诉用户参数哪里错了；
2. 把 `clap` 的内部错误统一转换成项目自己的 `InvalidUsage`。

入口最终决定退出码：

```zig
cli.run(init) catch |err| switch (err) {
    error.GitCommandFailed => std.process.exit(1),
    error.InvalidUsage => std.process.exit(2),
    else => return err,
};
```

约定上：

- `0`：成功；
- `1`：一般运行失败；
- `2`：命令行用法错误。

### 8.4 `catch {}` 的含义

```zig
diag.reportToFile(...) catch {};
```

表示即使“打印诊断信息”本身失败，也忽略这个次要错误，继续返回原来的参数错误。

这种写法要谨慎使用。只有在确实不值得覆盖原始错误时才适合忽略。

## 9. `defer` 与资源生命周期

`defer` 注册一段代码，在当前作用域退出时执行：

```zig
var iter = try init.minimal.args.iterateAllocator(init.gpa);
defer iter.deinit();
```

无论后面是正常 `return`、`try` 提前返回还是 `catch` 分支退出，`iter.deinit()` 都会执行。

常见资源对应关系：

| 获得资源 | 释放方式 |
| --- | --- |
| `iterateAllocator()` | `iter.deinit()` |
| `clap.parseEx()` | `result.deinit()` |
| `gpa.dupe()` | `gpa.free()` |
| `readFileAlloc()` | `gpa.free()` |
| `std.process.run()` | 释放 `stdout` 和 `stderr` |
| `ArrayList` | `deinit(gpa)` |
| `StringHashMapUnmanaged` | `deinit(gpa)` |

一个重要原则是：**谁获得所有权，谁负责释放；如果把所有权返回给调用者，就把释放责任一起交给调用者。**

## 10. allocator：显式管理动态内存

### 10.1 为什么到处都有 `gpa`

```zig
gpa: std.mem.Allocator
```

allocator 是一套分配和释放内存的接口。函数不必知道底层使用的是通用堆、arena 还是测试 allocator。

例如：

```zig
const path_copy = try gpa.dupe(u8, path);
defer gpa.free(path_copy);
```

`dupe` 分配新内存并复制字节，返回的切片由调用者拥有。

### 10.2 借用与拥有

在 `excludePath` 中：

```zig
const path = std.mem.trim(u8, result.stdout, " \t\r\n");
return gpa.dupe(u8, path);
```

`path` 只是指向 `result.stdout` 内部的借用切片。函数退出时，`result.stdout` 会被释放，所以不能直接 `return path`。

先 `dupe` 得到独立副本，才可以安全返回。

这是理解 Zig 内存管理非常关键的例子：

```text
result.stdout ──────── 拥有实际内存
      │
      └── path ─────── 只是其中一段视图

dupe 后：

result.stdout ──────── 之后可以释放
path_copy ──────────── 独立内存，交给调用者
```

### 10.3 `ArrayList`

```zig
var output: std.ArrayList(u8) = .empty;
defer output.deinit(gpa);

try output.appendSlice(gpa, "hide\t");
try output.append(gpa, '\n');
```

`ArrayList` 是可增长数组。增长可能需要重新分配，因此操作会接收 allocator，也可能返回 `error.OutOfMemory`。

```zig
return try output.toOwnedSlice(gpa);
```

`toOwnedSlice` 把内部缓冲区的所有权移交给返回值，并把列表重置。调用者之后要对返回切片执行 `gpa.free()`。

### 10.4 `StringHashMapUnmanaged`

```zig
var existing: std.StringHashMapUnmanaged(void) = .empty;
defer existing.deinit(gpa);
```

它被当作集合使用：

```zig
try existing.put(gpa, pattern, {});
if (existing.contains(pattern)) ...
```

值类型是 `void`，因为这里只关心 key 是否存在。

`Unmanaged` 表示容器内部不保存 allocator，每次可能分配的操作都显式传入 `gpa`。

## 11. `std.process.Init` 与显式 I/O

Zig 0.16 的入口接收：

```zig
pub fn main(init: std.process.Init) !void
```

项目使用其中三个重要成员：

```zig
init.minimal.args  // 命令行参数
init.gpa           // 通用 allocator
init.io            // I/O 上下文
```

显式传递 `io`：

```zig
fn writeError(io: std.Io, message: []const u8) !void
```

然后写入标准错误：

```zig
try std.Io.File.stderr().writeStreamingAll(io, message);
```

这种设计把“执行什么 I/O”与“使用哪套 I/O 实现”分离，也让 API 的副作用更加明显。

输出约定：

- `stdout`：命令的正常结果，例如 `list`；
- `stderr`：诊断和错误信息；
- 退出码：让 shell 或脚本判断成功与失败。

## 12. `clap` 的编译期参数定义

### 12.1 `parseParamsComptime`

```zig
const main_params = clap.parseParamsComptime(
    \\-h, --help     Show this help and exit.
    \\-V, --version  Show the version and exit.
    \\<command>
    \\
);
```

`\\` 是 Zig 多行字符串语法。每一行前面的 `\\` 不属于最终字符串内容。

`parseParamsComptime` 在编译期解析这段描述。拼写错误或不合法的参数定义能更早暴露，而不是等用户运行程序才发现。

### 12.2 自定义值解析器

```zig
const main_parsers = .{
    .command = clap.parsers.enumeration(Command),
};
```

参数描述中的 `<command>` 与解析器字段 `.command` 对应。

因此字符串 `"hide"` 会被转换成：

```zig
Command.hide
```

非法命令无法转换成该枚举，`clap` 会返回解析错误。

### 12.3 返回结果为什么有动态生成的字段

解析结果中可以直接使用：

```zig
result.args.help
result.args.version
result.positionals[0]
```

这些字段是 `clap` 根据参数定义在编译期生成的。修改 `main_params` 后，返回结果的类型也可能变化。

如果只在局部变量中使用：

```zig
var result = clap.parseEx(...);
```

编译器可以推断类型。

如果要把结果传给另一个函数，则需要给返回类型起别名：

```zig
const MainArgs = clap.ResultEx(
    clap.Help,
    &main_params,
    main_parsers,
);
```

之后可以写：

```zig
fn handle(args: MainArgs) void {
    _ = args;
}
```

`ResultEx` 只计算类型，不会真正解析命令行。

## 13. 两阶段子命令解析

这是当前 CLI 最值得掌握的部分。

输入：

```text
git-omit hide -h
```

首先创建迭代器并跳过程序名：

```zig
var iter = try init.minimal.args.iterateAllocator(init.gpa);
_ = iter.next();
```

此时迭代器剩余：

```text
hide | -h
  ↑
```

主解析器使用：

```zig
var result = clap.parseEx(
    clap.Help,
    &main_params,
    main_parsers,
    &iter,
    .{
        .terminating_positional = 0,
    },
);
```

`<command>` 是第 0 个位置参数。解析器读到 `hide` 后：

1. 把它转换成 `Command.hide`；
2. 因为 `terminating_positional = 0`，立即停止；
3. 不读取后面的 `-h`。

状态变成：

```text
主解析结果：command = .hide
迭代器剩余：-h
              ↑
```

然后把同一个迭代器指针交给子命令：

```zig
runPathCommand(init.io, init.gpa, &iter, command)
```

子解析器从当前位置继续：

```zig
clap.parseEx(
    clap.Help,
    &path_params,
    clap.parsers.default,
    iter,
    .{},
)
```

于是 `-h` 成为 `hide` 子命令的帮助参数。

对比：

```text
git-omit -h         主解析器读取 -h，显示主帮助
git-omit hide -h    主解析器停在 hide，子解析器读取 -h
```

这不是 `clap` 自动建立的完整子命令树，而是项目手动进行的两阶段解析。

## 14. 启动 Git 子进程

### 14.1 构造 argv

```zig
var argv: std.ArrayList([]const u8) = .empty;
try argv.append(gpa, "git");
try argv.appendSlice(gpa, args);
```

最终可能得到：

```text
["git", "update-index", "--skip-worktree", "--", "config.json"]
```

这里没有拼接成一整条 shell 字符串，而是直接传参数数组。这能避免空格、引号和 shell 转义造成的问题。

### 14.2 为什么有 `--`

```text
git update-index --skip-worktree -- <paths>
```

`--` 表示选项到此结束，后面都是路径。

如果用户有一个叫 `--strange-file` 的文件，没有 `--` 时 Git 可能把它误认为选项。

### 14.3 `std.process.run`

```zig
var result = std.process.run(gpa, io, .{
    .argv = argv.items,
    .stdout_limit = .limited(16 * 1024 * 1024),
    .stderr_limit = .limited(1024 * 1024),
});
```

它会：

1. 启动进程；
2. 等待进程结束；
3. 收集 stdout 和 stderr；
4. 返回终止状态。

限制输出大小可以避免异常子进程无限输出并消耗全部内存。

### 14.4 检查退出状态

```zig
const succeeded = switch (result.term) {
    .exited => |code| code == 0,
    else => false,
};
```

`result.term` 是一个 tagged union：它既记录是哪种结束方式，也携带对应数据。

- `.exited => |code|`：正常退出，并取出退出码；
- 其他情况可能是信号终止等。

### 14.5 输出内存归调用者所有

`std.process.run` 返回的 `stdout` 和 `stderr` 是动态分配的：

```zig
fn deinitRunResult(gpa: std.mem.Allocator, result: *std.process.RunResult) void {
    gpa.free(result.stdout);
    gpa.free(result.stderr);
}
```

因此每个成功获得 `RunResult` 的地方都安排了对应的 `defer`。

## 15. 文件操作与 hide/unhide

### 15.1 让 Git 告诉我们 exclude 文件位置

项目没有假设文件一定在当前目录的 `.git/info/exclude`，而是运行：

```text
git rev-parse --git-path info/exclude
```

这样更适合 worktree 等 Git 目录结构。

### 15.2 读取不存在的文件

```zig
return readFileAlloc(...) catch |err| switch (err) {
    error.FileNotFound => gpa.alloc(u8, 0),
    else => |e| return e,
};
```

“文件不存在”在这里可以合理地解释为空文件，所以转换为空切片。其他错误仍然向上传播。

这体现了错误处理的一条原则：

> 只有在当前层真正理解某个错误含义时，才在当前层处理它。

### 15.3 编辑逻辑与 I/O 分离

`hide` 的流程：

```text
定位文件 → 读取内容 → addPatterns() → 有变化才写回
```

真正的文本转换函数：

```zig
fn addPatterns(
    gpa: std.mem.Allocator,
    current: []const u8,
    patterns: []const []const u8,
) !?[]u8
```

它不访问文件系统，也不执行 Git，因此很容易用字符串输入输出进行测试。

### 15.4 遍历文本行

```zig
const end = std.mem.indexOfScalarPos(u8, current, start, '\n') orelse current.len;
const line = std.mem.trimEnd(u8, current[start..end], "\r");
```

这段代码：

1. 从 `start` 开始寻找换行符；
2. 如果没找到，就使用字符串末尾；
3. 切出当前行；
4. 删除 Windows CRLF 中残留的 `\r`。

### 15.5 有变化才重写

```zig
if (!changed) return null;
return try output.toOwnedSlice(gpa);
```

不必要地重写文件可能改变时间戳、换行格式或触发文件监控器。因此返回 `null` 表示“无变化”，调用者就不写文件。

## 16. freeze/unfreeze 背后的 Git 知识

```text
git-omit freeze config.json
```

实际执行：

```text
git update-index --skip-worktree -- config.json
```

恢复时执行：

```text
git update-index --no-skip-worktree -- config.json
```

需要区分：

- `.git/info/exclude` 用于本地忽略未跟踪文件；
- `skip-worktree` 是索引位，告诉 Git 尽量不要关注已跟踪文件在工作区的变化。

`skip-worktree` 不是安全备份，也不是通用的“永久忽略已跟踪文件”。切换分支、合并或上游文件发生变化时，仍要谨慎检查本地内容。

列出冻结文件使用：

```text
git ls-files -v -z
```

- `-v` 输出状态标记；
- `S ` 开头表示 `skip-worktree`；
- `-z` 用 NUL 字节分隔记录，使包含空格或换行的路径也能被可靠处理。

对应解析：

```zig
var records = std.mem.splitScalar(u8, git_output, 0);
```

这里的 `0` 就是 NUL 字节。

## 17. 编译期参数：`comptime` 与 `anytype`

格式化辅助函数：

```zig
fn writeFmt(
    gpa: std.mem.Allocator,
    io: std.Io,
    file: std.Io.File,
    comptime format: []const u8,
    args: anytype,
) !void
```

### `comptime format`

表示格式字符串必须在编译期已知。编译器因此可以检查：

- `{s}`、`{d}` 等格式是否正确；
- 参数数量是否匹配；
- 参数类型是否适合对应占位符。

### `anytype`

`anytype` 类似“由调用点推断的泛型参数”。每种不同的参数类型都会生成对应版本的函数代码。

调用：

```zig
try writeFmt(gpa, io, .stdout(), "git-omit {s}\n", .{version});
```

`.{version}` 是一个匿名 tuple，用来承载格式化参数。

## 18. 测试与可测试设计

Zig 测试直接写在源码中：

```zig
test "hide adds unique non-empty patterns" {
    // ...
}
```

运行：

```sh
zig build test
```

测试使用：

```zig
const gpa = std.testing.allocator;
```

这个 allocator 会检查内存泄漏。如果测试分配了内存却没有释放，测试会失败。

常见断言：

```zig
try std.testing.expect(condition);
try std.testing.expectEqualStrings(expected, actual);
```

当前测试重点覆盖无副作用的转换逻辑：

- 添加规则时去重并忽略空值；
- 没有变化时返回 `null`；
- 删除规则时保留注释和其他内容；
- list 只输出有效规则；
- Git 状态文本只提取 `skip-worktree` 路径。

这种结构比直接在每个测试里创建真实 Git 仓库更快、更稳定。真实 Git 流程则适合放在少量端到端测试中。

## 19. 把几个复杂类型读顺

### `*std.ArrayList(u8)`

```text
std.ArrayList(u8)   一个动态字节数组
*                   指向它的可变指针
```

函数拿到指针后，可以把内容追加到调用者的同一个列表中。

### `[]const []const u8`

```text
[]const u8          一个只读字符串
[]const (...)       一组只读元素
```

即一组命令行字符串。

### `!?[]u8`

从内向外读：

```text
[]u8     可变字节切片
?[]u8    可能有切片，也可能是 null
!?[]u8   上述结果也可能以错误结束
```

### `*std.process.Args.Iterator`

一个指向可变参数迭代器的指针。多个函数通过它共享当前解析位置。

## 20. 推荐阅读顺序

第一次阅读代码时，按这个顺序更容易：

1. [src/main.zig](../src/main.zig)：看错误如何变成退出码；
2. [src/cli.zig](../src/cli.zig)：看参数如何变成 `Command`；
3. [src/git.zig](../src/git.zig)：看如何启动 Git；
4. [src/exclude.zig](../src/exclude.zig)：看内存、切片、容器和文件编辑；
5. [build.zig](../build.zig)：最后看模块如何被编译起来。

遇到复杂表达式时，先看函数签名，再从内向外读类型。

例如：

```zig
fn addPatterns(...) !?[]u8
```

先问：

1. 成功值是什么？`?[]u8`；
2. 为什么可空？可能没有变化；
3. 为什么可能报错？可能分配失败；
4. 返回的切片由谁释放？调用者。

## 21. 动手练习

建议每完成一个练习都运行：

```sh
zig fmt src
zig build test
zig build
```

### 练习 1：增加 `status` 别名

让：

```text
git-omit status
```

与 `git-omit list` 行为一致。

你会练习：

- 修改 enum；
- 修改 `switch`；
- 修改帮助文本。

### 练习 2：给 list 增加过滤参数

支持：

```text
git-omit list --kind hide
git-omit list --kind freeze
```

你会练习：

- clap 值解析器；
- optional；
- enum；
- 条件分支。

### 已完成：避免硬编码版本号

项目现在以 `build.zig.zon` 的 `.version` 作为原生程序版本来源：

```zig
const manifest = @import("build.zig.zon");

const build_options = b.addOptions();
build_options.addOption([]const u8, "version", manifest.version);
root_module.addOptions("build_options", build_options);
```

`cli.zig` 再导入生成的模块：

```zig
const build_options = @import("build_options");
```

这涉及：

- `b.addOptions()`；
- 构建模块；
- 编译期配置。

### 练习 4：加入 `--dry-run`

让 hide/unhide 只显示将发生的变化，不写文件。

你会练习：

- bool 参数；
- 数据转换与 I/O 分离；
- stdout 输出；
- 新的单元测试。

### 练习 5：改善文件写入安全性

研究如何先写临时文件，再原子替换 exclude 文件。

你会练习：

- 文件生命周期；
- 错误清理；
- `errdefer`；
- 原子更新。

## 22. 最后记住这几个核心心智模型

1. **切片通常只是视图，不一定拥有内存。**
2. **看到 allocator，就要继续寻找对应的释放位置。**
3. **`try` 负责传播，`catch` 负责当前层真正理解的错误。**
4. **`defer` 让资源清理紧挨着资源获取。**
5. **`?T` 表示缺失，`!T` 表示失败，它们解决的是不同问题。**
6. **CLI 子命令解析本质上是在有状态地消费参数序列。**
7. **把文件和进程操作包在外层，把文本转换留成纯函数，测试会简单很多。**
8. **模块边界应该按职责划分，而不是单纯按代码行数划分。**

可以把当前项目理解成一个小型但完整的系统编程练习：它同时涉及类型、内存、I/O、进程、文件、构建、错误处理和测试。掌握这些之后，再阅读更大的 Zig 项目会轻松很多。
