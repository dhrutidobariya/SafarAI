import { useState, useEffect } from "react";
import Sidebar from "../components/Sidebar";
import Header from "../components/Header";
import { Download } from "lucide-react";

export default function HistoryPage() {
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    const fetchHistory = async () => {
      try {
        const token = localStorage.getItem("token");
        const response = await fetch("http://127.0.0.1:8000/history", {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        });
        if (!response.ok) throw new Error("Failed to fetch history");
        const data = await response.json();
        setHistory(data);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };

    fetchHistory();
  }, []);

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
      const pdfBlob = new Blob([blob], { type: "application/pdf" });
      const url = window.URL.createObjectURL(pdfBlob);
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

  return (
    <div className="chat-layout">
      <Sidebar />
      <main className="content">
        <Header />
        <div className="page-padding">
          <h2>Booking & Payment History</h2>

        {loading && <p>Loading your history...</p>}
        {error && <p className="error">{error}</p>}

        {!loading && !error && (
          <div className="history-table-container">
            {history.length === 0 ? (
              <p>No bookings found. Start chatting to book a ticket!</p>
            ) : (
              <table>
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>Train</th>
                    <th>Source ➔ Dest</th>
                    <th>Seat(s) & Numbers</th>
                    <th>Total Fare</th>
                    <th>Payment ID</th>
                    <th>Receipt</th>
                  </tr>
                </thead>
                <tbody>
                  {history.map((item) => (
                    <tr key={item.id}>
                      <td>{new Date(item.created_at).toLocaleDateString()}</td>
                      <td>{item.train.train_name}</td>
                      <td>{item.train.source} ➔ {item.train.destination}</td>
                      <td>
                        <div style={{ fontWeight: 'bold' }}>{item.seats} {item.seat_preference ? `(${item.seat_preference})` : ''}</div>
                        <div style={{ fontSize: '0.85em', color: '#a5d6ff', marginTop: '4px' }}>
                          {item.seat_numbers || 'N/A'}
                        </div>
                      </td>
                      <td>₹{item.total_fare}</td>

                      <td>
                        {item.payment ? (
                          <span className="status-payment-success">
                            {item.payment.transaction_id}
                          </span>
                        ) : (
                          <span style={{ color: '#8b949e' }}>N/A</span>
                        )}
                      </td>
                      <td>
                        {item.status.toLowerCase() === 'confirmed' && item.payment ? (
                          <button
                            onClick={() => handleDownloadReceipt(item.id)}
                            className="download-receipt-btn"
                            title="Download Receipt"
                            style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: '#a5d6ff' }}
                          >
                            <Download size={20} />
                          </button>
                        ) : (
                          <span style={{ color: '#8b949e' }}>-</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}
      </div>
    </main>
  </div>
);
}
