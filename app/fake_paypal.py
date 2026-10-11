"""Offline stand-in for paypal_client with the same function names. For tests and dry runs - no keys needed."""
import uuid


class FakePayPal:
    def __init__(self):
        self.invoices = {}
        self.payouts = {}

    def create_and_send_invoice(self, client, amount, due_date, currency="USD"):
        invoice_id = f"FAKE-INV-{len(self.invoices) + 1:03d}"
        self.invoices[invoice_id] = {"client": client, "amount": amount, "due_date": due_date,
                                     "currency": currency, "status": "unpaid"}
        return invoice_id

    def get_invoice_status(self, invoice_id):
        return self.invoices[invoice_id]["status"]

    def mark_paid(self, invoice_id):          # simulates the client paying
        self.invoices[invoice_id]["status"] = "paid"

    def send_payout(self, email, amount, currency="USD", request_id=None, note=""):
        request_id = request_id or str(uuid.uuid4())
        if request_id in self.payouts:        # same request id -> paid only once, like PayPal
            return self.payouts[request_id]["batch_id"]
        batch_id = f"FAKE-BATCH-{len(self.payouts) + 1:03d}"
        self.payouts[request_id] = {"batch_id": batch_id, "email": email, "amount": amount}
        return batch_id

    def get_payout_status(self, batch_id):
        return "success"