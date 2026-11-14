"""End-to-end tests of the question and answer page (fake model)."""

import os
import re

from playwright.sync_api import Page, expect


def open_page_with_key(page: Page) -> None:
    """Open the page and type the API key given by the verification."""
    page.goto("/")
    page.get_by_test_id("api-key").fill(os.environ["E2E_API_KEY"])


def ask(page: Page, text: str) -> None:
    """Type a question and send it with the button."""
    page.get_by_test_id("question").fill(text)
    page.get_by_test_id("send").click()


def test_user_sees_the_answer_with_a_request_id_after_sending_a_question(page: Page):
    open_page_with_key(page)
    ask(page, "How many vacation days does Ana have?")
    expect(page.get_by_test_id("answer")).to_contain_text(
        re.compile(r"request_id: (?!desconocido)\S+")
    )


def test_question_is_shown_in_the_conversation(page: Page):
    open_page_with_key(page)
    ask(page, "Tell me about the sales department")
    expect(page.get_by_test_id("answer")).to_contain_text(
        "Tell me about the sales department"
    )


def test_input_is_cleared_after_sending(page: Page):
    open_page_with_key(page)
    ask(page, "Who is the manager of finance?")
    expect(page.get_by_test_id("question")).to_have_value("")


def test_empty_question_shows_an_error_message_in_spanish(page: Page):
    open_page_with_key(page)
    ask(page, "")
    expect(page.get_by_test_id("answer")).to_contain_text(
        re.compile(r"pregunta", re.IGNORECASE)
    )


def test_second_question_keeps_the_previous_conversation(page: Page):
    open_page_with_key(page)
    ask(page, "First question about Ana")
    expect(page.get_by_test_id("answer")).to_contain_text("request_id:")
    ask(page, "Second question about Luis")
    answer = page.get_by_test_id("answer")
    expect(answer).to_contain_text("Second question about Luis")
    expect(answer).to_contain_text("First question about Ana")
