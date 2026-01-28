'use server'

const API_GATEWAY_URL = process.env.API_GATEWAY_URL || 'http://localhost:8080';

export async function getFlaskStatus() {
  try {
    const res = await fetch(`${API_GATEWAY_URL}/flask`, { cache: 'no-store' });
    if (!res.ok) {
        // Handle non-200 responses specifically if needed, or just return text
        return { error: `Error: ${res.status} ${res.statusText}` };
    }
    const data = await res.json();
    return data;
  } catch (error: any) {
    console.error("Failed to fetch flask status:", error);
    return { error: error.message || String(error) };
  }
}

export async function runFlaskTest() {
  try {
    const res = await fetch(`${API_GATEWAY_URL}/flask/test-infrastructure`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ test: true }),
      cache: 'no-store',
    });
     if (!res.ok) {
        return { error: `Error: ${res.status} ${res.statusText}` };
    }
    const data = await res.json();
    return data;
  } catch (error: any) {
    console.error("Failed to run flask test:", error);
    return { error: error.message || String(error) };
  }
}
