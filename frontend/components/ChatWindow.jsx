import { useEffect, useRef, useState } from "react";
import { useChat } from "../src/ChatContext";
import { downloadReceipt, sendMessage, verifyPayment } from "../services/chatService";
import {
  CheckCircle2,
  Download,
  Mic,
  SendHorizonal,
  Volume2,
  VolumeX,
} from "lucide-react";

function formatCurrency(amount) {
  return `Rs. ${Number(amount || 0).toLocaleString("en-IN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

function formatDateTime(value) {
  if (!value) {
    return "N/A";
  }

  return new Date(value).toLocaleString("en-IN", {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

function saveReceipt(blob, bookingId) {
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `receipt_${bookingId}.pdf`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
}

export default function ChatWindow() {
  const { messages, setMessages, chatStarted, setChatStarted } = useChat();
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const [speakingMessageIndex, setSpeakingMessageIndex] = useState(null);
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);
  const utteranceRef = useRef(null);

  const appendAssistantMessage = (message) => {
    setMessages((prev) => [...prev, { role: "assistant", ...message }]);
  };

  const handleReceiptDownload = async (bookingId) => {
    try {
      const blob = await downloadReceipt(bookingId);
      saveReceipt(blob, bookingId);
    } catch (err) {
      console.error(err);
      alert("Failed to download receipt. Please try again.");
    }
  };

  const handlePaymentSuccess = async (paymentData, bookingId) => {
    setLoading(true);
    try {
      const verification = await verifyPayment(paymentData);
      const booking = verification.booking;
      appendAssistantMessage({
        text:
          `Payment successful. Booking #${bookingId} is now confirmed.\n` +
          `PNR: ${booking?.pnr || "N/A"}\n` +
          `Receipt No: ${booking?.receipt_number || "N/A"}`,
        bookingId,
        bookingData: booking || null,
        paymentStatus: verification.payment_status || verification.status,
      });
    } catch (err) {
      console.error(err);
      appendAssistantMessage({
        text: err?.response?.data?.detail || "Payment verification failed. Please contact support.",
      });
    } finally {
      setLoading(false);
    }
  };

  const handleDemoPayment = async (order, bookingId) => {
    const proceed = window.confirm(
      `${order.message || "Demo payment mode is active."}\n\nPress OK to simulate a successful payment.`
    );

    if (!proceed) {
      appendAssistantMessage({
        text: "Demo payment was cancelled before completion.",
      });
      return;
    }

    await handlePaymentSuccess(
      {
        booking_id: bookingId,
        provider: "SIMULATED",
        razorpay_payment_id: order.order_id,
      },
      bookingId
    );
  };

  const handleRazorpayCheckout = (order, bookingId) => {
    if (order?.status === "ALREADY_PAID") {
      appendAssistantMessage({
        text: order.message || "This booking is already confirmed.",
        bookingId,
        paymentStatus: "SUCCESS",
      });
      return;
    }

    if (order?.provider === "SIMULATED") {
      handleDemoPayment(order, bookingId);
      return;
    }

    if (!order?.key || !order?.order_id) {
      appendAssistantMessage({
        text: "Payment could not be initialized. Please try again.",
      });
      return;
    }

    if (!window.Razorpay) {
      appendAssistantMessage({
        text: "Payment gateway failed to load. Refresh the page and try again.",
      });
      return;
    }

    const options = {
      key: order.key,
      amount: Math.round(Number(order.amount || 0) * 100),
      currency: order.currency,
      name: "Safar AI",
      description: `Payment for Booking #${bookingId}`,
      order_id: order.order_id,
      handler: async function (response) {
        await handlePaymentSuccess(
          {
            booking_id: bookingId,
            provider: "RAZORPAY",
            razorpay_order_id: response.razorpay_order_id,
            razorpay_payment_id: response.razorpay_payment_id,
            razorpay_signature: response.razorpay_signature,
          },
          bookingId
        );
      },
      prefill: {
        name: localStorage.getItem("name") || "Passenger",
        email: localStorage.getItem("email") || "passenger@example.com",
      },
      modal: {
        ondismiss: () => {
          appendAssistantMessage({
            text: "Payment was cancelled before completion.",
          });
        },
      },
      theme: { color: "#2563eb" },
    };

    const rzp = new window.Razorpay(options);
    rzp.open();
  };

  useEffect(() => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages]);

  useEffect(() => {
    return () => {
      if (window.speechSynthesis) {
        window.speechSynthesis.cancel();
      }
    };
  }, []);

  const sendText = async (textToSend) => {
    if (!textToSend.trim() || loading) {
      return;
    }

    if (!chatStarted) {
      setChatStarted(true);
    }

    setInput("");
    setMessages((prev) => [...prev, { role: "user", text: textToSend }]);
    setLoading(true);

    try {
      const res = await sendMessage(textToSend);
      const assistantMessage = {
        role: "assistant",
        text: res.reply || res.response || "No response received.",
        bookingId: res.booking_id || null,
        bookingData: res.booking || null,
        paymentStatus: res.payment_status || null,
      };
      setMessages((prev) => [...prev, assistantMessage]);

      if (res.razorpay_order && res.booking_id) {
        handleRazorpayCheckout(res.razorpay_order, res.booking_id);
      }
    } catch (err) {
      const detail = err?.response?.data?.detail || "Something went wrong.";
      appendAssistantMessage({ text: `Error: ${detail}` });
    } finally {
      setLoading(false);
    }
  };

  const submitMessage = (e) => {
    e.preventDefault();
    sendText(input);
    inputRef.current?.focus();
  };

  const startListening = () => {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      alert("Your browser does not support speech recognition.");
      return;
    }

    const recognition = new SpeechRecognition();
    recognition.lang = "en-US";
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;

    recognition.onstart = () => setIsListening(true);
    recognition.onresult = (event) => {
      setInput(event.results[0][0].transcript);
      inputRef.current?.focus();
    };
    recognition.onerror = (event) => {
      console.error("Speech recognition error", event.error);
      setIsListening(false);
    };
    recognition.onend = () => {
      setIsListening(false);
      inputRef.current?.focus();
    };

    recognition.start();
  };

  const stopReading = () => {
    if (!window.speechSynthesis) {
      return;
    }

    window.speechSynthesis.cancel();
    utteranceRef.current = null;
    setSpeakingMessageIndex(null);
  };

  const readMessage = (text, messageIndex) => {
    if (!window.speechSynthesis) {
      return;
    }

    if (speakingMessageIndex === messageIndex && window.speechSynthesis.speaking) {
      stopReading();
      return;
    }

    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utteranceRef.current = utterance;
    setSpeakingMessageIndex(messageIndex);

    utterance.onend = () => {
      if (utteranceRef.current === utterance) {
        utteranceRef.current = null;
        setSpeakingMessageIndex(null);
      }
    };
    utterance.onerror = () => {
      if (utteranceRef.current === utterance) {
        utteranceRef.current = null;
        setSpeakingMessageIndex(null);
      }
    };

    window.speechSynthesis.speak(utterance);
  };

  return (
    <div className={`chat-wrapper ${!chatStarted ? "initial-state" : ""}`}>
      {chatStarted ? (
        <div className="messages-container">
          <div className="messages">
            {messages.map((message, index) => {
              const isConfirmed =
                message.paymentStatus === "SUCCESS" || message.bookingData?.status === "CONFIRMED";

              return (
                <div key={index} className={`message ${message.role}`}>
                  <div className="message-content" style={{ whiteSpace: "pre-wrap" }}>
                    {message.text}
                  </div>

                  {message.bookingData && (
                    <div className={`booking-card ${isConfirmed ? "confirmed" : "pending"}`}>
                      <div className="booking-card-header">
                        <div>
                          <strong>{message.bookingData.train?.train_name || "Booking"}</strong>
                          <div className="booking-card-subtitle">
                            {message.bookingData.train?.source} to {message.bookingData.train?.destination}
                          </div>
                        </div>
                        <div className={`booking-state ${isConfirmed ? "success" : "awaiting"}`}>
                          {isConfirmed ? <CheckCircle2 size={16} /> : null}
                          <span>{message.bookingData.status}</span>
                        </div>
                      </div>

                      <div className="booking-card-grid">
                        <div>
                          <span>Booking ID</span>
                          <strong>#{message.bookingData.id}</strong>
                        </div>
                        <div>
                          <span>PNR</span>
                          <strong>{message.bookingData.pnr}</strong>
                        </div>
                        <div>
                          <span>Seats</span>
                          <strong>{message.bookingData.seats}</strong>
                        </div>
                        <div>
                          <span>Total Fare</span>
                          <strong>{formatCurrency(message.bookingData.total_fare)}</strong>
                        </div>
                        <div>
                          <span>Seat Preference</span>
                          <strong>{message.bookingData.seat_preference || "No Preference"}</strong>
                        </div>
                        <div>
                          <span>Receipt No</span>
                          <strong>{message.bookingData.receipt_number || "Pending"}</strong>
                        </div>
                      </div>

                      <div className="booking-card-meta">
                        <div>Seat Numbers: {message.bookingData.seat_numbers || "Will be assigned shortly"}</div>
                        <div>
                          Travel: {message.bookingData.booking_date} | Departure:{" "}
                          {message.bookingData.train?.departure_time || "N/A"} | Arrival:{" "}
                          {message.bookingData.train?.arrival_time || "N/A"}
                        </div>
                        {message.bookingData.payment?.transaction_id ? (
                          <div>
                            Transaction ID: {message.bookingData.payment.transaction_id} | Paid on{" "}
                            {formatDateTime(message.bookingData.payment.paid_at)}
                          </div>
                        ) : null}
                      </div>

                      {isConfirmed ? (
                        <button
                          className="download-ticket-btn"
                          onClick={() => handleReceiptDownload(message.bookingData.id)}
                        >
                          <Download size={18} />
                          Download Receipt
                        </button>
                      ) : null}
                    </div>
                  )}

                  {message.bookingId && !message.bookingData && isConfirmed ? (
                    <button
                      className="download-ticket-btn"
                      onClick={() => handleReceiptDownload(message.bookingId)}
                    >
                      <Download size={18} />
                      Download Receipt
                    </button>
                  ) : null}

                  {message.role === "assistant" ? (
                    <div className="message-actions">
                      <button
                        onClick={() => readMessage(message.text, index)}
                        title={speakingMessageIndex === index ? "Stop reading" : "Read out loud"}
                        aria-pressed={speakingMessageIndex === index}
                      >
                        {speakingMessageIndex === index ? <VolumeX size={18} /> : <Volume2 size={18} />}
                      </button>
                    </div>
                  ) : null}
                </div>
              );
            })}
            <div ref={messagesEndRef} />
          </div>
        </div>
      ) : (
        <div className="welcome-hero">
          <h1>Where should we begin?</h1>
        </div>
      )}

      <div className="input-area">
        <form className="chat-input-container" onSubmit={submitMessage}>
          <div className="chat-input-wrapper">
            <input
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Ask anything"
            />

            <div className="chat-input-actions">
              <button
                type="button"
                className="icon-btn"
                title="Voice search"
                onClick={startListening}
                style={{ color: isListening ? "#f43f5e" : "inherit" }}
              >
                <Mic size={20} />
              </button>
              <button type="submit" className="send-btn" disabled={!input.trim() || loading}>
                {loading ? "..." : <SendHorizonal size={20} />}
              </button>
            </div>
          </div>
        </form>
      </div>
    </div>
  );
}

export function useScrollToBottom(ref, messages) {
  useEffect(() => {
    if (ref.current) {
      ref.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages]);
}
