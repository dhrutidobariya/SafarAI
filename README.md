# Railway Ticket Booking Chatbot

Full-stack railway ticket booking chatbot with live RapidAPI train search.

## Tech Stack
- Frontend: React + Vite
- Backend: FastAPI
- Database: MySQL
- Train Search: RapidAPI

## Backend Setup
1. Create and seed database:
   - Open MySQL and run `database/schema.sql`
2. Configure env:
   - Copy `backend/.env.example` to `backend/.env`
   - Fill `DATABASE_URL`, `JWT_SECRET_KEY`, `RAPIDAPI_KEY`
3. Install and run:
   - `cd backend`
   - `python -m venv .venv`
   - `.venv\Scripts\activate`
   - `pip install -r requirements.txt`
   - `uvicorn main:app --reload --port 8000`

## Frontend Setup
1. Install and run:
   - `cd frontend`
   - `npm install`
   - `npm run dev`

Frontend runs at `http://localhost:5173`, backend at `http://127.0.0.1:8000`.

## API Endpoints
- `POST /chat`
- `GET /trains`
- `POST /book`
- `POST /payment/order`
- `POST /payment/verify`
- `GET /history`

Flow:
User Input -> Chat State Manager -> RapidAPI Train Search -> Booking Snapshot -> Payment / Receipt
