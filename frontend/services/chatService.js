import api from "./api";

export async function sendMessage(message) {
  const { data } = await api.post("/chat", { message });
  return data;
}

export async function verifyPayment(paymentData) {
  const { data } = await api.post("/payment/verify", paymentData);
  return data;
}
