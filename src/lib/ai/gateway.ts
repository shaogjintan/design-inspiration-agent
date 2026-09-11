// -----------------------------------------------------------------------
// AWS LLM Gateway client — SERVER-SIDE ONLY.
//
// What this actually talks to (important, since it's easy to assume this
// project calls Bedrock directly via the AWS SDK — it doesn't):
//
//   Our team was NOT given raw AWS access keys + `bedrock:InvokeModel`
//   permission. We were given a URL + API key for a gateway the org
//   already runs in front of Bedrock:
//
//     Next.js server  --HTTP, X-API-Key header-->  LLM Gateway (ALB)
//                                                        |
//                                                        v
//                                              AWS Bedrock Runtime
//                                              (Claude Sonnet 4.5)
//
//   The gateway speaks Ollama's native wire protocol, NOT OpenAI's and
//   NOT the raw Bedrock Converse API:
//
//     POST {LLM_GATEWAY_URL}/api/chat
//     Headers: X-API-Key: <LLM_GATEWAY_API_KEY>
//     Body:    { model, messages: [{role, content}], stream: false }
//     Reply:   { message: { role: "assistant", content: "..." }, ... }
//
//   This is exactly what ShowMeYourAgent-Starter-Kit/weather_demo.py and
//   test_llm_gateway.py do (there, via a `ChatOllama`/urllib client). We
//   reimplement the same two calls here with plain `fetch` since Node
//   already has it — no AWS SDK, no LangChain needed for this part.
//
//   Because the API key must never reach the browser, every function in
//   this file may ONLY be called from server-side code — a Route Handler
//   (src/app/api/.../route.ts) or a Server Action. The guard below turns
//   an accidental client-side import into a loud, immediate error instead
//   of a silently leaked key.
// -----------------------------------------------------------------------

if (typeof window !== "undefined") {
  throw new Error(
    "src/lib/ai/gateway.ts imports server-only secrets (LLM_GATEWAY_API_KEY) " +
      "and must never be imported from client components."
  );
}

export interface GatewayMessage {
  role: "system" | "user" | "assistant";
  content: string;
}

interface GatewayChatResponse {
  message?: { role: string; content: string };
  done_reason?: string;
  error?: string;
}

function getConfig() {
  const url = process.env.LLM_GATEWAY_URL;
  const apiKey = process.env.LLM_GATEWAY_API_KEY;
  const model = process.env.LLM_MODEL;

  if (!url || !apiKey || !model) {
    throw new Error(
      "Missing LLM_GATEWAY_URL / LLM_GATEWAY_API_KEY / LLM_MODEL. " +
        "Add them to .env.local (see design-inspiration-agent/.env.local) " +
        "and restart `npm run dev`."
    );
  }
  return { url: url.replace(/\/$/, ""), apiKey, model };
}

/**
 * Send a chat turn to the gateway and get back the assistant's full reply.
 * Non-streaming — fine for now; add a streaming variant later if the UI
 * needs tokens-as-they-arrive.
 */
export async function chatCompletion(
  messages: GatewayMessage[],
  opts: { numPredict?: number } = {}
): Promise<string> {
  const { url, apiKey, model } = getConfig();

  const res = await fetch(`${url}/api/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-API-Key": apiKey,
    },
    body: JSON.stringify({
      model,
      messages,
      stream: false,
      options: { num_predict: opts.numPredict ?? 1024 },
    }),
    // The gateway's ALB is known to rate-limit rapid successive calls and
    // Bedrock replies can be slow; give it real headroom.
    signal: AbortSignal.timeout(120_000),
  });

  const body = (await res.json().catch(() => null)) as GatewayChatResponse | null;

  if (!res.ok) {
    throw new Error(
      `LLM Gateway error ${res.status}: ${body?.error ?? JSON.stringify(body)}`
    );
  }

  const content = body?.message?.content;
  if (typeof content !== "string") {
    throw new Error(`LLM Gateway returned an unexpected shape: ${JSON.stringify(body)}`);
  }
  return content;
}
