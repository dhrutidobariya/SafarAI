CREATE DATABASE IF NOT EXISTS railway_booking;
USE railway_booking;

CREATE TABLE IF NOT EXISTS users (
  id INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(100) NOT NULL,
  email VARCHAR(120) NOT NULL UNIQUE,
  hashed_password VARCHAR(255) NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS trains (
  id INT AUTO_INCREMENT PRIMARY KEY,
  train_name VARCHAR(100) NOT NULL,
  source VARCHAR(60) NOT NULL,
  destination VARCHAR(60) NOT NULL,
  travel_date DATE NOT NULL,
  departure_time VARCHAR(20) NOT NULL,
  arrival_time VARCHAR(20) NOT NULL,
  seats_available INT NOT NULL,
  fare_per_seat FLOAT NOT NULL
);

CREATE TABLE IF NOT EXISTS bookings (
  id INT AUTO_INCREMENT PRIMARY KEY,
  user_id INT NOT NULL,
  train_id INT NOT NULL,
  seats INT NOT NULL,
  seat_numbers VARCHAR(255) DEFAULT NULL,
  seat_preference VARCHAR(50) DEFAULT NULL,
  booking_date DATE NOT NULL,
  total_fare FLOAT NOT NULL,
  status VARCHAR(30) DEFAULT 'PENDING',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_bookings_user FOREIGN KEY (user_id) REFERENCES users(id),
  CONSTRAINT fk_bookings_train FOREIGN KEY (train_id) REFERENCES trains(id)
);

CREATE TABLE IF NOT EXISTS payments (
  id INT AUTO_INCREMENT PRIMARY KEY,
  booking_id INT NOT NULL UNIQUE,
  amount FLOAT NOT NULL,
  method VARCHAR(30) DEFAULT 'SIMULATED',
  transaction_id VARCHAR(120),
  status VARCHAR(20) NOT NULL,
  paid_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_payments_booking FOREIGN KEY (booking_id) REFERENCES bookings(id)
);

CREATE TABLE IF NOT EXISTS chat_history (
  id INT AUTO_INCREMENT PRIMARY KEY,
  user_id INT NOT NULL,
  role VARCHAR(20) NOT NULL,
  message TEXT NOT NULL,
  is_tool_message BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_chat_user FOREIGN KEY (user_id) REFERENCES users(id)
);

INSERT INTO trains (train_name, source, destination, travel_date, departure_time, arrival_time, seats_available, fare_per_seat) VALUES
('Rajdhani Express', 'New Delhi', 'Mumbai Central', CURDATE() + INTERVAL 1 DAY, '16:30', '08:15', 45, 4200.00),
('Gatiman Express', 'Delhi HN', 'Jhansi', CURDATE() + INTERVAL 1 DAY, '08:10', '12:35', 112, 1100.00),
('Vande Bharat Express', 'Varanasi', 'New Delhi', CURDATE() + INTERVAL 1 DAY, '15:00', '23:00', 204, 1850.00),
('Shatabdi Express', 'Bengaluru', 'Chennai', CURDATE() + INTERVAL 1 DAY, '06:00', '11:00', 88, 950.00),
('Howrah Mail', 'Mumbai CSMT', 'Howrah', CURDATE() + INTERVAL 1 DAY, '21:30', '06:30', 12, 2800.00),
('Deccan Queen', 'Pune', 'Mumbai CSMT', CURDATE() + INTERVAL 1 DAY, '07:15', '10:25', 310, 450.00),
('Grand Trunk Express', 'Chennai Central', 'New Delhi', CURDATE() + INTERVAL 1 DAY, '19:00', '15:30', 40, 3100.00),
('Coromandel Express', 'Howrah', 'Chennai Central', CURDATE() + INTERVAL 1 DAY, '15:20', '17:00', 5, 2600.00),
('Golden Chariot', 'Bengaluru', 'Goa', CURDATE() + INTERVAL 1 DAY, '20:00', '09:00', 12, 15000.00),
('Brindavan Express', 'Chennai', 'Bengaluru', CURDATE() + INTERVAL 1 DAY, '07:40', '13:45', 450, 250.00),
('August Kranti Rajdhani', 'Mumbai Central', 'Hazrat Nizamuddin', CURDATE() + INTERVAL 1 DAY, '17:40', '09:45', 60, 4100.00),
('Saraighat Express', 'Howrah', 'Guwahati', CURDATE() + INTERVAL 1 DAY, '15:50', '09:30', 15, 2200.00),
('Tamil Nadu Express', 'New Delhi', 'Chennai Central', CURDATE() + INTERVAL 1 DAY, '22:30', '06:15', 22, 3300.00),
('Duronto Express', 'Sealdah', 'New Delhi', CURDATE() + INTERVAL 1 DAY, '16:50', '10:30', 95, 3800.00),
('Flying Ranee', 'Surat', 'Mumbai Central', CURDATE() + INTERVAL 1 DAY, '05:25', '09:40', 200, 180.00),
('Mandovi Express', 'Mumbai CSMT', 'Madgaon', CURDATE() + INTERVAL 1 DAY, '07:10', '19:15', 140, 1200.00),
('Sabarmati Express', 'Ahmedabad', 'Varanasi', CURDATE() + INTERVAL 1 DAY, '23:10', '11:20', 30, 1600.00),
('Taj Express', 'New Delhi', 'Jhansi', CURDATE() + INTERVAL 1 DAY, '06:45', '14:00', 210, 350.00),
('Godavari Express', 'Visakhapatnam', 'Hyderabad', CURDATE() + INTERVAL 1 DAY, '17:20', '05:45', 55, 1450.00),
('Kerala Express', 'New Delhi', 'Trivandrum', CURDATE() + INTERVAL 1 DAY, '11:25', '13:15', 10, 3900.00),
('Humsafar Express', 'Lucknow', 'Anand Vihar', CURDATE() + INTERVAL 1 DAY, '23:10', '07:00', 300, 1350.00),
('Double Decker Express', 'Jaipur', 'Delhi Sarai Rohilla', CURDATE() + INTERVAL 1 DAY, '06:00', '10:30', 150, 650.00),
('Netaji Express', 'Howrah', 'Kalka', CURDATE() + INTERVAL 1 DAY, '20:00', '03:00', 18, 2900.00),
('Garib Rath', 'Patna', 'Kolkata', CURDATE() + INTERVAL 1 DAY, '20:10', '05:00', 400, 750.00),
('Uday Express', 'Coimbatore', 'Bengaluru', CURDATE() + INTERVAL 1 DAY, '05:45', '12:40', 120, 800.00),
('Tejas Express', 'Ahmedabad', 'Mumbai Central', CURDATE() + INTERVAL 1 DAY, '06:40', '13:05', 85, 2200.00),
('Kanyakumari Express', 'Bengaluru', 'Kanyakumari', CURDATE() + INTERVAL 1 DAY, '17:15', '09:00', 12, 1900.00),
('Charminar Express', 'Hyderabad', 'Chennai', CURDATE() + INTERVAL 1 DAY, '18:30', '08:00', 110, 1500.00),
('Sanghamitra Express', 'Bengaluru', 'Patna', CURDATE() + INTERVAL 1 DAY, '10:00', '10:00', 5, 3400.00),
('Navjivan Express', 'Ahmedabad', 'Chennai', CURDATE() + INTERVAL 1 DAY, '06:40', '16:00', 220, 2700.00);
