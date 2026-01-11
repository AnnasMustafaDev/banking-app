import pytest
from fastapi.testclient import TestClient
from main import app, accounts, ledger, idempotency_store, rate_limits, account_locks
import time
import threading

client = TestClient(app)

# Fixtures
@pytest.fixture(autouse=True)
def reset_storage():
    """Reset in-memory storage before each test"""
    accounts.clear()
    ledger.clear()
    idempotency_store.clear()
    rate_limits.clear()
    account_locks.clear()
    yield


class TestHealthAndBasics:
    """Test health check and basic endpoints"""

    def test_health_check(self):
        """Test health check endpoint"""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_get_balance_new_account(self):
        """Test getting balance for a new account (should be 0)"""
        response = client.get("/balance/newaccount")
        assert response.status_code == 200
        data = response.json()
        assert data["account_id"] == "newaccount"
        assert data["balance"] == 0


class TestDeposits:
    """Test deposit functionality"""

    def test_deposit_basic(self):
        """Test basic deposit"""
        response = client.post("/deposit", json={
            "account_id": "user1",
            "amount": 1000
        })
        assert response.status_code == 200
        data = response.json()
        assert data["type"] == "deposit"
        assert data["amount"] == 1000
        assert data["balance_after"] == 1000

    def test_deposit_multiple(self):
        """Test multiple deposits accumulate"""
        client.post("/deposit", json={"account_id": "user1", "amount": 500})
        response = client.post("/deposit", json={"account_id": "user1", "amount": 300})
        
        assert response.json()["balance_after"] == 800
        
        # Check ledger
        balance_response = client.get("/balance/user1")
        assert balance_response.json()["balance"] == 800

    def test_deposit_invalid_amount(self):
        """Test deposit with invalid amount"""
        response = client.post("/deposit", json={
            "account_id": "user1",
            "amount": 0
        })
        assert response.status_code == 422  # Validation error

    def test_deposit_large_amount(self):
        """Test deposit of large amount"""
        response = client.post("/deposit", json={
            "account_id": "user1",
            "amount": 1_000_000
        })
        assert response.status_code == 200
        assert response.json()["balance_after"] == 1_000_000


class TestWithdrawals:
    """Test withdrawal functionality"""

    def test_withdraw_basic(self):
        """Test basic withdrawal"""
        # Deposit first
        client.post("/deposit", json={"account_id": "user1", "amount": 1000})
        
        # Withdraw
        response = client.post("/withdraw", json={
            "account_id": "user1",
            "amount": 300
        })
        assert response.status_code == 200
        data = response.json()
        assert data["type"] == "withdrawal"
        assert data["amount"] == -300
        assert data["balance_after"] == 700

    def test_withdraw_insufficient_funds(self):
        """Test withdrawal with insufficient funds"""
        client.post("/deposit", json={"account_id": "user1", "amount": 100})
        
        response = client.post("/withdraw", json={
            "account_id": "user1",
            "amount": 200
        })
        assert response.status_code == 400
        assert "Insufficient funds" in response.json()["detail"]

    def test_withdraw_from_empty_account(self):
        """Test withdrawal from account with zero balance"""
        response = client.post("/withdraw", json={
            "account_id": "newaccount",
            "amount": 100
        })
        assert response.status_code == 400
        assert "Insufficient funds" in response.json()["detail"]

    def test_withdraw_all_funds(self):
        """Test withdrawing all available funds"""
        client.post("/deposit", json={"account_id": "user1", "amount": 500})
        
        response = client.post("/withdraw", json={
            "account_id": "user1",
            "amount": 500
        })
        assert response.status_code == 200
        assert response.json()["balance_after"] == 0


class TestTransfers:
    """Test transfer functionality"""

    def test_transfer_basic(self):
        """Test basic successful transfer"""
        # Setup
        client.post("/deposit", json={"account_id": "user1", "amount": 1000})
        
        # Transfer
        response = client.post("/transfer", json={
            "from_account": "user1",
            "to_account": "user2",
            "amount": 300
        })
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "tx_id" in data

        # Verify balances
        user1_balance = client.get("/balance/user1").json()["balance"]
        user2_balance = client.get("/balance/user2").json()["balance"]
        
        assert user1_balance == 700
        assert user2_balance == 300

    def test_transfer_insufficient_funds(self):
        """Test transfer with insufficient funds"""
        client.post("/deposit", json={"account_id": "user1", "amount": 100})
        
        response = client.post("/transfer", json={
            "from_account": "user1",
            "to_account": "user2",
            "amount": 200
        })
        assert response.status_code == 400
        assert "Insufficient funds" in response.json()["detail"]

    def test_transfer_exceeds_per_transfer_limit(self):
        """Test transfer exceeding per-transfer limit (10,000)"""
        client.post("/deposit", json={"account_id": "user1", "amount": 100_000})
        
        response = client.post("/transfer", json={
            "from_account": "user1",
            "to_account": "user2",
            "amount": 15_000
        })
        assert response.status_code == 400
        assert "Per-transfer limit exceeded" in response.json()["detail"]

    def test_transfer_at_per_transfer_limit(self):
        """Test transfer at exactly the per-transfer limit (should succeed)"""
        client.post("/deposit", json={"account_id": "user1", "amount": 20_000})
        
        response = client.post("/transfer", json={
            "from_account": "user1",
            "to_account": "user2",
            "amount": 10_000
        })
        assert response.status_code == 200

    def test_transfer_exceeds_daily_limit(self):
        """Test transfer exceeding daily limit (25,000)"""
        client.post("/deposit", json={"account_id": "user1", "amount": 50_000})
        
        # First transfer: 10,000
        response1 = client.post("/transfer", json={
            "from_account": "user1",
            "to_account": "user2",
            "amount": 10_000
        })
        assert response1.status_code == 200
        
        # Second transfer: 10,000
        response2 = client.post("/transfer", json={
            "from_account": "user1",
            "to_account": "user3",
            "amount": 10_000
        })
        assert response2.status_code == 200
        
        # Third transfer: 6,000 (total = 26,000, exceeds limit)
        response3 = client.post("/transfer", json={
            "from_account": "user1",
            "to_account": "user4",
            "amount": 6_000
        })
        assert response3.status_code == 400
        assert "Daily transfer limit exceeded" in response3.json()["detail"]

    def test_transfer_at_daily_limit(self):
        """Test transfers that exactly hit daily limit"""
        client.post("/deposit", json={"account_id": "user1", "amount": 30_000})
        
        # Transfer exactly 25,000
        response = client.post("/transfer", json={
            "from_account": "user1",
            "to_account": "user2",
            "amount": 25_000
        })
        assert response.status_code == 200
        
        # Another transfer should fail (already at limit)
        response2 = client.post("/transfer", json={
            "from_account": "user1",
            "to_account": "user3",
            "amount": 1
        })
        assert response2.status_code == 400
        assert "Daily transfer limit exceeded" in response2.json()["detail"]

    def test_transfer_same_account(self):
        """Test transfer to same account (edge case)"""
        client.post("/deposit", json={"account_id": "user1", "amount": 1000})
        
        response = client.post("/transfer", json={
            "from_account": "user1",
            "to_account": "user1",
            "amount": 100
        })
        # This should succeed (balance stays same)
        assert response.status_code == 200


class TestIdempotency:
    """Test idempotency key functionality"""

    def test_idempotency_key_prevents_duplicate(self):
        """Test that idempotency key prevents duplicate transfers"""
        client.post("/deposit", json={"account_id": "user1", "amount": 1000})
        
        idempotency_key = "test-key-123"
        
        # First transfer
        response1 = client.post("/transfer", json={
            "from_account": "user1",
            "to_account": "user2",
            "amount": 100
        }, headers={"idempotency-key": idempotency_key})
        
        assert response1.status_code == 200
        tx_id_1 = response1.json()["tx_id"]
        
        # Second transfer with same key
        response2 = client.post("/transfer", json={
            "from_account": "user1",
            "to_account": "user2",
            "amount": 100
        }, headers={"idempotency-key": idempotency_key})
        
        assert response2.status_code == 200
        tx_id_2 = response2.json()["tx_id"]
        
        # Should be same transaction
        assert tx_id_1 == tx_id_2
        
        # Balance should only change by 100, not 200
        user1_balance = client.get("/balance/user1").json()["balance"]
        assert user1_balance == 900

    def test_different_idempotency_keys_create_different_transfers(self):
        """Test that different idempotency keys create different transfers"""
        client.post("/deposit", json={"account_id": "user1", "amount": 1000})
        
        # Transfer 1 with key 1
        response1 = client.post("/transfer", json={
            "from_account": "user1",
            "to_account": "user2",
            "amount": 100
        }, headers={"idempotency-key": "key1"})
        
        tx_id_1 = response1.json()["tx_id"]
        
        # Transfer 2 with key 2
        response2 = client.post("/transfer", json={
            "from_account": "user1",
            "to_account": "user2",
            "amount": 100
        }, headers={"idempotency-key": "key2"})
        
        tx_id_2 = response2.json()["tx_id"]
        
        # Should be different transactions
        assert tx_id_1 != tx_id_2
        
        # Balance should change by 200
        user1_balance = client.get("/balance/user1").json()["balance"]
        assert user1_balance == 800


class TestRateLimiting:
    """Test rate limiting functionality"""

    def test_rate_limit_10_per_minute(self):
        """Test rate limit of 10 transfers per minute"""
        client.post("/deposit", json={"account_id": "user1", "amount": 200_000})
        
        # Make 10 transfers (should all succeed)
        for i in range(10):
            response = client.post("/transfer", json={
                "from_account": "user1",
                "to_account": f"user{i+2}",
                "amount": 1000
            })
            assert response.status_code == 200, f"Transfer {i+1} failed"
        
        # 11th transfer should fail (rate limited)
        response = client.post("/transfer", json={
            "from_account": "user1",
            "to_account": "user99",
            "amount": 1000
        })
        assert response.status_code == 429
        assert "Rate limit exceeded" in response.json()["detail"]

    def test_rate_limit_per_account(self):
        """Test rate limit applies per account"""
        client.post("/deposit", json={"account_id": "user1", "amount": 200_000})
        client.post("/deposit", json={"account_id": "user2", "amount": 200_000})
        
        # User1: 10 transfers
        for i in range(10):
            response = client.post("/transfer", json={
                "from_account": "user1",
                "to_account": f"dest{i}",
                "amount": 1000
            })
            assert response.status_code == 200
        
        # User1: 11th should fail
        response = client.post("/transfer", json={
            "from_account": "user1",
            "to_account": "dest99",
            "amount": 1000
        })
        assert response.status_code == 429
        
        # User2: should still be able to transfer (separate rate limit)
        response = client.post("/transfer", json={
            "from_account": "user2",
            "to_account": "dest1",
            "amount": 1000
        })
        assert response.status_code == 200


class TestConcurrency:
    """Test concurrent transaction handling"""

    def test_concurrent_transfers_same_recipient(self):
        """Test two concurrent transfers to same recipient"""
        # Setup: user1 and user2 both have funds
        client.post("/deposit", json={"account_id": "user1", "amount": 5000})
        client.post("/deposit", json={"account_id": "user2", "amount": 5000})
        
        results = []

        def transfer_1():
            response = client.post("/transfer", json={
                "from_account": "user1",
                "to_account": "userX",
                "amount": 1000
            })
            results.append(("user1", response.status_code))

        def transfer_2():
            response = client.post("/transfer", json={
                "from_account": "user2",
                "to_account": "userX",
                "amount": 1000
            })
            results.append(("user2", response.status_code))

        # Run transfers concurrently
        t1 = threading.Thread(target=transfer_1)
        t2 = threading.Thread(target=transfer_2)
        
        t1.start()
        t2.start()
        
        t1.join()
        t2.join()

        # Both should succeed
        assert all(status == 200 for _, status in results)
        
        # Recipient should have 2000
        recipient_balance = client.get("/balance/userX").json()["balance"]
        assert recipient_balance == 2000

    def test_concurrent_transfers_same_sender(self):
        """Test concurrent transfers from same sender (should handle rate limit)"""
        client.post("/deposit", json={"account_id": "user1", "amount": 200_000})
        
        results = []
        lock = threading.Lock()

        def make_transfer(i):
            try:
                response = client.post("/transfer", json={
                    "from_account": "user1",
                    "to_account": f"user{i}",
                    "amount": 100
                })
                with lock:
                    results.append((i, response.status_code))
            except Exception as e:
                with lock:
                    results.append((i, str(e)))

        # Create 12 threads to test rate limiting
        threads = []
        for i in range(12):
            t = threading.Thread(target=make_transfer, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # Exactly 10 should succeed, 2 should be rate limited
        success_count = sum(1 for _, status in results if status == 200)
        rate_limited = sum(1 for _, status in results if status == 429)
        
        assert success_count == 10
        assert rate_limited == 2

    def test_concurrent_withdraw_and_transfer(self):
        """Test concurrent withdraw and transfer from same account"""
        client.post("/deposit", json={"account_id": "user1", "amount": 2000})
        
        results = []
        lock = threading.Lock()

        def withdraw():
            response = client.post("/withdraw", json={
                "account_id": "user1",
                "amount": 500
            })
            with lock:
                results.append(("withdraw", response.status_code))

        def transfer():
            response = client.post("/transfer", json={
                "from_account": "user1",
                "to_account": "user2",
                "amount": 500
            })
            with lock:
                results.append(("transfer", response.status_code))

        # Run concurrently
        t1 = threading.Thread(target=withdraw)
        t2 = threading.Thread(target=transfer)
        
        t1.start()
        t2.start()
        
        t1.join()
        t2.join()

        # Both should succeed (enough funds)
        assert all(status == 200 for _, status in results)
        
        # Total deducted should be 1000
        user1_balance = client.get("/balance/user1").json()["balance"]
        assert user1_balance == 1000


class TestTransactionHistory:
    """Test transaction history and pagination"""

    def test_transaction_history_basic(self):
        """Test retrieving transaction history"""
        client.post("/deposit", json={"account_id": "user1", "amount": 1000})
        client.post("/withdraw", json={"account_id": "user1", "amount": 200})
        client.post("/transfer", json={
            "from_account": "user1",
            "to_account": "user2",
            "amount": 100
        })
        
        response = client.get("/accounts/user1/transactions")
        assert response.status_code == 200
        data = response.json()
        
        assert data["total_transactions"] == 3
        assert len(data["items"]) == 3
        assert data["items"][0]["type"] == "deposit"
        assert data["items"][1]["type"] == "withdrawal"
        assert data["items"][2]["type"] == "transfer_out"

    def test_pagination(self):
        """Test pagination with limit and cursor"""
        # Create 15 transactions
        client.post("/deposit", json={"account_id": "user1", "amount": 10_000})
        for i in range(14):
            client.post("/transfer", json={
                "from_account": "user1",
                "to_account": f"user{i+2}",
                "amount": 100
            })
        
        # Get first page (limit=5)
        response1 = client.get("/accounts/user1/transactions?limit=5&cursor=0")
        data1 = response1.json()
        
        assert len(data1["items"]) == 5
        assert data1["has_more"] is True
        assert data1["next_cursor"] == 5
        
        # Get second page
        response2 = client.get("/accounts/user1/transactions?limit=5&cursor=5")
        data2 = response2.json()
        
        assert len(data2["items"]) == 5
        assert data2["has_more"] is True
        
        # Get third page
        response3 = client.get("/accounts/user1/transactions?limit=5&cursor=10")
        data3 = response3.json()
        
        assert len(data3["items"]) == 5
        assert data3["has_more"] is False
        assert data3["next_cursor"] is None

    def test_transaction_history_empty_account(self):
        """Test transaction history for account with no transactions"""
        response = client.get("/accounts/newuser/transactions")
        assert response.status_code == 200
        data = response.json()
        
        assert data["total_transactions"] == 0
        assert len(data["items"]) == 0
        assert data["has_more"] is False


class TestAccountSummary:
    """Test account summary endpoint"""

    def test_account_summary_new_account(self):
        """Test summary for new account"""
        response = client.get("/accounts/newuser/summary")
        assert response.status_code == 200
        data = response.json()
        
        assert data["balance"] == 0
        assert data["daily_transfer_total"] == 0
        assert data["daily_transfer_remaining"] == 25_000
        assert data["transaction_count"] == 0

    def test_account_summary_with_transactions(self):
        """Test summary with transactions"""
        client.post("/deposit", json={"account_id": "user1", "amount": 5000})
        client.post("/transfer", json={
            "from_account": "user1",
            "to_account": "user2",
            "amount": 3000
        })
        client.post("/transfer", json={
            "from_account": "user1",
            "to_account": "user3",
            "amount": 1000
        })
        
        response = client.get("/accounts/user1/summary")
        data = response.json()
        
        assert data["balance"] == 1000  # 5000 - 3000 - 1000
        assert data["daily_transfer_total"] == 4000
        assert data["daily_transfer_remaining"] == 21_000
        assert data["transaction_count"] == 3


class TestValidation:
    """Test input validation"""

    def test_invalid_amount_zero(self):
        """Test that zero amount is rejected"""
        response = client.post("/deposit", json={
            "account_id": "user1",
            "amount": 0
        })
        assert response.status_code == 422

    def test_invalid_amount_negative(self):
        """Test that negative amount is rejected"""
        response = client.post("/deposit", json={
            "account_id": "user1",
            "amount": -100
        })
        assert response.status_code == 422

    def test_missing_required_fields(self):
        """Test missing required fields"""
        response = client.post("/deposit", json={"amount": 100})
        assert response.status_code == 422


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
