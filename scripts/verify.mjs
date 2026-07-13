import { spawnSync } from "node:child_process";

const npm = process.platform === "win32" ? "npm.cmd" : "npm";
const uv = process.platform === "win32" ? "uv.exe" : "uv";

const groups = {
  format: [
    [uv, ["run", "--project", "apps/api", "ruff", "format", "apps/api"]],
    [npm, ["exec", "prettier", "--", "--write", "."]],
  ],
  formatcheck: [
    [uv, ["run", "--project", "apps/api", "ruff", "format", "--check", "apps/api"]],
    [npm, ["exec", "prettier", "--", "--check", "."]],
  ],
  lint: [
    [uv, ["run", "--project", "apps/api", "ruff", "check", "apps/api"]],
    [npm, ["--workspace", "@jepret/web", "run", "lint"]],
  ],
  typecheck: [
    [uv, ["run", "--project", "apps/api", "mypy", "apps/api/app"]],
    [npm, ["--workspace", "@jepret/web", "run", "typecheck"]],
  ],
  test: [
    [uv, ["run", "--project", "apps/api", "pytest", "apps/api/tests", "-q"]],
    [npm, ["--workspace", "@jepret/web", "test"]],
  ],
  contracts: [[npm, ["run", "contracts:check"]]],
  build: [
    [npm, ["--workspace", "@jepret/web", "run", "build"]],
    ["docker", ["compose", "config", "--quiet"]],
  ],
  e2e: [[npm, ["--workspace", "@jepret/web", "run", "e2e"]]],
};

const requested = process.argv[2];
const order =
  requested === "verify"
    ? ["formatcheck", "lint", "typecheck", "test", "contracts", "build"]
    : [requested];
for (const group of order) {
  if (!groups[group]) throw new Error(`Unknown quality group: ${group}`);
  for (const [command, args] of groups[group]) {
    const result = spawnSync(command, args, { stdio: "inherit", shell: false });
    if (result.status !== 0) process.exit(result.status ?? 1);
  }
}
