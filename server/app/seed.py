"""Seed: system categories, demo user, multi-currency accounts, transactions,
budgets, envelopes, goals, debts, subscriptions, alerts, and RAG corpus.
"""
from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, UTC
import random

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.db.session import SessionFactory, engine
from app.models import (
    Account,
    Alert,
    Budget,
    BudgetEnvelope,
    Category,
    Debt,
    FxRate,
    Goal,
    KnowledgeDoc,
    RecurringSubscription,
    Transaction,
    User,
)
from app.services.txn_service import create_transaction

SYSTEM_CATEGORIES = [
    ("Groceries", "expense", "#22c55e", "shopping-cart"),
    ("Dining Out", "expense", "#f97316", "utensils"),
    ("Subscriptions", "expense", "#a855f7", "repeat"),
    ("Transport & Fuel", "expense", "#0ea5e9", "fuel"),
    ("Public Transport", "expense", "#06b6d4", "train"),
    ("Housing", "expense", "#ef4444", "home"),
    ("Utilities & Telecom", "expense", "#eab308", "zap"),
    ("Shopping", "expense", "#ec4899", "shopping-bag"),
    ("Health & Pharmacy", "expense", "#14b8a6", "pill"),
    ("Health & Fitness", "expense", "#84cc16", "activity"),
    ("Insurance", "expense", "#f43f5e", "shield"),
    ("Cash & ATM", "expense", "#94a3b8", "dollar-sign"),
    ("Entertainment", "expense", "#8b5cf6", "film"),
    ("Travel", "expense", "#3b82f6", "plane"),
    ("Education", "expense", "#6366f1", "book"),
    ("Uncategorized", "expense", "#9ca3af", "help-circle"),
    ("Salary", "income", "#10b981", "briefcase"),
    ("Investment Income", "income", "#059669", "trending-up"),
    ("Refunds", "income", "#34d399", "rotate-ccw"),
    ("Transfers", "transfer", "#64748b", "arrow-left-right"),
]

INITIAL_FX_RATES = [
    ("USD", "AUD", 1.54),
    ("AUD", "USD", 0.65),
    ("USD", "EUR", 0.92),
    ("EUR", "USD", 1.09),
    ("USD", "GBP", 0.79),
    ("GBP", "USD", 1.27),
    ("USD", "JPY", 155.2),
    ("JPY", "USD", 0.00644),
    ("AUD", "EUR", 0.60),
    ("EUR", "AUD", 1.67),
    ("AUD", "GBP", 0.51),
    ("GBP", "AUD", 1.95),
    ("AUD", "JPY", 100.8),
    ("JPY", "AUD", 0.00992),
]

BASE_TXN_TEMPLATES = [
    # (merchant_raw, description, amount, category, day_offset, recurring, currency, acc_type)
    ("WOOLWORTHS 1234 SYDNEY", "Weekly groceries and household items", -8450, "Groceries", 2, True, "AUD", "checking"),
    ("WOOLWORTHS 5678 NEWTOWN", "Mid-week top-up groceries", -3420, "Groceries", 9, False, "AUD", "checking"),
    ("COLES SUPERMARKETS SYDNEY", "Fresh produce & meat", -11240, "Groceries", 16, False, "AUD", "checking"),
    ("HARRIS FARM MARKETS", "Organic fruits and vegetables", -6890, "Groceries", 23, False, "AUD", "card"),
    ("NETFLIX.COM", "Monthly subscription HD", -1699, "Subscriptions", 5, True, "AUD", "card"),
    ("SPOTIFY AUSTRALIA", "Premium Individual music", -1399, "Subscriptions", 7, True, "AUD", "card"),
    ("STARBUCKS COFFEE SYDNEY CBD", "Flat white & croissant", -850, "Dining Out", 1, False, "AUD", "card"),
    ("UBER EATS", "Thai dinner delivery", -3850, "Dining Out", 3, False, "AUD", "card"),
    ("DIN TAI FUNG SYDNEY", "Dinner with friends", -7800, "Dining Out", 10, False, "AUD", "card"),
    ("GUZMAN Y GOMEZ", "Burrito bowl lunch", -1850, "Dining Out", 17, False, "AUD", "card"),
    ("SHELL OIL 8842", "Unleaded 98 petrol", -7200, "Transport & Fuel", 4, False, "AUD", "checking"),
    ("BP CONNECT EXPRESS", "Fuel & windshield fluid", -6450, "Transport & Fuel", 18, False, "AUD", "checking"),
    ("OPAL TRAVEL SYDNEY", "Metro card auto-topup", -2000, "Public Transport", 6, True, "AUD", "checking"),
    ("OPAL TRAVEL SYDNEY", "Train commute", -2000, "Public Transport", 20, True, "AUD", "checking"),
    ("MONTHLY RENT PAYMENT", "Apartment lease payment", -260000, "Housing", 1, True, "AUD", "checking"),
    ("AGL ELECTRICITY", "Quarterly energy bill", -18450, "Utilities & Telecom", 12, False, "AUD", "checking"),
    ("TELSTRA NBN", "Monthly broadband internet", -8900, "Utilities & Telecom", 8, True, "AUD", "checking"),
    ("SYDNEY WATER", "Residential water service", -5400, "Utilities & Telecom", 25, False, "AUD", "checking"),
    ("AMAZON.COM.AU", "Ergonomic keyboard and desk mat", -12999, "Shopping", 11, False, "AUD", "card"),
    ("JB HI-FI SYDNEY", "Noise cancelling headphones", -34900, "Shopping", 22, False, "AUD", "card"),
    ("UNIQLO AUSTRALIA", "Winter fleece and thermals", -8990, "Shopping", 14, False, "AUD", "card"),
    ("CHEMIST WAREHOUSE", "Vitamins and first aid", -3200, "Health & Pharmacy", 13, False, "AUD", "card"),
    ("ANYTIME FITNESS", "Monthly gym membership", -6500, "Health & Fitness", 8, True, "AUD", "checking"),
    ("BUPA HEALTH INSURANCE", "Comprehensive health cover", -16500, "Insurance", 15, True, "AUD", "checking"),
    ("ATM WITHDRAWAL WESTPAC", "Weekend cash withdrawal", -20000, "Cash & ATM", 19, False, "AUD", "checking"),
    ("EVENT CINEMAS GEORGE ST", "IMAX Movie tickets & popcorn", -5400, "Entertainment", 15, False, "AUD", "card"),
    ("TICKETEK AUSTRALIA", "Concert tickets", -18500, "Entertainment", 27, False, "AUD", "card"),
    ("QANTAS AIRWAYS", "Flight SYD to MEL return", -34500, "Travel", 24, False, "AUD", "card"),
    ("UDEMY ONLINE COURSE", "Fullstack development bootcamp", -2499, "Education", 21, False, "AUD", "card"),
    ("PAYROLL ACME PTY LTD", "Fortnightly salary direct deposit", 482000, "Salary", 1, True, "AUD", "checking"),
    ("PAYROLL ACME PTY LTD", "Fortnightly salary direct deposit", 482000, "Salary", 15, True, "AUD", "checking"),
    ("INTEREST PAID SAVINGS", "Monthly high-yield interest", 3850, "Investment Income", 28, True, "AUD", "savings"),
    ("REFUND AMAZON ORDER", "Returned item", 4200, "Refunds", 8, False, "AUD", "card"),
    # Multi-currency accounts transactions
    ("APPLE INC DIVIDEND", "Quarterly dividend payment", 8500, "Investment Income", 12, True, "USD", "invest_usd"),
    ("VANGUARD S&P 500 ETF", "Monthly ETF distribution", 18500, "Investment Income", 24, True, "USD", "invest_usd"),
    ("BOULANGERIE DU COIN PARIS", "Pastries and espresso", -1250, "Dining Out", 5, False, "EUR", "travel_eur"),
    ("SNCF VOYAGES PARIS", "TGV train ticket to Lyon", -8500, "Public Transport", 12, False, "EUR", "travel_eur"),
    ("GELATERIA ROMA", "Artisan gelato", -600, "Dining Out", 18, False, "EUR", "travel_eur"),
    ("TFL UNDERGROUND LONDON", "Tube contactless fare", -720, "Public Transport", 9, False, "GBP", "current_gbp"),
    ("PRET A MANGER LONDON", "Sandwich and organic coffee", -1150, "Dining Out", 14, False, "GBP", "current_gbp"),
    ("FAMILYMART SHINJUKU TOKYO", "Bento box & green tea", -1450, "Dining Out", 4, False, "JPY", "cash_jpy"),
    ("SEVEN ELEVEN TOKYO", "Snacks and bottled water", -850, "Dining Out", 16, False, "JPY", "cash_jpy"),
]

KNOWLEDGE = [
    ("Emergency fund basics",
     "An emergency fund is cash reserved for genuine emergencies like job loss, unexpected medical bills, "
     "or major car repairs.\n\n"
     "A standard benchmark is 3 to 6 months of essential living expenses (rent, utilities, groceries, "
     "debt minimums). Start with a small milestone such as $1,000 or one week of expenses, then build "
     "month over month through automated transfers. Keep the fund liquid and in a high-yield savings "
     "account separate from daily spending so it is not accidentally spent."),
    ("Zero-based budgeting explained",
     "Zero-based budgeting assigns every single dollar of income a designated purpose until total income "
     "minus allocations equals zero.\n\n"
     "Categories span essential bills, discretionary lifestyle spending, sinking funds, and savings/debt goals. "
     "When unexpected expenses arise or income fluctuates mid-month, adjust other envelope allocations "
     "proactively. Envelopes that consistently underspend can be swept into investments or high-priority goals."),
    ("Debt payoff strategies: snowball vs avalanche",
     "The debt avalanche method pays statutory minimum payments on all debts and directs every extra available "
     "dollar to the debt with the highest annual percentage rate (APR). Mathematically, this minimizes the "
     "total interest accrued and results in the fastest debt-free date.\n\n"
     "The debt snowball method orders debts from smallest balance to largest balance regardless of interest rate. "
     "Paying off smaller balances first delivers rapid psychological wins that boost motivation and adherence. "
     "Choose the strategy that aligns with your behavioral profile."),
    ("Understanding credit utilization and credit scores",
     "Credit utilization ratio is the percentage of your revolving credit limit currently in use across all "
     "credit accounts. Keeping utilization below 30% — and ideally under 10% — is strongly associated with "
     "top-tier credit scores.\n\n"
     "Making multiple mid-cycle payments before statement closing dates lowers reported utilization balances "
     "even if you pay your statement balance in full every month."),
    ("Index fund investing and compounding returns",
     "Broad-market index funds (such as S&P 500 or MSCI World index tracking ETFs) provide low-cost, instant "
     "diversification across hundreds of established companies.\n\n"
     "Dollar-cost averaging into diversified index funds over 10-30 year horizons harnesses compound growth "
     "while eliminating the risks of individual stock picking and market timing fees."),
]


async def _seed_with_session(db: AsyncSession) -> None:
    # 1. System Categories
    cats: dict[str, Category] = {}
    for item in SYSTEM_CATEGORIES:
        name, kind, color = item[0], item[1], item[2]
        icon = item[3] if len(item) > 3 else "wallet"
        cat = await db.scalar(
            select(Category).where(Category.name == name, Category.user_id.is_(None))
        )
        if not cat:
            cat = Category(user_id=None, name=name, kind=kind, color=color, icon=icon)
            db.add(cat)
            await db.flush()
        cats[name] = cat
    await db.commit()

    # 2. FX Rates
    for base, quote, rate in INITIAL_FX_RATES:
        existing_fx = await db.scalar(
            select(FxRate).where(FxRate.base == base, FxRate.quote == quote)
        )
        if not existing_fx:
            db.add(FxRate(base=base, quote=quote, rate=rate))
    await db.commit()

    # 3. Demo User
    demo = await db.scalar(select(User).where(User.email == "demo@financebuddy.app"))
    if not demo:
        demo = User(
            email="demo@financebuddy.app",
            password_hash=hash_password("DemoPass123!"),
            full_name="Demo User",
            locale="en",
            base_currency="AUD",
            is_active=True,
        )
        db.add(demo)
        await db.flush()
        await db.commit()

    # 4. Multi-Currency Accounts
    existing_accounts = (
        await db.execute(select(Account).where(Account.user_id == demo.id))
    ).scalars().all()
    
    acc_map: dict[str, Account] = {a.name: a for a in existing_accounts}

    if "Everyday Checking" not in acc_map:
        checking_aud = Account(
            user_id=demo.id, name="Everyday Checking", type="depository",
            subtype="checking", currency="AUD", balance_minor=350000, is_manual=True
        )
        db.add(checking_aud)
        acc_map["Everyday Checking"] = checking_aud

    if "High-Interest Savings" not in acc_map:
        savings_aud = Account(
            user_id=demo.id, name="High-Interest Savings", type="depository",
            subtype="savings", currency="AUD", balance_minor=1200000, is_manual=True
        )
        db.add(savings_aud)
        acc_map["High-Interest Savings"] = savings_aud

    if "Rewards Credit Card" not in acc_map:
        card_aud = Account(
            user_id=demo.id, name="Rewards Credit Card", type="credit",
            subtype="credit_card", currency="AUD", balance_minor=-145000, is_manual=True
        )
        db.add(card_aud)
        acc_map["Rewards Credit Card"] = card_aud

    if "Global Tech Portfolio" not in acc_map:
        invest_usd = Account(
            user_id=demo.id, name="Global Tech Portfolio", type="investment",
            subtype="brokerage", currency="USD", balance_minor=2500000, is_manual=True
        )
        db.add(invest_usd)
        acc_map["Global Tech Portfolio"] = invest_usd

    if "European Travel Vault" not in acc_map:
        travel_eur = Account(
            user_id=demo.id, name="European Travel Vault", type="depository",
            subtype="savings", currency="EUR", balance_minor=420000, is_manual=True
        )
        db.add(travel_eur)
        acc_map["European Travel Vault"] = travel_eur

    if "UK Barclays Current" not in acc_map:
        current_gbp = Account(
            user_id=demo.id, name="UK Barclays Current", type="depository",
            subtype="checking", currency="GBP", balance_minor=185000, is_manual=True
        )
        db.add(current_gbp)
        acc_map["UK Barclays Current"] = current_gbp

    if "Japan Yen Cash" not in acc_map:
        cash_jpy = Account(
            user_id=demo.id, name="Japan Yen Cash", type="depository",
            subtype="cash", currency="JPY", balance_minor=150000, is_manual=True
        )
        db.add(cash_jpy)
        acc_map["Japan Yen Cash"] = cash_jpy

    await db.flush()
    await db.commit()

    # Re-fetch accounts with IDs
    all_accounts = (
        await db.execute(select(Account).where(Account.user_id == demo.id))
    ).scalars().all()
    acc_by_name = {a.name: a for a in all_accounts}

    # 5. Realistic Historical Transactions (100+ transactions over 4 months)
    existing_txns_count = len(
        (await db.execute(select(Transaction.id).where(Transaction.user_id == demo.id))).all()
    )

    today = date.today()
    if existing_txns_count < 100:
        for months_back in range(4):
            for template in BASE_TXN_TEMPLATES:
                merchant, desc, amount, cat_name, offset, _rec, curr, acc_key = template
                txn_date = today - timedelta(days=offset + (months_back * 30) + random.randint(-1, 1))
                
                if acc_key == "checking":
                    target_acc = acc_by_name.get("Everyday Checking")
                elif acc_key == "savings":
                    target_acc = acc_by_name.get("High-Interest Savings")
                elif acc_key == "card":
                    target_acc = acc_by_name.get("Rewards Credit Card")
                elif acc_key == "invest_usd":
                    target_acc = acc_by_name.get("Global Tech Portfolio")
                elif acc_key == "travel_eur":
                    target_acc = acc_by_name.get("European Travel Vault")
                elif acc_key == "current_gbp":
                    target_acc = acc_by_name.get("UK Barclays Current")
                elif acc_key == "cash_jpy":
                    target_acc = acc_by_name.get("Japan Yen Cash")
                else:
                    target_acc = acc_by_name.get("Everyday Checking")

                if not target_acc:
                    continue

                cat_obj = cats.get(cat_name)
                cat_id = cat_obj.id if cat_obj else None

                try:
                    await create_transaction(
                        db,
                        account=target_acc,
                        date=txn_date,
                        amount_minor=amount,
                        currency=curr,
                        merchant_raw=merchant,
                        description=desc,
                        category_id=cat_id,
                        source="seed",
                        skip_events=True,
                    )
                except Exception:
                    continue
        await db.commit()

    # 6. Budgets & Budget Envelopes
    existing_budget = await db.scalar(
        select(Budget).where(Budget.user_id == demo.id, Budget.active.is_(True))
    )
    if not existing_budget:
        start_of_month = date(today.year, today.month, 1)
        budget = Budget(
            user_id=demo.id,
            name="Monthly Living Budget",
            strategy="envelope",
            period="monthly",
            start_date=start_of_month,
            income_planned_minor=964000,  # $9,640.00
            currency="AUD",
            active=True,
        )
        db.add(budget)
        await db.flush()

        envelope_allocations = [
            ("Groceries", 90000),         # $900.00
            ("Dining Out", 45000),        # $450.00
            ("Transport & Fuel", 35000),  # $350.00
            ("Utilities & Telecom", 30000),# $300.00
            ("Entertainment", 20000),     # $200.00
            ("Housing", 260000),          # $2,600.00
            ("Subscriptions", 12000),     # $120.00
            ("Health & Fitness", 15000),  # $150.00
        ]

        for cat_name, alloc_minor in envelope_allocations:
            cat_obj = cats.get(cat_name)
            envelope = BudgetEnvelope(
                budget_id=budget.id,
                category_id=cat_obj.id if cat_obj else None,
                name=cat_name,
                allocated_minor=alloc_minor,
                rollover=False,
                carry_in_minor=0,
            )
            db.add(envelope)
        await db.commit()

    # 7. Goals
    existing_goals = (
        await db.execute(select(Goal).where(Goal.user_id == demo.id))
    ).scalars().all()
    if not existing_goals:
        savings_acc = acc_by_name.get("High-Interest Savings")
        travel_acc = acc_by_name.get("European Travel Vault")

        g1 = Goal(
            user_id=demo.id,
            name="Emergency Fund",
            target_minor=2000000,       # $20,000.00 AUD
            saved_minor=1200000,        # $12,000.00 AUD
            currency="AUD",
            target_date=today + timedelta(days=240),
            strategy="fixed_monthly",
            monthly_amount_minor=100000, # $1,000.00 / mo
            percent_of_income=0.0,
            account_id=savings_acc.id if savings_acc else None,
        )
        g2 = Goal(
            user_id=demo.id,
            name="Japan & Europe Vacation",
            target_minor=600000,        # $6,000.00 AUD
            saved_minor=350000,         # $3,500.00 AUD
            currency="AUD",
            target_date=today + timedelta(days=180),
            strategy="fixed_monthly",
            monthly_amount_minor=50000,  # $500.00 / mo
            percent_of_income=0.0,
            account_id=travel_acc.id if travel_acc else None,
        )
        g3 = Goal(
            user_id=demo.id,
            name="House Deposit",
            target_minor=10000000,      # $100,000.00 AUD
            saved_minor=4500000,        # $45,000.00 AUD
            currency="AUD",
            target_date=today + timedelta(days=730),
            strategy="percent_income",
            monthly_amount_minor=0,
            percent_of_income=20.0,
        )
        db.add_all([g1, g2, g3])
        await db.commit()

    # 8. Debts
    existing_debts = (
        await db.execute(select(Debt).where(Debt.user_id == demo.id))
    ).scalars().all()
    if not existing_debts:
        d1 = Debt(
            user_id=demo.id,
            name="Rewards Credit Card",
            principal_minor=145000,     # $1,450.00 AUD
            apr_bps=1999,               # 19.99% APR
            min_payment_minor=15000,    # $150.00 / mo
            due_day=15,
            currency="AUD",
        )
        d2 = Debt(
            user_id=demo.id,
            name="Auto Loan - Toyota RAV4",
            principal_minor=1850000,    # $18,500.00 AUD
            apr_bps=650,                # 6.50% APR
            min_payment_minor=42000,    # $420.00 / mo
            due_day=1,
            currency="AUD",
        )
        db.add_all([d1, d2])
        await db.commit()

    # 9. Recurring Subscriptions
    existing_subs = (
        await db.execute(select(RecurringSubscription).where(RecurringSubscription.user_id == demo.id))
    ).scalars().all()
    if not existing_subs:
        s1 = RecurringSubscription(
            user_id=demo.id,
            merchant_norm="netflix",
            display_name="Netflix Standard HD",
            avg_amount_minor=1699,
            currency="AUD",
            cadence_days=30,
            first_seen=today - timedelta(days=120),
            last_seen=today - timedelta(days=5),
            next_expected=today + timedelta(days=25),
            status="active",
            occurrence_count=4,
        )
        s2 = RecurringSubscription(
            user_id=demo.id,
            merchant_norm="spotify",
            display_name="Spotify Premium Individual",
            avg_amount_minor=1399,
            currency="AUD",
            cadence_days=30,
            first_seen=today - timedelta(days=120),
            last_seen=today - timedelta(days=7),
            next_expected=today + timedelta(days=23),
            status="active",
            occurrence_count=4,
        )
        s3 = RecurringSubscription(
            user_id=demo.id,
            merchant_norm="anytime fitness",
            display_name="Anytime Fitness Gym",
            avg_amount_minor=6500,
            currency="AUD",
            cadence_days=30,
            first_seen=today - timedelta(days=120),
            last_seen=today - timedelta(days=8),
            next_expected=today + timedelta(days=22),
            status="active",
            occurrence_count=4,
        )
        s4 = RecurringSubscription(
            user_id=demo.id,
            merchant_norm="amazon web services",
            display_name="AWS Cloud Hosting",
            avg_amount_minor=4550,
            currency="AUD",
            cadence_days=30,
            first_seen=today - timedelta(days=90),
            last_seen=today - timedelta(days=3),
            next_expected=today + timedelta(days=27),
            status="active",
            occurrence_count=3,
        )
        db.add_all([s1, s2, s3, s4])
        await db.commit()

    # 10. Anomalies & Alerts
    existing_alerts = (
        await db.execute(select(Alert).where(Alert.user_id == demo.id))
    ).scalars().all()
    if not existing_alerts:
        a1 = Alert(
            user_id=demo.id,
            type="spending_spike",
            severity="warning",
            title="Unusual dining transaction detected",
            body="Transaction of $320.00 at Rockpool Dining is 3.8x your average restaurant spend.",
            payload={"merchant": "Rockpool Bar & Grill", "amount_minor": 32000, "z_score": 3.8, "category": "Dining Out"},
            read_at=None,
        )
        a2 = Alert(
            user_id=demo.id,
            type="duplicate_subscription",
            severity="info",
            title="Potential duplicate streaming subscription",
            body="Detected both Netflix ($16.99) and Stan ($16.00) charges within 48 hours.",
            payload={"subscriptions": ["Netflix", "Stan"], "cadence_days": 30},
            read_at=None,
        )
        a3 = Alert(
            user_id=demo.id,
            type="budget_overspend",
            severity="warning",
            title="Dining Out budget near limit (88%)",
            body="You have spent $396.00 of your $450.00 Dining Out envelope with 12 days remaining.",
            payload={"category": "Dining Out", "allocated_minor": 45000, "spent_minor": 39600, "percent": 88.0},
            read_at=None,
        )
        db.add_all([a1, a2, a3])
        await db.commit()

    # 11. Knowledge Corpus for RAG
    for title, content in KNOWLEDGE:
        existing_doc = await db.scalar(
            select(KnowledgeDoc).where(KnowledgeDoc.title == title, KnowledgeDoc.user_id.is_(None))
        )
        if not existing_doc:
            from app.ai.rag import ingest_document

            await ingest_document(db, title, content, user_id=None, source_type="guide")

    await db.commit()
    print("Seed complete. Login: demo@financebuddy.app / DemoPass123!")


async def seed(session: AsyncSession | None = None) -> None:
    if session is not None:
        await _seed_with_session(session)
    else:
        async with engine.begin() as conn:
            pass
        async with SessionFactory() as db:
            await _seed_with_session(db)


if __name__ == "__main__":
    asyncio.run(seed())
