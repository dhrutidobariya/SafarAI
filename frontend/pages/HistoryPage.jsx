import { useEffect, useState } from "react";
import { Download } from "lucide-react";
import Header from "../components/Header";
import Sidebar from "../components/Sidebar";
import { downloadReceipt, getBookingHistory } from "../services/chatService";

function formatCurrency(amount) {
  return `Rs. ${Number(amount || 0).toLocaleString("en-IN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
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

export default function HistoryPage() {
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    const fetchHistory = async () => {
      try {
        const data = await getBookingHistory();
        setHistory(data);
      } catch (err) {
        setError(err?.response?.data?.detail || "Failed to fetch history");
      } finally {
        setLoading(false);
      }
    };

    fetchHistory();
  }, []);

  const handleDownloadReceipt = async (bookingId) => {
    try {
      const blob = await downloadReceipt(bookingId);
      saveReceipt(blob, bookingId);
    } catch (err) {
      console.error(err);
      alert("Failed to download receipt. Please try again.");
    }
  };

  return (
    <div className="chat-layout">
      <Sidebar />
      <main className="content">
        <Header />
        <div className="page-padding">
          <h2>Booking & Payment History</h2>

          {loading ? <p>Loading your history...</p> : null}
          {error ? <p className="error">{error}</p> : null}

          {!loading && !error ? (
            <div className="history-table-container">
              {history.length === 0 ? (
                <p>No bookings found. Start chatting to book a ticket.</p>
              ) : (
                <table>
                  <thead>
                    <tr>
                      <th>Date</th>
                      <th>Train</th>
                      <th>Route</th>
                      <th>Seat Details</th>
                      <th>Status</th>
                      <th>Total Fare</th>
                      <th>Transaction ID</th>
                      <th>Receipt</th>
                    </tr>
                  </thead>
                  <tbody>
                    {history.map((item) => {
                      const isConfirmed =
                        item.status?.toUpperCase() === "CONFIRMED" &&
                        item.payment?.status?.toUpperCase() === "SUCCESS";

                      return (
                        <tr key={item.id}>
                          <td>{new Date(item.created_at).toLocaleDateString("en-IN")}</td>
                          <td>{item.train?.train_name}</td>
                          <td>
                            {item.train?.source} to {item.train?.destination}
                          </td>
                          <td>
                            <div style={{ fontWeight: "bold" }}>
                              {item.seats} seat{item.seats > 1 ? "s" : ""} ({item.seat_preference || "No Preference"})
                            </div>
                            <div style={{ fontSize: "0.85em", color: "#6b7280", marginTop: "4px" }}>
                              {item.seat_numbers || "Pending assignment"}
                            </div>
                          </td>
                          <td>
                            <span className={`status-badge ${isConfirmed ? "status-confirmed" : "status-pending"}`}>
                              {item.status}
                            </span>
                          </td>
                          <td>{formatCurrency(item.total_fare)}</td>
                          <td>
                            {item.payment?.transaction_id ? (
                              <span className="status-payment-success">{item.payment.transaction_id}</span>
                            ) : (
                              <span style={{ color: "#8b949e" }}>N/A</span>
                            )}
                          </td>
                          <td>
                            {isConfirmed ? (
                              <button
                                onClick={() => handleDownloadReceipt(item.id)}
                                className="download-receipt-btn"
                                title="Download Receipt"
                                style={{
                                  background: "transparent",
                                  border: "none",
                                  cursor: "pointer",
                                  color: "#389fff",
                                  padding: 0,
                                }}
                              >
                                <Download size={20} />
                              </button>
                            ) : (
                              <span style={{ color: "#8b949e" }}>-</span>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              )}
            </div>
          ) : null}
        </div>
      </main>
    </div>
  );
}
