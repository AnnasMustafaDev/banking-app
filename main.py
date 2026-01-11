from fastapi import FastAPI, HTTPException, Header
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, List
from uuid import uuid4
from datetime import datetime, timedelta
import threading
import time

app = FastAPI()

# ----------------------------
# CORS Configuration
# ----------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------------------
# Configuration
# ----------------------------
PER_TRANSFER_MAX = 10_000
DAILY_TRANSFER_LIMIT = 25_000
IDEMPOTENCY_TTL_SECONDS = 60 * 60 * 24  # 24 hours
RATE_LIMIT_PER_MINUTE = 10

# ----------------------------
# In-memory storage
# ----------------------------
accounts = {}            # account_id -> balance
ledger = {}              # account_id -> list of ledger entries
account_locks = {}       # account_id -> threading.Lock

idempotency_store = {}   # key -> {response, expires_at}
rate_limits = {}         # account_id -> [timestamps]

# ----------------------------
# Models
# ----------------------------
class AmountRequest(BaseModel):
    account_id: str
    amount: int = Field(gt=0)

class TransferRequest(BaseModel):
    from_account: str
    to_account: str
    amount: int = Field(gt=0)

class LedgerEntry(BaseModel):
    tx_id: str
    type: str
    amount: int
    balance_after: int
    timestamp: datetime

# ----------------------------
# Helpers
# ----------------------------
def get_lock(account_id: str):
    """Get or create a lock for an account"""
    if account_id not in account_locks:
        account_locks[account_id] = threading.Lock()
    return account_locks[account_id]

def check_rate_limit(account_id: str):
    """Check and enforce rate limit (10 transfers/minute per account)"""
    now = time.time()
    timestamps = rate_limits.get(account_id, [])
    # Remove timestamps older than 60 seconds
    timestamps = [t for t in timestamps if now - t < 60]

    if len(timestamps) >= RATE_LIMIT_PER_MINUTE:
        raise HTTPException(status_code=429, detail="Rate limit exceeded: max 10 transfers per minute")

    timestamps.append(now)
    rate_limits[account_id] = timestamps

def check_idempotency(key: str):
    """Check if idempotency key exists and is still valid"""
    record = idempotency_store.get(key)
    if record and record["expires_at"] > time.time():
        return record["response"]
    return None

def store_idempotency(key: str, response):
    """Store idempotency key with TTL"""
    idempotency_store[key] = {
        "response": response,
        "expires_at": time.time() + IDEMPOTENCY_TTL_SECONDS
    }

def get_daily_transfer_total(account_id: str):
    """Get total transfers made today from account"""
    today = datetime.utcnow().date()
    total = 0
    for entry in ledger.get(account_id, []):
        if entry["type"] == "transfer_out" and entry["timestamp"].date() == today:
            total += abs(entry["amount"])
    return total

def ensure_account(account_id: str):
    """Initialize account if it doesn't exist"""
    if account_id not in accounts:
        accounts[account_id] = 0
        ledger[account_id] = []

# ----------------------------
# Endpoints
# ----------------------------

@app.get("/")
def root():
    """Serve the frontend"""
    return FileResponse("static/index.html")

@app.get("/balance/{account_id}")
def get_balance(account_id: str):
    """Get current balance of an account"""
    ensure_account(account_id)
    return {
        "account_id": account_id,
        "balance": accounts[account_id]
    }

@app.post("/deposit")
def deposit(req: AmountRequest):
    """Deposit funds into an account (no limit)"""
    ensure_account(req.account_id)
    lock = get_lock(req.account_id)

    with lock:
        accounts[req.account_id] += req.amount
        entry = {
            "tx_id": str(uuid4()),
            "type": "deposit",
            "amount": req.amount,
            "balance_after": accounts[req.account_id],
            "timestamp": datetime.utcnow()
        }
        ledger[req.account_id].append(entry)

    return entry

@app.post("/withdraw")
def withdraw(req: AmountRequest):
    """Withdraw funds from an account"""
    ensure_account(req.account_id)
    lock = get_lock(req.account_id)

    with lock:
        if accounts[req.account_id] < req.amount:
            raise HTTPException(status_code=400, detail="Insufficient funds")

        accounts[req.account_id] -= req.amount
        entry = {
            "tx_id": str(uuid4()),
            "type": "withdrawal",
            "amount": -req.amount,
            "balance_after": accounts[req.account_id],
            "timestamp": datetime.utcnow()
        }
        ledger[req.account_id].append(entry)

    return entry

@app.post("/transfer")
def transfer(
    req: TransferRequest,
    idempotency_key: Optional[str] = Header(None)
):
    """
    Transfer funds between accounts with idempotency support.
    Include 'idempotency-key' header to ensure idempotent transfers.
    """
    # Check per-transfer limit
    if req.amount > PER_TRANSFER_MAX:
        raise HTTPException(
            status_code=400,
            detail=f"Per-transfer limit exceeded: max {PER_TRANSFER_MAX}"
        )

    # Check idempotency key
    if idempotency_key:
        cached = check_idempotency(idempotency_key)
        if cached:
            return cached

    ensure_account(req.from_account)
    ensure_account(req.to_account)

    # Check rate limit
    check_rate_limit(req.from_account)

    # Prevent deadlock by consistent lock order
    first, second = sorted([req.from_account, req.to_account])
    with get_lock(first), get_lock(second):

        # Check daily transfer limit
        if get_daily_transfer_total(req.from_account) + req.amount > DAILY_TRANSFER_LIMIT:
            raise HTTPException(
                status_code=400,
                detail=f"Daily transfer limit exceeded: max {DAILY_TRANSFER_LIMIT}"
            )

        # Check sufficient funds
        if accounts[req.from_account] < req.amount:
            raise HTTPException(status_code=400, detail="Insufficient funds")

        # Execute transfer
        accounts[req.from_account] -= req.amount
        accounts[req.to_account] += req.amount

        tx_id = str(uuid4())
        timestamp = datetime.utcnow()

        ledger[req.from_account].append({
            "tx_id": tx_id,
            "type": "transfer_out",
            "amount": -req.amount,
            "balance_after": accounts[req.from_account],
            "timestamp": timestamp
        })

        ledger[req.to_account].append({
            "tx_id": tx_id,
            "type": "transfer_in",
            "amount": req.amount,
            "balance_after": accounts[req.to_account],
            "timestamp": timestamp
        })

    response = {"tx_id": tx_id, "status": "success"}

    # Store idempotency key
    if idempotency_key:
        store_idempotency(idempotency_key, response)

    return response

@app.get("/accounts/{account_id}/transactions")
def get_transactions(account_id: str, limit: int = 10, cursor: int = 0):
    """
    Get transaction history for an account (paginated).
    
    Query params:
    - limit: number of items per page (default 10)
    - cursor: offset for pagination (default 0)
    """
    ensure_account(account_id)
    entries = ledger[account_id][cursor: cursor + limit]
    total = len(ledger[account_id])
    
    return {
        "account_id": account_id,
        "items": entries,
        "total_transactions": total,
        "current_cursor": cursor,
        "next_cursor": cursor + limit if cursor + limit < total else None,
        "has_more": cursor + limit < total
    }

@app.get("/accounts/{account_id}/summary")
def account_summary(account_id: str):
    """Get account summary including balance and daily transfer info"""
    ensure_account(account_id)
    daily_total = get_daily_transfer_total(account_id)
    
    return {
        "account_id": account_id,
        "balance": accounts[account_id],
        "daily_transfer_total": daily_total,
        "daily_transfer_limit": DAILY_TRANSFER_LIMIT,
        "daily_transfer_remaining": DAILY_TRANSFER_LIMIT - daily_total,
        "transaction_count": len(ledger[account_id])
    }

@app.get("/health")
def health_check():
    """Health check endpoint"""
    return {"status": "ok"}
