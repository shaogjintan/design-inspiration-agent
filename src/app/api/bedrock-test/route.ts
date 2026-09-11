// Sanity-check route for the Bedrock LLM Gateway connection.
// Visit http://localhost:3000/api/bedrock-test (or `curl` it) after setting
// .env.local — remove this route once real features call gateway.ts instead.

import { NextResponse } from "next/server";
import { chatCompletion } from "@/lib/ai/gateway";

export async function GET() {
  try {
    const reply = await chatCompletion([
      { role: "user", content: "Say hello in exactly one short sentence." },
    ]);
    return NextResponse.json({ ok: true, reply });
  } catch (err) {
    return NextResponse.json(
      { ok: false, error: err instanceof Error ? err.message : String(err) },
      { status: 500 }
    );
  }
}
