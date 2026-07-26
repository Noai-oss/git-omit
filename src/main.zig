const std = @import("std");
const cli = @import("cli.zig");

pub fn main(init: std.process.Init) !void {
    cli.run(init) catch |err| switch (err) {
        error.GitCommandFailed => std.process.exit(1),
        error.InvalidUsage => std.process.exit(2),
        else => return err,
    };
}
