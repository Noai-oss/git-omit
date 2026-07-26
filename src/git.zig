const std = @import("std");

pub fn excludePath(io: std.Io, gpa: std.mem.Allocator) ![]u8 {
    var result = try run(io, gpa, &.{ "rev-parse", "--git-path", "info/exclude" });
    defer deinitRunResult(gpa, &result);

    const path = std.mem.trim(u8, result.stdout, " \t\r\n");
    if (path.len == 0) {
        try writeError(io, "git returned an empty exclude path");
        return error.GitCommandFailed;
    }
    return gpa.dupe(u8, path);
}

pub fn setFrozen(
    io: std.Io,
    gpa: std.mem.Allocator,
    frozen: bool,
    paths: []const []const u8,
) !void {
    var args: std.ArrayList([]const u8) = .empty;
    defer args.deinit(gpa);

    try args.appendSlice(gpa, &.{
        "update-index",
        if (frozen) "--skip-worktree" else "--no-skip-worktree",
        "--",
    });
    try args.appendSlice(gpa, paths);

    var result = try run(io, gpa, args.items);
    defer deinitRunResult(gpa, &result);
}

pub fn appendFrozenItems(
    io: std.Io,
    gpa: std.mem.Allocator,
    output: *std.ArrayList(u8),
) !void {
    var result = try run(io, gpa, &.{ "ls-files", "-v", "-z" });
    defer deinitRunResult(gpa, &result);
    try appendFrozenItemsFromOutput(gpa, output, result.stdout);
}

fn run(
    io: std.Io,
    gpa: std.mem.Allocator,
    args: []const []const u8,
) !std.process.RunResult {
    var argv: std.ArrayList([]const u8) = .empty;
    defer argv.deinit(gpa);

    try argv.append(gpa, "git");
    try argv.appendSlice(gpa, args);

    var result = std.process.run(gpa, io, .{
        .argv = argv.items,
        .stdout_limit = .limited(16 * 1024 * 1024),
        .stderr_limit = .limited(1024 * 1024),
    }) catch |err| {
        try writeError(io, @errorName(err));
        return error.GitCommandFailed;
    };

    const succeeded = switch (result.term) {
        .exited => |code| code == 0,
        else => false,
    };
    if (!succeeded) {
        const message = std.mem.trim(u8, result.stderr, " \t\r\n");
        try writeError(io, if (message.len == 0) "git command failed" else message);
        deinitRunResult(gpa, &result);
        return error.GitCommandFailed;
    }

    return result;
}

fn deinitRunResult(gpa: std.mem.Allocator, result: *std.process.RunResult) void {
    gpa.free(result.stdout);
    gpa.free(result.stderr);
}

fn appendFrozenItemsFromOutput(
    gpa: std.mem.Allocator,
    output: *std.ArrayList(u8),
    git_output: []const u8,
) !void {
    var records = std.mem.splitScalar(u8, git_output, 0);
    while (records.next()) |record| {
        if (!std.mem.startsWith(u8, record, "S ")) continue;
        try output.appendSlice(gpa, "freeze\t");
        try output.appendSlice(gpa, record[2..]);
        try output.append(gpa, '\n');
    }
}

fn writeError(io: std.Io, message: []const u8) !void {
    try std.Io.File.stderr().writeStreamingAll(io, "git-omit: ");
    try std.Io.File.stderr().writeStreamingAll(io, message);
    try std.Io.File.stderr().writeStreamingAll(io, "\n");
}

test "list formatting includes only skip-worktree paths" {
    const gpa = std.testing.allocator;
    var output: std.ArrayList(u8) = .empty;
    defer output.deinit(gpa);

    try appendFrozenItemsFromOutput(
        gpa,
        &output,
        "H normal.txt\x00S config.json\x00",
    );

    try std.testing.expectEqualStrings("freeze\tconfig.json\n", output.items);
}
