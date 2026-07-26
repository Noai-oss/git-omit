const std = @import("std");
const build_options = @import("build_options");
const clap = @import("clap");
const exclude = @import("exclude.zig");
const git = @import("git.zig");

const Command = enum {
    hide,
    unhide,
    freeze,
    unfreeze,
    list,
};

const main_parsers = .{
    .command = clap.parsers.enumeration(Command),
};

const main_params = clap.parseParamsComptime(
    \\-h, --help     Show this help and exit.
    \\-V, --version  Show the version and exit.
    \\<command>
    \\
);

const path_params = clap.parseParamsComptime(
    \\-h, --help  Show help for this command.
    \\<str>...
    \\
);

const list_params = clap.parseParamsComptime(
    \\-h, --help  Show help for this command.
    \\
);

pub fn run(init: std.process.Init) !void {
    var iter = try init.minimal.args.iterateAllocator(init.gpa);
    defer iter.deinit();

    // Skip argv[0].
    _ = iter.next();

    var diag = clap.Diagnostic{};
    var result = clap.parseEx(clap.Help, &main_params, main_parsers, &iter, .{
        .diagnostic = &diag,
        .allocator = init.gpa,
        .terminating_positional = 0,
    }) catch |err| {
        diag.reportToFile(init.io, .stderr(), err) catch {};
        return error.InvalidUsage;
    };
    defer result.deinit();

    if (result.args.help != 0) {
        try printMainHelpTo(init.io, .stdout());
        return;
    }
    if (result.args.version != 0) {
        try writeFmt(init.gpa, init.io, .stdout(), "git-omit {s}\n", .{build_options.version});
        return;
    }

    const command = result.positionals[0] orelse {
        try printMainHelpTo(init.io, .stderr());
        return error.InvalidUsage;
    };

    switch (command) {
        .hide, .unhide, .freeze, .unfreeze => try runPathCommand(
            init.io,
            init.gpa,
            &iter,
            command,
        ),
        .list => try runListCommand(init.io, init.gpa, &iter),
    }
}

fn runPathCommand(
    io: std.Io,
    gpa: std.mem.Allocator,
    iter: *std.process.Args.Iterator,
    command: Command,
) !void {
    var diag = clap.Diagnostic{};
    var result = clap.parseEx(clap.Help, &path_params, clap.parsers.default, iter, .{
        .diagnostic = &diag,
        .allocator = gpa,
    }) catch |err| {
        diag.reportToFile(io, .stderr(), err) catch {};
        return error.InvalidUsage;
    };
    defer result.deinit();

    if (result.args.help != 0) {
        try printCommandHelp(io, command);
        return;
    }

    const values = result.positionals[0];
    if (values.len == 0) {
        try writeFmt(
            gpa,
            io,
            .stderr(),
            "git-omit: {s} requires at least one {s}\n",
            .{
                @tagName(command),
                if (command == .hide or command == .unhide) "pattern" else "path",
            },
        );
        return error.InvalidUsage;
    }

    switch (command) {
        .hide => try exclude.hide(io, gpa, values),
        .unhide => try exclude.unhide(io, gpa, values),
        .freeze => try git.setFrozen(io, gpa, true, values),
        .unfreeze => try git.setFrozen(io, gpa, false, values),
        .list => unreachable,
    }
}

fn runListCommand(
    io: std.Io,
    gpa: std.mem.Allocator,
    iter: *std.process.Args.Iterator,
) !void {
    var diag = clap.Diagnostic{};
    var result = clap.parseEx(clap.Help, &list_params, clap.parsers.default, iter, .{
        .diagnostic = &diag,
        .allocator = gpa,
    }) catch |err| {
        diag.reportToFile(io, .stderr(), err) catch {};
        return error.InvalidUsage;
    };
    defer result.deinit();

    if (result.args.help != 0) {
        try printCommandHelp(io, .list);
        return;
    }

    var output: std.ArrayList(u8) = .empty;
    defer output.deinit(gpa);

    try exclude.appendItems(io, gpa, &output);
    try git.appendFrozenItems(io, gpa, &output);
    try std.Io.File.stdout().writeStreamingAll(io, output.items);
}

fn printMainHelpTo(io: std.Io, file: std.Io.File) !void {
    try file.writeStreamingAll(io,
        \\Usage: git-omit [--help] [--version] <command> [arguments]
        \\
        \\Keep local Git noise local.
        \\
        \\Commands:
        \\  hide <pattern>...    Add patterns to .git/info/exclude
        \\  unhide <pattern>...  Remove patterns from .git/info/exclude
        \\  freeze <path>...     Mark tracked files as skip-worktree
        \\  unfreeze <path>...   Clear skip-worktree from tracked files
        \\  list                 List hidden patterns and frozen paths
        \\
    );
}

fn printCommandHelp(io: std.Io, command: Command) !void {
    const text = switch (command) {
        .hide =>
        \\Usage: git-omit hide <pattern>...
        \\Add patterns to .git/info/exclude.
        \\
        ,
        .unhide =>
        \\Usage: git-omit unhide <pattern>...
        \\Remove exact patterns from .git/info/exclude.
        \\
        ,
        .freeze =>
        \\Usage: git-omit freeze <path>...
        \\Mark tracked files as skip-worktree.
        \\
        ,
        .unfreeze =>
        \\Usage: git-omit unfreeze <path>...
        \\Clear skip-worktree from tracked files.
        \\
        ,
        .list =>
        \\Usage: git-omit list
        \\List hidden patterns and frozen paths.
        \\
        ,
    };
    try std.Io.File.stdout().writeStreamingAll(io, text);
}

fn writeFmt(
    gpa: std.mem.Allocator,
    io: std.Io,
    file: std.Io.File,
    comptime format: []const u8,
    args: anytype,
) !void {
    const message = try std.fmt.allocPrint(gpa, format, args);
    defer gpa.free(message);
    try file.writeStreamingAll(io, message);
}
