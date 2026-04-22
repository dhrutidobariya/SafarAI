# Railway Ticket Booking MCP System

Full-stack chatbot railway ticket booking system with MCP-style tool calling.

## Tech Stack
- Frontend: React + Vite
- Backend: FastAPI
- Database: MySQL
- AI: OpenAI API with MCP tool orchestration

## Backend Setup
1. Create and seed database:
   - Open MySQL and run `database/schema.sql`
2. Configure env:
   - Copy `backend/.env.example` to `backend/.env`
   - Fill `DATABASE_URL`, `JWT_SECRET_KEY`, `OPENAI_API_KEY`
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

## MCP Tools Implemented
- `search_trains(source, destination, travel_date)`
- `check_availability(train_id, seats)`
- `book_ticket(user_id, train_id, seats, travel_date)`
- `process_payment(booking_id, amount)`
- `generate_ticket(booking_id)`

Flow:
User Input -> LLM Parser -> MCP Tool Calls -> Backend Logic -> Tool Results -> Final Bot Reply
