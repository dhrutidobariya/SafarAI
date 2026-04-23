import api from "./api";

export async function sendMessage(message) {
  const { data } = await api.post("/chat", { message });
  return data;
}

export async function verifyPayment(paymentData) {
  const { data } = await api.post("/payment/verify", paymentData);
  return data;
}

export async function getBookingHistory() {
  const { data } = await api.get("/history");
  return data;
}

export async function downloadReceipt(bookingId) {
  const { data } = await api.get(`/ticket/${bookingId}`, { responseType: "blob" });
  return data;
}
