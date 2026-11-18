"""Unit tests for app.pii: masking of personal data by regular expressions.

``mask(text)`` returns ``(masked_text, types)`` where ``types`` is a sorted
list without repeats, in lowercase (``email``, ``phone``, ``curp``, ``rfc``,
``card``).
"""

import pytest

from app.pii import mask

CURP = "GOMC800101HDFRRS09"
RFC = "GOMC800101AB1"


def test_email_is_masked():
    text, types = mask("Escribe a ana.lopez@empresa.com hoy")
    assert text == "Escribe a [EMAIL] hoy"
    assert types == ["email"]


@pytest.mark.parametrize(
    "number",
    ["5512345678", "55 1234 5678", "55-1234-5678", "+52 55 1234 5678", "+525512345678"],
)
def test_ten_digit_phone_is_masked_in_any_format(number):
    text, types = mask(f"Llamame al {number} gracias")
    assert "[PHONE]" in text
    assert "1234" not in text
    assert types == ["phone"]


def test_curp_and_rfc_are_masked_each_with_its_own_marker():
    text, types = mask(f"CURP {CURP} y RFC {RFC}")
    assert text == "CURP [CURP] y RFC [RFC]"
    assert types == ["curp", "rfc"]


@pytest.mark.parametrize("card", ["4111111111111", "4111 1111 1111 1111"])
def test_cards_of_13_and_16_digits_are_masked(card):
    text, types = mask(f"Tarjeta {card}")
    assert text == "Tarjeta [CARD]"
    assert types == ["card"]


def test_twelve_digits_are_not_a_card():
    text, types = mask("Folio 411111111111")
    assert "[CARD]" not in text
    assert "card" not in types


def test_phone_is_not_taken_from_inside_a_card():
    text, types = mask("Tarjeta 4111111111111111")
    assert "[PHONE]" not in text
    assert types == ["card"]


def test_text_without_personal_data_is_unchanged():
    question = "Quien trabaja en Ventas con id EMP-0002?"
    assert mask(question) == (question, [])


def test_several_data_together_give_sorted_types_without_repeats():
    text, types = mask("a@x.com, b@y.com, 5512345678 y " + CURP)
    assert text.count("[EMAIL]") == 2
    assert types == ["curp", "email", "phone"]


def test_masked_text_never_contains_the_original_value():
    text, _ = mask("Mi correo es secreto@example.com")
    assert "secreto" not in text
