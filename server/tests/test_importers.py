from datetime import date

from app.services.importers import _parse_amount, _parse_date, parse_csv


CSV_SAMPLE = b""""Date","Amount","Merchant Name","Description"
"2026-01-05","-42.10","WOOLWORTHS 2211","Groceries run"
"15/01/2026","1200.00","ACME PAYROLL","Salary"
"2026-01-25","(25.00)","ATM FEE",""
"""


def test_parse_dates():
    assert _parse_date("2026-01-05") == date(2026, 1, 5)
    assert _parse_date("15/01/2026") == date(2026, 1, 15)


def test_parse_amounts():
    assert _parse_amount("-42.10") == -4210
    assert _parse_amount("(25.00)") == -2500
    assert _parse_amount("$1,200.00") == 120000


def test_csv_rows_parsed():
    txns = parse_csv(CSV_SAMPLE)
    assert len(txns) == 3
    assert txns[0].amount_minor == -4210
    assert "woolworths" in txns[0].merchant_raw.lower()


def test_csv_debit_credit_columns():
    csv_bytes = b""""Date","Merchant","Debit","Credit"
"2026-02-01","Supermarket","55.20",""
"2026-02-02","Employer","","2500.00"
"""
    txns = parse_csv(csv_bytes)
    assert len(txns) == 2
    assert txns[0].amount_minor == -5520
    assert txns[1].amount_minor == 250000


def test_receipt_text_parser():
    from app.services.receipt_ocr import parse_receipt_text

    sample = """STARBUCKS COFFEE
Date: 2026-03-10
Caffe Latte $4.50
Blueberry Muffin $3.75
Subtotal: $8.25
Tax: $0.75
Total: $9.00"""
    res = parse_receipt_text(sample)
    assert "starbucks" in res["merchant"].lower()
    assert res["date"] == "2026-03-10"
    assert res["total_minor"] == 900
    assert res["total_amount"] == 9.00
    assert res["currency"] == "USD"
    assert len(res["items"]) >= 1
