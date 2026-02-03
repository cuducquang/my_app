const express = require("express");
const { spawn } = require("child_process");
const { randomUUID } = require("crypto");
const path = require("path");

const PORT = process.env.PORT || 8000;
const MCP_ARGS = process.env.CHROME_MCP_ARGS
  ? process.env.CHROME_MCP_ARGS.split(" ").filter(Boolean)
  : ["--headless=true", "--isolated=true"];

const app = express();
app.use(express.json({ limit: "1mb" }));

const pending = new Map();

function startMcpProcess() {
  const isWin = process.platform === "win32";
  const npxCmd = isWin ? "npx" : "npx";
  const args = ["chrome-devtools-mcp@latest", ...MCP_ARGS];

  const child = spawn(npxCmd, args, {
    stdio: ["pipe", "pipe", "pipe"],
    cwd: path.resolve(__dirname),
    env: { ...process.env },
    shell: true,
  });

  let buffer = "";
  child.stdout.on("data", (chunk) => {
    buffer += chunk.toString();
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed) continue;
      try {
        const msg = JSON.parse(trimmed);
        if (msg.id && pending.has(msg.id)) {
          pending.get(msg.id).resolve(msg);
          pending.delete(msg.id);
        }
      } catch (err) {
        // ignore non-JSON lines
      }
    }
  });

  child.stderr.on("data", (chunk) => {
    console.error("[chrome-mcp]", chunk.toString());
  });

  child.on("exit", (code) => {
    console.error(`[chrome-mcp] exited with code ${code}`);
  });

  return child;
}

const mcpProcess = startMcpProcess();

function sendJsonRpc(payload, timeoutMs = 60000) {
  const id = payload.id || randomUUID();
  const message = { ...payload, id };
  const json = JSON.stringify(message);
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      pending.delete(id);
      reject(new Error("MCP timeout"));
    }, timeoutMs);
    pending.set(id, {
      resolve: (data) => {
        clearTimeout(timer);
        resolve(data);
      },
      reject,
    });
    mcpProcess.stdin.write(json + "\n");
  });
}

app.get("/health", (_req, res) => {
  res.json({ status: "ok" });
});

app.post("/", async (req, res) => {
  try {
    const result = await sendJsonRpc(req.body);
    res.json(result);
  } catch (err) {
    res.status(502).json({ error: "mcp_failed", message: err.message });
  }
});

app.post("/mcp", async (req, res) => {
  try {
    const result = await sendJsonRpc(req.body);
    res.json(result);
  } catch (err) {
    res.status(502).json({ error: "mcp_failed", message: err.message });
  }
});

app.listen(PORT, () => {
  console.log(`[mcp-bridge] listening on ${PORT}`);
});

