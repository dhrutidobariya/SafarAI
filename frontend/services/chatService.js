import api from "./api";

export async function sendMessage(message) {
  const { data } = await api.post("/chat", { message });
  return data;
}
