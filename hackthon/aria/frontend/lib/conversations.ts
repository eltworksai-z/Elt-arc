import { post } from "./api";

export async function startConversation(firstMessage?: string): Promise<string> {
  const session = await post<{ session_id: string }>("/api/sessions", {});
  if (firstMessage) await post(`/api/sessions/${session.session_id}/messages`, { text: firstMessage, source: "text" });
  return session.session_id;
}
