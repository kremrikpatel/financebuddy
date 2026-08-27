"""Bank aggregation provider abstraction.

Providers: Plaid (US), GoCardless Bank Account Data (EU/UK), Basiq (AU).
Each implements: create_link_session → exchange/fulfillment → sync accounts+transactions.
All are optional at runtime — the registry reports availability by config keys.
"""
from __future__ import annotations

import abc
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.crypto import open_sealed, seal
from app.core.logging import get_logger
from app.models import Account, BankConnection
from app.services.txn_service import create_transaction

log = get_logger("providers")


@dataclass
class ProviderTxn:
    external_id: str
    date: date
    amount_minor: int
    merchant_raw: str
    description: str | None = None


@dataclass
class ProviderAccount:
    external_id: str
    name: str
    type: str
    subtype: str | None
    currency: str
    balance_minor: int
    transactions: list[ProviderTxn] = field(default_factory=list)


class AggregationError(Exception):
    pass


class BaseProvider(abc.ABC):
    key: str
    region: str

    @abc.abstractmethod
    def is_configured(self) -> bool: ...

    @abc.abstractmethod
    async def create_link(self, user_id: str, redirect_uri: str | None) -> dict:
        """Return {link_url?, link_token?, session_id?} for client-side link flow."""

    @abc.abstractmethod
    async def exchange(self, public_token_or_ref: str) -> str:
        """Persist connection; returns external connection id."""

    @abc.abstractmethod
    async def fetch_accounts(self, conn: BankConnection) -> list[ProviderAccount]: ...


# ── Plaid (US) ──────────────────────────────────────────────────────────

PLAID_HOSTS = {
    "sandbox": "https://sandbox.plaid.com",
    "development": "https://development.plaid.com",
    "production": "https://production.plaid.com",
}


class PlaidProvider(BaseProvider):
    key = "plaid"
    region = "US"

    def is_configured(self) -> bool:
        return bool(settings.plaid_client_id and settings.plaid_secret)

    @property
    def host(self) -> str:
        return PLAID_HOSTS.get(settings.plaid_env, PLAID_HOSTS["sandbox"])

    async def _post(self, path: str, body: dict) -> dict:
        body.update({"client_id": settings.plaid_client_id, "secret": settings.plaid_secret})
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(f"{self.host}{path}", json=body)
            if r.status_code >= 400:
                raise AggregationError(f"Plaid {path}: {r.text[:300]}")
            return r.json()

    async def create_link(self, user_id: str, redirect_uri: str | None) -> dict:
        data = await self._post("/link/token/create", {
            "user": {"client_user_id": user_id},
            "client_name": "FinanceBuddy",
            "products": ["transactions"],
            "country_codes": ["US", "CA"],
            "language": "en",
        })
        return {"link_token": data["link_token"], "expiration": data.get("expiration")}

    async def exchange(self, public_token: str) -> str:
        data = await self._post("/item/public_token/exchange", {"public_token": public_token})
        # access token sealed and attached to connection row by router
        self._last_access_token = data["access_token"]
        return data["item_id"]

    last_access_token: str | None = None

    async def fetch_accounts(self, conn: BankConnection) -> list[ProviderAccount]:
        token = open_sealed(conn.access_token_sealed) if conn.access_token_sealed else None
        if not token:
            raise AggregationError("Missing Plaid access token")
        accs = await self._post("/accounts/get", {"access_token": token})["accounts"]
        out: list[ProviderAccount] = []
        for a in accs:
            balances = a.get("balances", {})
            current = balances.get("current") or 0.0
            if a.get("type") in ("credit", "loan"):
                current = -abs(current)
            out.append(ProviderAccount(
                external_id=a["account_id"], name=a["name"], type=a["type"],
                subtype=a.get("subtype"), currency=(balances.get("iso_currency_code") or "USD"),
                balance_minor=round(current * 100),
            ))
        return out

    async def fetch_transactions(self, conn: BankConnection, days: int = 90) -> dict[str, list[ProviderTxn]]:
        from datetime import timedelta

        token = open_sealed(conn.access_token_sealed)
        end = datetime.utcnow().date()
        start = end - timedelta(days=min(days, 730))
        data = await self._post("/transactions/get", {
            "access_token": token,
            "start_date": start.isoformat(), "end_date": end.isoformat(),
            "options": {"count": 250},
        })
        by_account: dict[str, list[ProviderTxn]] = {}
        for t in data.get("transactions", []):
            # Plaid: positive amount = outflow → our convention: expense negative
            minor = -round(float(t["amount"]) * 100)
            by_account.setdefault(t["account_id"], []).append(ProviderTxn(
                external_id=t["transaction_id"],
                date=datetime.strptime(t["date"], "%Y-%m-%d").date(),
                amount_minor=minor,
                merchant_raw=t.get("merchant_name") or t.get("name") or "Unknown",
                description=t.get("original_description"),
            ))
        return by_account


# ── GoCardless Bank Account Data (EU/UK) ────────────────────────────────

GC_HOSTS = {"sandbox": "https://bankaccountdata.gocardless.com/api/v2"}


class GoCardlessProvider(BaseProvider):
    key = "gocardless"
    region = "EU"

    def is_configured(self) -> bool:
        return bool(settings.gocardless_secret_id and settings.gocardless_secret_key)

    @property
    def base(self) -> str:
        return GC_HOSTS["sandbox"] if settings.gocardless_env == "sandbox" else GC_HOSTS["sandbox"]

    _token_cache: tuple[str, float] | None = None

    async def _token(self) -> str:
        import time

        if self._token_cache and time.time() - self._token_cache[1] < 3000:
            return self._token_cache[0]
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(f"{self.base}/token/new/", json={
                "secret_id": settings.gocardless_secret_id,
                "secret_key": settings.gocardless_secret_key,
            })
            r.raise_for_status()
            tok = r.json()["access"]
            self._token_cache = (tok, time.time())
            return tok

    async def _req(self, method: str, path: str, body: dict | None = None) -> dict:
        headers = {"Authorization": f"Bearer {await self._token()}"}
        async with httpx.AsyncClient(timeout=25) as client:
            r = await client.request(method, f"{self.base}{path}", json=body or {}, headers=headers)
            if r.status_code >= 400:
                raise AggregationError(f"GoCardless {path}: {r.text[:300]}")
            return r.json()

    async def create_link(self, user_id: str, redirect_uri: str | None) -> dict:
        institutions = await self._req("GET", "/institutions/?country=de")
        data = await self._req("POST", "/requisitions/", {
            "redirect": redirect_uri or "https://localhost/callback",
            "institution_id": institutions[0]["id"],
            "user_language": "en",
        })
        return {"requisition_id": data["id"], "link_url": data["link"]}

    async def exchange(self, requisition_id: str) -> str:
        return requisition_id  # requisition id IS the persistent ref

    async def fetch_accounts(self, conn: BankConnection) -> list[ProviderAccount]:
        detail = await self._req("GET", f"/requisitions/{conn.external_id}/")
        out: list[ProviderAccount] = []
        for acct_id in detail.get("accounts", []):
            meta = await self._req("GET", f"/accounts/{acct_id}/")
            balances = await self._req("GET", f"/accounts/{acct_id}/balances/")
            bal = 0.0
            cur = meta.get("currency", "EUR")
            if balances.get("balances"):
                b0 = balances["balances"][0]["balanceAmount"]
                bal, cur = float(b0["amount"]), b0["currency"]
            out.append(ProviderAccount(
                external_id=acct_id, name=meta.get("productName") or meta.get("ownerName") or "Account",
                type="depository", subtype=meta.get("account_type"), currency=cur,
                balance_minor=round(bal * 100)))
        return out

    async def fetch_transactions(self, conn: BankConnection) -> dict[str, list[ProviderTxn]]:
        detail = await self._req("GET", f"/requisitions/{conn.external_id}/")
        by_account: dict[str, list[ProviderTxn]] = {}
        for acct_id in detail.get("accounts", []):
            data = await self._req("GET", f"/accounts/{acct_id}/transactions/")
            rows = data.get("transactions", {}).get("booked", [])
            for t in rows:
                amt = float(t.get("transactionAmount", {}).get("amount", "0"))
                name = t.get("merchantName") or t.get("creditorName") or t.get("debtorName") \
                    or t.get("remittanceInformationUnstructured") or "Unknown"
                by_account.setdefault(acct_id, []).append(ProviderTxn(
                    external_id=t.get("transactionId", ""),
                    date=datetime.strptime(t["bookingDate"], "%Y-%m-%d").date(),
                    amount_minor=round(amt * 100), merchant_raw=name.strip()))
        return by_account


# ── Basiq (AU) ──────────────────────────────────────────────────────────

BASIQ_AUTH = "https://auth.basiq.io/token"
BASIQ_API = "https://api.basiq.io/v3"


class BasiqProvider(BaseProvider):
    key = "basiq"
    region = "AU"

    def is_configured(self) -> bool:
        return bool(settings.basiq_api_key)

    _token_cache: tuple[str, float] | None = None

    async def _token(self) -> str:
        import time

        if self._token_cache and time.time() - self._token_cache[1] < 1800:
            return self._token_cache[0]
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(BASIQ_AUTH, headers={
                "Authorization": f"Basic {settings.basiq_api_key}",
                "basiq-version": "3.0",
            }, data={"scope": "SERVER_ACCESS"})
            r.raise_for_status()
            tok = r.json()["access_token"]
            self._token_cache = (tok, time.time())
            return tok

    async def _req(self, method: str, path: str, body: dict | None = None) -> dict:
        headers = {"Authorization": f"Bearer {await self._token()}", "basiq-version": "3.0"}
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.request(method, f"{BASIQ_API}{path}", json=body or {}, headers=headers)
            if r.status_code >= 400:
                raise AggregationError(f"Basiq {path}: {r.text[:300]}")
            return r.json()

    async def create_link(self, user_id: str, redirect_uri: str | None) -> dict:
        data = await self._req("POST", "/users", {"mobile_number": f"+61400000000"})
        auth = await self._req("POST", "/auth_link", {"user_id": data["id"], "mobile": "+61400000000"})
        return {"basiq_user_id": data["id"], "link_url": auth["links"]["public"]["href"]}

    async def exchange(self, basiq_user_id: str) -> str:
        return basiq_user_id

    async def fetch_accounts(self, conn: BankConnection) -> list[ProviderAccount]:
        data = await self._req("GET", f"/users/{conn.external_id}/accounts")
        out: list[ProviderAccount] = []
        for a in data.get("data", []):
            bal = a.get("balance", "0")
            out.append(ProviderAccount(
                external_id=a["id"], name=a.get("nickname") or a.get("accountNo") or "Account",
                type="credit" if a.get("class") == "CREDIT_CARD" else "depository",
                subtype=a.get("type"), currency="AUD", balance_minor=round(float(bal) * 100)))
        return out

    async def fetch_transactions(self, conn: BankConnection) -> dict[str, list[ProviderTxn]]:
        data = await self._req("GET", f"/users/{conn.external_id}/transactions?limit=500")
        by_account: dict[str, list[ProviderTxn]] = {}
        for t in data.get("data", []):
            amt = float(t.get("amount", "0"))
            direction = t.get("direction", "expense")
            minor = round(abs(amt) * 100)
            if direction != "income":
                minor = -minor
            by_account.setdefault(t.get("accountId", ""), []).append(ProviderTxn(
                external_id=t.get("id", ""),
                date=datetime.strptime(t["postDate"][:10], "%Y-%m-%d").date(),
                amount_minor=minor,
                merchant_raw=(t.get("description") or {}).get("summary") or "Unknown"))
        return by_account


# ── Mock / Sandbox Provider (Universal Fallback) ─────────────────────────

class MockBankProvider(BaseProvider):
    key = "mock"
    region = "GLOBAL"

    def __init__(self, key: str = "mock"):
        self.key = key

    def is_configured(self) -> bool:
        return True

    async def create_link(self, user_id: str, redirect_uri: str | None) -> dict:
        token = f"mock-link-{uuid.uuid4().hex[:12]}"
        return {
            "link_token": token,
            "link_url": f"https://financebuddy.mock/link/{token}",
            "expiration": "2099-12-31T23:59:59Z",
        }

    async def exchange(self, public_token_or_ref: str) -> str:
        return f"mock_item_{public_token_or_ref[:16]}"

    async def fetch_accounts(self, conn: BankConnection) -> list[ProviderAccount]:
        return [
            ProviderAccount(
                external_id=f"{conn.external_id}_chk",
                name="Everyday Checking",
                type="depository",
                subtype="checking",
                currency="USD",
                balance_minor=354020,
            ),
            ProviderAccount(
                external_id=f"{conn.external_id}_sav",
                name="High-Yield Savings",
                type="depository",
                subtype="savings",
                currency="USD",
                balance_minor=1285000,
            ),
            ProviderAccount(
                external_id=f"{conn.external_id}_crd",
                name="Platinum Rewards Card",
                type="credit",
                subtype="credit card",
                currency="USD",
                balance_minor=-42580,
            ),
        ]

    async def fetch_transactions(self, conn: BankConnection, days: int = 90) -> dict[str, list[ProviderTxn]]:
        from datetime import timedelta
        today = date.today()
        chk_id = f"{conn.external_id}_chk"
        crd_id = f"{conn.external_id}_crd"

        return {
            chk_id: [
                ProviderTxn(external_id=f"{chk_id}_t1", date=today - timedelta(days=2), amount_minor=-11540, merchant_raw="Whole Foods Market", description="Groceries"),
                ProviderTxn(external_id=f"{chk_id}_t2", date=today - timedelta(days=15), amount_minor=325000, merchant_raw="Acme Corp Payroll", description="Direct Deposit Salary"),
                ProviderTxn(external_id=f"{chk_id}_t3", date=today - timedelta(days=5), amount_minor=-8500, merchant_raw="Shell Gas Station", description="Fuel"),
            ],
            crd_id: [
                ProviderTxn(external_id=f"{crd_id}_t1", date=today - timedelta(days=1), amount_minor=-1499, merchant_raw="Netflix.com", description="Streaming subscription"),
                ProviderTxn(external_id=f"{crd_id}_t2", date=today - timedelta(days=3), amount_minor=-4250, merchant_raw="Uber Eats", description="Dinner delivery"),
                ProviderTxn(external_id=f"{crd_id}_t3", date=today - timedelta(days=6), amount_minor=-1890, merchant_raw="Starbucks", description="Coffee"),
            ],
        }


REGISTRY: dict[str, BaseProvider] = {}


def get_providers() -> dict[str, BaseProvider]:
    global REGISTRY
    if not REGISTRY:
        for p in (PlaidProvider(), GoCardlessProvider(), BasiqProvider(), MockBankProvider("mock"), MockBankProvider("sandbox")):
            REGISTRY[p.key] = p
    return REGISTRY


def available_providers() -> list[dict]:
    return [
        {"key": p.key, "region": p.region, "configured": p.is_configured()}
        for p in get_providers().values()
    ]


async def sync_connection(db: AsyncSession, user_id: uuid.UUID, conn: BankConnection,
                          provider: BaseProvider) -> dict:
    """Full sync: upsert accounts + ingest new transactions."""
    from app.services.importers import ImportReport

    provider_accounts = await provider.fetch_accounts(conn)
    report = ImportReport()
    try:
        txns_by_acct = await provider.fetch_transactions(conn)
    except (NotImplementedError, AttributeError):
        txns_by_acct = {}

    existing = {
        a.external_id: a for a in (await db.execute(
            select(Account).where(
                Account.user_id == user_id, Account.connection_id == conn.id))).scalars().all()
    }
    created_accounts = []
    for pa in provider_accounts:
        acct = existing.get(pa.external_id)
        if not acct:
            acct = Account(user_id=user_id, connection_id=conn.id, name=pa.name,
                           type=pa.type, subtype=pa.subtype, currency=pa.currency.upper(),
                           balance_minor=pa.balance_minor, external_id=pa.external_id)
            db.add(acct)
            await db.flush()
            created_accounts.append(acct.name)
        else:
            acct.balance_minor = pa.balance_minor
        for t in txns_by_acct.get(pa.external_id, []):
            from app.services.txn_service import create_transaction as ct

            _, was_created = await ct(db, account=acct, date=t.date,
                                      amount_minor=t.amount_minor, currency=acct.currency,
                                      merchant_raw=t.merchant_raw, description=t.description,
                                      source="sync", external_id=t.external_id or None)
            if was_created:
                report.created += 1
            else:
                report.duplicates += 1
    return {"created_txns": report.created, "duplicates": report.duplicates,
            "created_accounts": created_accounts, "errors": report.errors}
