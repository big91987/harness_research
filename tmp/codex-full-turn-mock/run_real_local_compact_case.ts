import fs from "node:fs";
import path from "node:path";
import { spawn } from "node:child_process";

const outDir = "/private/tmp/codex-real-local-compact-case";
const dumpPath = path.join(outDir, "dumped-responses-requests.json");
const codexHome = "/private/tmp/codex-real-local-compact-home";
const realCodexHome = path.join(process.env.HOME || "", ".codex");

fs.rmSync(outDir, { recursive: true, force: true });
fs.rmSync(codexHome, { recursive: true, force: true });
fs.mkdirSync(outDir, { recursive: true });
fs.mkdirSync(codexHome, { recursive: true });
fs.writeFileSync(dumpPath, "");

const authSrc = path.join(realCodexHome, "auth.json");
if (fs.existsSync(authSrc)) {
  fs.copyFileSync(authSrc, path.join(codexHome, "auth.json"));
}

function runCodex(args: string[]) {
  return new Promise<void>((resolve, reject) => {
    const child = spawn(
      "/Users/zhaojiuzhou/work/codex/codex-rs/target/debug/codex",
      args,
      {
        cwd: "/Users/zhaojiuzhou/Documents/harness_research",
        env: {
          ...process.env,
          CODEX_HOME: codexHome,
          CODEX_DUMP_RESPONSES_REQUEST: dumpPath,
          NO_PROXY: "127.0.0.1,localhost",
          no_proxy: "127.0.0.1,localhost",
          HTTP_PROXY: "",
          HTTPS_PROXY: "",
          ALL_PROXY: "",
          http_proxy: "",
          https_proxy: "",
          all_proxy: "",
        },
        stdio: ["ignore", "pipe", "pipe"],
      }
    );
    child.stdout.on("data", (chunk) => process.stdout.write(chunk));
    child.stderr.on("data", (chunk) => process.stderr.write(chunk));
    child.on("exit", (code) => {
      if (code === 0) resolve();
      else reject(new Error(`codex exited with ${code}`));
    });
  });
}

function commonArgs() {
  return [
    "--ignore-user-config",
    "--skip-git-repo-check",
    "-m",
    "gpt-5.5",
    "-c",
    'model_provider="localcompact"',
    "-c",
    'model_providers.localcompact={name="LocalCompactOpenAI",wire_api="responses",requires_openai_auth=true,request_max_retries=0,stream_max_retries=0,stream_idle_timeout_ms=300000,supports_websockets=false}',
    "-c",
    "model_auto_compact_token_limit=200",
    "-c",
    "model_reasoning_effort=low",
  ];
}

async function main() {
  await runCodex([
    "exec",
    ...commonArgs(),
    "local compact case 第 1 轮：只回答“收到”。",
  ]);
  await runCodex([
    "exec",
    "resume",
    "--last",
    ...commonArgs(),
    "local compact case 第 2 轮：只回答“继续”。",
  ]);
  console.log(`\nOUT_DIR=${outDir}`);
  console.log(`CODEX_HOME=${codexHome}`);
  console.log(`DUMP=${dumpPath}`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
