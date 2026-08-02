const std = @import("std");
const git = @import("git.zig");

pub fn hide(
    io: std.Io,
    gpa: std.mem.Allocator,
    patterns: []const []const u8,
) !void {
    const path = try git.excludePath(io, gpa);
    defer gpa.free(path);

    const current = try readFileOrEmpty(io, gpa, path);
    defer gpa.free(current);

    const edited = try addPatterns(gpa, current, patterns);
    if (edited) |content| {
        defer gpa.free(content);
        try writeFile(io, path, content);
    }
}

pub fn unhide(
    io: std.Io,
    gpa: std.mem.Allocator,
    patterns: []const []const u8,
) !void {
    const path = try git.excludePath(io, gpa);
    defer gpa.free(path);

    const current = try readFileOrEmpty(io, gpa, path);
    defer gpa.free(current);

    const edited = try removePatterns(gpa, current, patterns);
    if (edited) |content| {
        defer gpa.free(content);
        try writeFile(io, path, content);
    }
}

pub fn appendItems(
    io: std.Io,
    gpa: std.mem.Allocator,
    output: *std.ArrayList(u8),
) !void {
    const path = try git.excludePath(io, gpa);
    defer gpa.free(path);

    const current = try readFileOrEmpty(io, gpa, path);
    defer gpa.free(current);
    try appendItemsFromContents(gpa, output, current);
}

fn readFileOrEmpty(
    io: std.Io,
    gpa: std.mem.Allocator,
    path: []const u8,
) ![]u8 {
    return std.Io.Dir.cwd().readFileAlloc(io, path, gpa, .limited(16 * 1024 * 1024)) catch |err| switch (err) {
        error.FileNotFound => gpa.alloc(u8, 0),
        else => |e| return e,
    };
}

fn writeFile(io: std.Io, path: []const u8, content: []const u8) !void {
    if (std.fs.path.dirname(path)) |parent| {
        try std.Io.Dir.cwd().createDirPath(io, parent);
    }
    try std.Io.Dir.cwd().writeFile(io, .{
        .sub_path = path,
        .data = content,
    });
}

fn addPatterns(
    gpa: std.mem.Allocator,
    current: []const u8,
    patterns: []const []const u8,
) !?[]u8 {
    var existing: std.StringHashMapUnmanaged(void) = .empty;
    defer existing.deinit(gpa);

    var output: std.ArrayList(u8) = .empty;
    defer output.deinit(gpa);

    var start: usize = 0;
    while (start < current.len) {
        const end = std.mem.indexOfScalarPos(u8, current, start, '\n') orelse current.len;
        const line = std.mem.trimEnd(u8, current[start..end], "\r");
        try existing.put(gpa, line, {});
        try output.appendSlice(gpa, line);
        try output.append(gpa, '\n');
        if (end == current.len) break;
        start = end + 1;
    }

    var changed = false;
    for (patterns) |raw_pattern| {
        const pattern = std.mem.trim(u8, raw_pattern, " \t\r\n");
        if (pattern.len == 0 or existing.contains(pattern)) continue;
        try output.appendSlice(gpa, pattern);
        try output.append(gpa, '\n');
        try existing.put(gpa, pattern, {});
        changed = true;
    }

    if (!changed) return null;
    return try output.toOwnedSlice(gpa);
}

fn removePatterns(
    gpa: std.mem.Allocator,
    current: []const u8,
    patterns: []const []const u8,
) !?[]u8 {
    var targets: std.StringHashMapUnmanaged(void) = .empty;
    defer targets.deinit(gpa);

    for (patterns) |raw_pattern| {
        const pattern = std.mem.trim(u8, raw_pattern, " \t\r\n");
        if (pattern.len != 0) try targets.put(gpa, pattern, {});
    }
    if (targets.count() == 0) return null;

    var output: std.ArrayList(u8) = .empty;
    defer output.deinit(gpa);

    var changed = false;
    var start: usize = 0;
    while (start < current.len) {
        const end = std.mem.indexOfScalarPos(u8, current, start, '\n') orelse current.len;
        const line = std.mem.trimEnd(u8, current[start..end], "\r");
        if (targets.contains(line)) {
            changed = true;
        } else {
            try output.appendSlice(gpa, line);
            try output.append(gpa, '\n');
        }
        if (end == current.len) break;
        start = end + 1;
    }

    if (!changed) return null;
    return try output.toOwnedSlice(gpa);
}

fn appendItemsFromContents(
    gpa: std.mem.Allocator,
    output: *std.ArrayList(u8),
    current: []const u8,
) !void {
    var start: usize = 0;
    while (start < current.len) {
        const end = std.mem.indexOfScalarPos(u8, current, start, '\n') orelse current.len;
        const line = std.mem.trimEnd(u8, current[start..end], "\r");
        const stripped = std.mem.trim(u8, line, " \t");
        if (stripped.len != 0 and stripped[0] != '#') {
            try output.appendSlice(gpa, "hide\t");
            try output.appendSlice(gpa, line);
            try output.append(gpa, '\n');
        }
        if (end == current.len) break;
        start = end + 1;
    }
}

test "hide adds unique non-empty patterns" {
    const gpa = std.testing.allocator;
    const patterns = [_][]const u8{ " *.log ", "build/", "", "build/" };
    const edited = (try addPatterns(gpa, "# shared\n*.log\n", &patterns)).?;
    defer gpa.free(edited);

    try std.testing.expectEqualStrings("# shared\n*.log\nbuild/\n", edited);
}

test "hide does not rewrite an unchanged file" {
    const patterns = [_][]const u8{"*.log"};
    try std.testing.expect((try addPatterns(
        std.testing.allocator,
        "*.log\n",
        &patterns,
    )) == null);
}

test "unhide removes exact patterns and preserves comments" {
    const gpa = std.testing.allocator;
    const patterns = [_][]const u8{"*.log"};
    const edited = (try removePatterns(
        gpa,
        "# shared\n*.log\n*.tmp\n",
        &patterns,
    )).?;
    defer gpa.free(edited);

    try std.testing.expectEqualStrings("# shared\n*.tmp\n", edited);
}

test "list formatting ignores blank lines and comments" {
    const gpa = std.testing.allocator;
    var output: std.ArrayList(u8) = .empty;
    defer output.deinit(gpa);

    try appendItemsFromContents(gpa, &output, "\n# comment\n  # comment\n*.log\n");

    try std.testing.expectEqualStrings("hide\t*.log\n", output.items);
}
