export async function POST(request: Request) {
  const body = await request.json();
  const baseUrl = process.env.API_GATEWAY_URL;
  if (!baseUrl) {
    return new Response(
      JSON.stringify({ error: "API_GATEWAY_URL is not configured" }),
      { status: 500, headers: { "Content-Type": "application/json" } }
    );
  }

  const response = await fetch(`${baseUrl}/agent/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body ?? {}),
  });

  return new Response(response.body, {
    status: response.status,
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
    },
  });
}

