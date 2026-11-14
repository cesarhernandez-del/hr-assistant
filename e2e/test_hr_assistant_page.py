"""End-to-end test of the API key handling on the web page."""

from playwright.sync_api import Page, expect


def test_wrong_api_key_shows_invalid_key_message(page: Page):
    page.goto("/")
    page.get_by_test_id("api-key").fill("this-is-not-a-valid-key")
    page.get_by_test_id("question").fill("Who works in engineering?")
    page.get_by_test_id("send").click()
    expect(page.get_by_test_id("answer")).to_contain_text("Clave inválida")
