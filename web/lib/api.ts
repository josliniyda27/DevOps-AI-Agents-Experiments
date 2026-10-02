import type { ChatResponse, HistoryTurn } from "./types";

export class ApiError extends Error {}

export async function askQuestion(question: string, history: HistoryTurn[], signal?: AbortSignal): Promise<ChatResponse> {
  let response: Response;
  try {
    response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, history }),
      signal,
    });
  } catch (error) {
    if ((error as Error).name === "AbortError") throw error;
    throw new ApiError("Can't reach the assistant. Check that the API server is running.");
  }

  if (response.status === 401) throw new ApiError("You are not signed in, or the site and API keys do not match. Reload the page and sign in again.");
  if (response.status === 422) throw new ApiError("That message is too long. Please shorten it.");
  if (!response.ok) throw new ApiError("The assistant couldn't complete the request. Please try again.");
  return response.json();
}

export async function checkHealth(signal?: AbortSignal): Promise<boolean> {
  try {
    return (await fetch("/api/health", { signal, cache: "no-store" })).ok;
  } catch {
    return false;
  }
}
