import { NextResponse } from "next/server";

export async function POST(request: Request) {
  const body = await request.json();
  const baseUrl = process.env.API_GATEWAY_URL;
  if (!baseUrl) {
    return NextResponse.json(
      { error: "API_GATEWAY_URL is not configured" },
      { status: 500 }
    );
  }

  try {
    const response = await fetch(`${baseUrl}/recommendations`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body ?? {}),
      cache: "no-store",
    });

    const data = await response.json();
    return NextResponse.json(data, { status: response.status });
  } catch {
    return NextResponse.json(
      { error: "agent_service_unavailable" },
      { status: 502 }
    );
  }
}

