from app.ai.pii import mask_pii


def test_masks_email():
    assert "[EMAIL]" in mask_pii("contact me at john.doe@example.com please")


def test_masks_phone():
    masked = mask_pii("call +61 412 345 678 now")
    assert "[PHONE]" in masked


def test_masks_valid_card_luhn():
    assert "[CARD]" in mask_pii("card 4532015112830366 on file")


def test_keeps_random_numbers():
    text = "invoice 12345 total"
    assert "12345" in mask_pii(text)


def test_masks_iban():
    assert "[IBAN]" in mask_pii("transfer to DE89370400440532013000")
