import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { spawn } from "node:child_process";

const port = 18182;
const outDir = "/private/tmp/codex-diff-context-turns";
const dumpPath = path.join(outDir, "dumped-responses-requests.json");
const requestsPath = path.join(outDir, "mock-server-requests.ndjson");
const eventsPath = path.join(outDir, "mock-server-events.ndjson");
const codexHome = "/private/tmp/codex-diff-context-home";

fs.rmSync(outDir, { recursive: true, force: true });
fs.rmSync(codexHome, { recursive: true, force: true });
fs.mkdirSync(outDir, { recursive: true });
fs.mkdirSync(codexHome, { recursive: true });
for (const file of [dumpPath, requestsPath, eventsPath]) {
  fs.writeFileSync(file, "");
}

function sse(events: unknown[]): string {
  return events
    .map((event: any) => `event: ${event.type}\ndata: ${JSON.stringify(event)}\n\n`)
    .join("");
}

function responseEvents(id: string, text: string) {
  return [
    { type: "response.created", response: { id } },
    {
      type: "response.output_item.done",
      item: {
        type: "message",
        role: "assistant",
        id: `msg-${id}`,
        content: [{ type: "output_text", text }],
      },
    },
    {
      type: "response.completed",
      response: {
        id,
        usage: {
          input_tokens: 0,
          input_tokens_details: null,
          output_tokens: 0,
          output_tokens_details: null,
          total_tokens: 0,
        },
      },
    },
  ];
}

let responseNo = 0;
const server = http.createServer((req, res) => {
  if (req.method !== "POST" || !req.url?.startsWith("/v1/responses")) {
    res.writeHead(404);
    res.end("not found");
    return;
  }
  const chunks: Buffer[] = [];
  req.on("data", (chunk) => chunks.push(Buffer.from(chunk)));
  req.on("end", () => {
    const raw = Buffer.concat(chunks);
    const body = JSON.parse(raw.toString("utf8"));
    fs.appendFileSync(requestsPath, JSON.stringify(body) + "\n");
    responseNo += 1;
    const events = responseEvents(`resp-${responseNo}`, `mock final ${responseNo}`);
    fs.appendFileSync(
      eventsPath,
      JSON.stringify({
        responseNo,
        inputCount: Array.isArray(body.input) ? body.input.length : null,
        events,
      }) + "\n"
    );
    res.writeHead(200, {
      "content-type": "text/event-stream; charset=utf-8",
      "cache-control": "no-cache",
    });
    res.end(sse(events));
  });
});

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
          OPENAI_API_KEY: "sk-test",
          NO_PROXY: "127.0.0.1,localhost,*",
          no_proxy: "127.0.0.1,localhost,*",
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
      if (code === 0) {
        resolve();
      } else {
        reject(new Error(`codex exited with ${code}`));
      }
    });
  });
}

function providerArgs() {
  return [
    "--ignore-user-config",
    "--skip-git-repo-check",
    "-c",
    'model_provider="mock"',
    "-c",
    `model_providers.mock={name="mock",base_url="http://127.0.0.1:${port}/v1",env_key="OPENAI_API_KEY",wire_api="responses",request_max_retries=0,stream_max_retries=0,stream_idle_timeout_ms=10000,supports_websockets=false}`,
  ];
}

async function main() {
  await new Promise<void>((resolve) => server.listen(port, "127.0.0.1", resolve));
  try {
    await runCodex([
      "exec",
      ...providerArgs(),
      "-m",
      "gpt-5",
      "turn1：建立上下文基线，只回答一句。",
    ]);
    await runCodex([
      "exec",
      "resume",
      "--last",
      ...providerArgs(),
      "-m",
      "gpt-5",
      "turn2：同配置继续，只回答一句。",
    ]);
    await runCodex([
      "exec",
      "resume",
      "--last",
      ...providerArgs(),
      "-m",
      "gpt-5.1",
      "turn3：改模型后继续，只回答一句。",
    ]);
    console.log(`\nOUT_DIR=${outDir}`);
    console.log(`CODEX_HOME=${codexHome}`);
  } finally {
    server.close();
  }
}

main().catch((err) => {
  console.error(err);
  server.close(() => process.exit(1));
});
