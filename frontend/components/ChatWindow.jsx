import { useState, useRef, useEffect } from "react";
import { useChat } from "../src/ChatContext";
import { sendMessage, verifyPayment } from "../services/chatService";
import {
  Mic,
  SendHorizonal,
  Download,
  Volume2
} from "lucide-react";

export default function ChatWindow() {
  const handleRazorpayCheckout = (order, bookingId) => {
    const options = {
      key: order.key,
      amount: order.amount * 100,
      currency: order.currency,
      name: "SafarAI",
      description: `Payment for Booking #${bookingId}`,
      order_id: order.order_id,
      handler: async function (response) {
        setLoading(true);
        try {
          const verifyData = {
            booking_id: bookingId,
            razorpay_order_id: response.razorpay_order_id,
            razorpay_payment_id: response.razorpay_payment_id,
            razorpay_signature: response.razorpay_signature
          };
          const verification = await verifyPayment(verifyData);
          if (verification.status === "SUCCESS") {
            setMessages((prev) => [...prev, { 
              role: "assistant", 
              text: `Payment successful! ✅\nTransaction ID: ${response.razorpay_payment_id}\nBooking #${bookingId} is now CONFIRMED.`,
              bookingId 
            }]);
            // Send a ghost message to reset bot state if needed, or just let user know
          }
        } catch (err) {
          console.error(err);
          setMessages((prev) => [...prev, { role: "assistant", text: "Payment verification failed. Please contact support." }]);
        } finally {
          setLoading(false);
        }
      },
      prefill: {
        name: localStorage.getItem("name") || "Passenger",
        email: localStorage.getItem("email") || "passenger@example.com",
      },
      theme: { color: "#2563eb" },
    };

    const rzp = new window.Razorpay(options);
    rzp.open();
  };

  const { messages, setMessages, chatStarted, setChatStarted } = useChat();
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages]);

  const sendText = async (textToSend) => {
    if (!textToSend.trim() || loading) return;

    if (!chatStarted) setChatStarted(true);

    setInput("");
    setMessages((prev) => [...prev, { role: "user", text: textToSend }]);
    setLoading(true);
    try {
      const res = await sendMessage(textToSend);
      let botMessage = res.reply || res.response;
      let bookingId = res.booking_id || null;
      setMessages((prev) => [...prev, { role: "assistant", text: botMessage, bookingId }]);

      if (res.razorpay_order) {
        handleRazorpayCheckout(res.razorpay_order, res.booking_id);
      }
    } catch (err) {
      const detail = err?.response?.data?.detail || "Something went wrong.";
      const errorMsg = `Error: ${detail}`;
      setMessages((prev) => [...prev, { role: "assistant", text: errorMsg }]);
    } finally {
      setLoading(false);
    }
  };

  const submitMessage = (e) => {
    e.preventDefault();
    sendText(input);
    if (inputRef.current) {
      inputRef.current.focus();
    }
  };

  const handleDownloadReceipt = async (bookingId) => {
    try {
      const token = localStorage.getItem("token");
      const response = await fetch(`http://127.0.0.1:8000/ticket/${bookingId}`, {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });
      if (!response.ok) throw new Error("Failed to download receipt");
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `receipt_${bookingId}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      console.error(err);
      alert("Failed to download receipt. Please try again.");
    }
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
      const transcript = event.results[0][0].transcript;
      setInput(transcript);
      if (inputRef.current) {
        inputRef.current.focus();
      }
    };

    recognition.onerror = (event) => {
      console.error("Speech recognition error", event.error);
      setIsListening(false);
    };

    recognition.onend = () => {
      setIsListening(false);
      if (inputRef.current) {
        inputRef.current.focus();
      }
    };

    recognition.start();
  };

  const readMessage = (text) => {
    if (!window.speechSynthesis) return;
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    window.speechSynthesis.speak(utterance);
  };

  const copyToClipboard = (text) => {
    navigator.clipboard.writeText(text);
    // Optional: add a "copied" toast or tooltip
  };

  return (
    <div className={`chat-wrapper ${!chatStarted ? 'initial-state' : ''}`}>
      {chatStarted ? (
        <div className="messages-container">
          <div className="messages">
            {messages.map((m, i) => (
              <div key={i} className={`message ${m.role}`}>
                <div className="message-content" style={{ whiteSpace: 'pre-wrap' }}>{m.text}</div>

                {m.bookingId && m.text.toLowerCase().includes("payment successful") && (
                  <button
                    className="download-ticket-btn"
                    onClick={() => handleDownloadReceipt(m.bookingId)}
                  >
                    <Download size={18} />
                    Download Ticket
                  </button>
                )}

                {m.role === "assistant" && (
                  <div className="message-actions">
                    <button onClick={() => readMessage(m.text)} title="Read out loud"><Volume2 size={18} /></button>
                  </div>
                )}
              </div>
            ))}
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
                style={{ color: isListening ? '#f43f5e' : 'inherit' }}
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

// Add auto-scroll helper
export function useScrollToBottom(ref, messages) {
  useEffect(() => {
    if (ref.current) {
      ref.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages]);
}


