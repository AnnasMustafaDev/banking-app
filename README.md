# Bank App - Account Management System

A FastAPI-based banking application with deposits, withdrawals, transfers, and comprehensive account management features.

## Features Implemented

### ✅ Core Banking Operations
- **Deposits**: Deposit funds without limits
- **Withdrawals**: Withdraw funds with balance validation
- **Transfers**: Transfer funds between accounts with advanced controls

### ✅ Security & Reliability
- **Idempotency Keys**: Prevent duplicate transfers (24-hour TTL)
- **Concurrent Transaction Handling**: Thread-safe operations with proper locking
- **Race Condition Prevention**: Consistent lock ordering to prevent deadlocks

### ✅ Limits & Validations
- **Per-Transfer Limit**: Max $10,000 per transfer
- **Daily Transfer Limit**: Max $25,000 per account per day
- **Rate Limiting**: 10 transfers per minute per account
- **Balance Validation**: Ensure sufficient funds for all operations

### ✅ Ledger & History
- **Transaction Ledger**: Complete record of all transactions
- **Paginated History**: Get transaction history with cursor-based pagination
- **Account Summary**: Balance, daily transfer totals, and transaction count

## Project Structure

```
bank_app/
├── main.py              # FastAPI backend application
├── static/
│   └── index.html       # Frontend interface
├── test_main.py         # Comprehensive test suite
├── run_tests.py         # Test runner script
├── requirements.txt     # Python dependencies
└── README.md           # This file
```

## Installation & Setup

### 1. Create Virtual Environment (Optional but Recommended)
```bash
cd d:\bank_app
python -m venv venv
venv\Scripts\activate  # On Windows
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

## Running the Application

### Start the Server
```bash
python -m uvicorn main:app --reload --port 8000
```

The application will be available at:
- **Backend API**: http://localhost:8000
- **Frontend UI**: http://localhost:8000
- **API Documentation**: http://localhost:8000/docs (Swagger UI)

### Access the Frontend
Open your browser and navigate to `http://localhost:8000`

## Running Tests

### Run All Tests
```bash
python run_tests.py
```

### Or run pytest directly
```bash
pytest test_main.py -v
```

### Run Specific Test Class
```bash
pytest test_main.py::TestTransfers -v
```

### Run with Coverage
```bash
pytest test_main.py --cov=main --cov-report=html
```

## Test Coverage

The test suite includes 40+ tests covering:

### Basic Operations
- ✅ Health check
- ✅ Balance retrieval
- ✅ Deposits (basic, multiple, large amounts)
- ✅ Withdrawals (basic, insufficient funds, all funds)

### Transfer Features
- ✅ Successful transfers
- ✅ Insufficient funds handling
- ✅ Per-transfer limit enforcement ($10,000 max)
- ✅ Daily transfer limit enforcement ($25,000 max)
- ✅ Same-account transfers

### Idempotency
- ✅ Idempotency key prevents duplicates
- ✅ Different keys create different transfers
- ✅ Replay detection with TTL

### Rate Limiting
- ✅ 10 transfers per minute per account
- ✅ Rate limit properly tracked
- ✅ Per-account rate limiting

### Concurrency
- ✅ Concurrent transfers to same recipient
- ✅ Concurrent transfers from same sender
- ✅ Concurrent withdraw and transfer

### Transaction History
- ✅ Basic transaction history retrieval
- ✅ Pagination with limit and cursor
- ✅ Empty account history

### Validation
- ✅ Invalid amounts (zero, negative)
- ✅ Missing required fields

## API Endpoints

### Account Operations

#### Get Balance
```bash
GET /balance/{account_id}
```

#### Get Account Summary
```bash
GET /accounts/{account_id}/summary
```

### Transactions

#### Deposit
```bash
POST /deposit
{
  "account_id": "user1",
  "amount": 1000
}
```

#### Withdraw
```bash
POST /withdraw
{
  "account_id": "user1",
  "amount": 500
}
```

#### Transfer (with optional idempotency)
```bash
POST /transfer
Headers: idempotency-key: <optional-uuid>
{
  "from_account": "user1",
  "to_account": "user2",
  "amount": 100
}
```

#### Get Transaction History (Paginated)
```bash
GET /accounts/{account_id}/transactions?limit=10&cursor=0
```

### System

#### Health Check
```bash
GET /health
```

## API Documentation

When running locally, interactive API documentation is available at:
- **Swagger UI**: http://localhost:8000/docs/
- **ReDoc**: http://localhost:8000/redoc

## Frontend Features

The web interface provides:
- 📊 Account information and balance display
- 💰 Deposit and withdrawal operations
- 📤 Transfer with idempotency support
- 📋 Transaction history with pagination
- 🔍 Account summary with daily transfer limits
- ✅ Real-time validation and error handling

## Configuration

Edit these constants in `main.py` to customize limits:

```python
PER_TRANSFER_MAX = 10_000              # Max per transfer
DAILY_TRANSFER_LIMIT = 25_000          # Max daily per account
IDEMPOTENCY_TTL_SECONDS = 60 * 60 * 24 # 24 hours
RATE_LIMIT_PER_MINUTE = 10             # Transfers per minute
```

## Thread Safety

The application uses:
- **threading.Lock**: Per-account locks prevent race conditions
- **Lock ordering**: Sorted account IDs prevent deadlocks
- **Atomic operations**: Critical sections are properly protected

Example: When transferring between user1 and user3, locks are acquired in order: user1, then user3 (sorted), ensuring consistent ordering even if another thread tries user3 → user1.

## Error Handling

All errors return appropriate HTTP status codes:

| Status Code | Meaning |
|------------|---------|
| 200 | Success |
| 400 | Bad request (insufficient funds, limits exceeded) |
| 422 | Validation error (invalid input) |
| 429 | Rate limit exceeded |
| 500 | Server error |

## Known Limitations

This is a demonstration application with these limitations:
- **In-memory storage**: Data is lost on server restart
- **No authentication**: No user authentication implemented
- **No persistence**: Data not stored in database
- **Single server**: Not designed for multi-server deployment

For production use, consider:
- Adding a persistent database (PostgreSQL, MongoDB)
- Implementing proper authentication/authorization
- Using distributed caching for rate limiting (Redis)
- Adding comprehensive logging and monitoring

## Development Notes

### Idempotency Implementation
- Stores responses with TTL of 24 hours
- Uses provided idempotency-key header
- Returns cached response if key exists and not expired
- Prevents duplicate charges from retries

### Rate Limiting Strategy
- Tracks timestamps of requests per account
- Removes timestamps older than 60 seconds
- Simple sliding window implementation
- Can be enhanced with Redis for distributed systems

### Concurrency Handling
- Each account has its own lock
- Transactions acquire locks in sorted order of accounts
- Prevents deadlocks while ensuring atomicity
- Handles concurrent deposits/withdrawals safely

## Example Usage

### 1. Deposit Money
```bash
curl -X POST http://localhost:8000/deposit \
  -H "Content-Type: application/json" \
  -d '{"account_id": "user1", "amount": 1000}'
```

### 2. Check Balance
```bash
curl http://localhost:8000/balance/user1
```

### 3. Transfer Money
```bash
curl -X POST http://localhost:8000/transfer \
  -H "Content-Type: application/json" \
  -H "idempotency-key: 550e8400-e29b-41d4-a716-446655440000" \
  -d '{
    "from_account": "user1",
    "to_account": "user2",
    "amount": 100
  }'
```

### 4. Get Transaction History
```bash
curl "http://localhost:8000/accounts/user1/transactions?limit=10&cursor=0"
```

## Support

For issues or questions, check:
1. Test suite for usage examples
2. Frontend code in `static/index.html`
3. API endpoint implementations in `main.py`
