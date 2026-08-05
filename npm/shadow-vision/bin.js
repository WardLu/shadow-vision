#!/usr/bin/env node
const { spawn } = require("node:child_process");
const child = spawn("uvx", ["shadow-vision", ...process.argv.slice(2)], {
  stdio: "inherit",
});
child.on("error", (err) => {
  if (err.code === "ENOENT") {
    console.error("shadow-vision requires 'uv' installed. Install: https://docs.astral.sh/uv/");
    process.exit(127);
  }
  throw err;
});
child.on("exit", (code) => process.exit(code ?? 1));
