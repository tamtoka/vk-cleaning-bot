"""Локальные тесты бота.

Эти тесты не подключаются к ВКонтакте, не используют настоящий токен
и не запускают Long Poll. Они проверяют только логику:
каталог, меню, обработку команд и клавиатуры.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import bot

BASE_DIR = Path(__file__).resolve().parent.parent
CATALOG_PATH = BASE_DIR / "catalog.json"


@pytest.fixture(scope="module")
def catalog() -> list[bot.Service]:
    return bot.load_catalog(CATALOG_PATH)


@pytest.fixture(scope="module")
def catalog_names(catalog: list[bot.Service]) -> list[str]:
    return [service.name for service in catalog]


def keyboard_labels(keyboard) -> list[str]:
    payload = keyboard.get_json()
    if isinstance(payload, str):
        payload = json.loads(payload)
    labels: list[str] = []
    for row in payload["buttons"]:
        for button in row:
            labels.append(button["action"]["label"])
    return labels


# --- Каталог -----------------------------------------------------------------


def test_catalog_has_four_expected_services(catalog):
    assert [service.id for service in catalog] == ["sofa", "armchair", "mattress", "carpet"]
    assert [service.name for service in catalog] == [
        "Химчистка дивана",
        "Химчистка кресла",
        "Химчистка матраса",
        "Чистка ковра",
    ]
    assert [service.price for service in catalog] == [
        "от 2500 ₽",
        "от 1000 ₽",
        "от 1500 ₽",
        "от 300 ₽/м²",
    ]


def test_catalog_services_have_descriptions(catalog):
    for service in catalog:
        assert len(service.description) > 20


def test_catalog_missing_file_raises(tmp_path):
    with pytest.raises(bot.SettingsError):
        bot.load_catalog(tmp_path / "нет-такого-файла.json")


def test_catalog_invalid_json_raises(tmp_path):
    broken = tmp_path / "broken.json"
    broken.write_text("{ это не json", encoding="utf-8")
    with pytest.raises(bot.SettingsError):
        bot.load_catalog(broken)


def test_catalog_empty_list_raises(tmp_path):
    empty = tmp_path / "empty.json"
    empty.write_text("[]", encoding="utf-8")
    with pytest.raises(bot.SettingsError):
        bot.load_catalog(empty)


def test_catalog_missing_field_raises(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(
        '[{"id": "sofa", "name": "Химчистка дивана", "price": "от 2500 ₽"}]',
        encoding="utf-8",
    )
    with pytest.raises(bot.SettingsError):
        bot.load_catalog(bad)


def test_catalog_duplicate_id_raises(tmp_path):
    bad = tmp_path / "dup.json"
    item = {
        "id": "sofa",
        "name": "Химчистка дивана",
        "description": "Описание услуги для теста.",
        "price": "от 2500 ₽",
    }
    bad.write_text(json.dumps([item, item], ensure_ascii=False), encoding="utf-8")
    with pytest.raises(bot.SettingsError):
        bot.load_catalog(bad)


# --- Настройки ---------------------------------------------------------------


def test_settings_require_token(tmp_path, monkeypatch):
    monkeypatch.delenv("VK_TOKEN", raising=False)
    with pytest.raises(bot.SettingsError):
        bot.load_settings(tmp_path / "нет-файла.env")


def test_settings_read_token_and_allow_empty_contact(monkeypatch):
    monkeypatch.setenv("VK_TOKEN", "учебный-токен")
    monkeypatch.delenv("MANAGER_CONTACT", raising=False)
    settings = bot.load_settings(Path("нет-файла.env"))
    assert settings.token == "учебный-токен"
    assert settings.manager_contact == ""


# --- Меню и команды ----------------------------------------------------------


@pytest.mark.parametrize(
    "command",
    ["Начать", "начать", "НАЧАТЬ", "Старт", "старт", "Меню", "меню", "/start", "/menu"],
)
def test_start_commands_open_main_menu(command, catalog):
    reply = bot.route_message(command, catalog)
    assert reply.keyboard == bot.MAIN_KEYBOARD
    assert "Услуги" in reply.text
    assert "Прайс-лист" in reply.text
    assert "Связаться с менеджером" in reply.text


@pytest.mark.parametrize("command", ["Назад", "назад", "В меню", "Главное меню"])
def test_back_returns_to_main_menu(command, catalog):
    reply = bot.route_message(command, catalog)
    assert reply.keyboard == bot.MAIN_KEYBOARD


def test_services_section_lists_all_services(catalog, catalog_names):
    reply = bot.route_message("Услуги", catalog)
    assert reply.keyboard == bot.SERVICES_KEYBOARD
    for name in catalog_names:
        assert name in reply.text


def test_price_list_shows_all_services_with_prices(catalog):
    reply = bot.route_message("Прайс-лист", catalog)
    assert reply.keyboard == bot.MAIN_KEYBOARD
    for service in catalog:
        assert service.name in reply.text
        assert service.price in reply.text


@pytest.mark.parametrize("index", [0, 1, 2, 3])
def test_service_card_shows_name_description_and_price(index, catalog, catalog_names):
    service = catalog[index]
    reply = bot.route_message(service.name, catalog)
    assert reply.keyboard == bot.SERVICE_KEYBOARD
    assert service.name in reply.text
    assert service.description in reply.text
    assert service.price in reply.text


def test_service_card_works_for_different_letter_case(catalog):
    reply = bot.route_message("химчистка дивана", catalog)
    assert reply.keyboard == bot.SERVICE_KEYBOARD
    assert "Химчистка дивана" in reply.text


def test_manager_contact_is_shown(catalog):
    reply = bot.route_message("Связаться с менеджером", catalog, "+7 900 000-00-00")
    assert "+7 900 000-00-00" in reply.text


def test_manager_contact_missing_message(catalog):
    reply = bot.route_message("Связаться с менеджером", catalog, "")
    assert reply.text == bot.MANAGER_CONTACT_MISSING


def test_unknown_message_returns_hint(catalog):
    reply = bot.route_message("привет, а сколько будет стоить?", catalog)
    assert reply.keyboard == bot.MAIN_KEYBOARD
    assert "не понял" in reply.text.lower()


# --- Клавиатуры --------------------------------------------------------------


def test_main_keyboard_buttons(catalog):
    assert keyboard_labels(bot.main_keyboard()) == [
        "Услуги",
        "Прайс-лист",
        "Связаться с менеджером",
        "Оставить заявку",
    ]


def test_services_keyboard_buttons(catalog, catalog_names):
    labels = keyboard_labels(bot.services_keyboard(catalog))
    assert labels == catalog_names + ["Прайс-лист", "Главное меню"]


def test_service_keyboard_buttons(catalog):
    assert keyboard_labels(bot.service_keyboard()) == ["Услуги", "Главное меню"]


def test_get_keyboard_returns_requested_keyboard(catalog):
    assert keyboard_labels(bot.get_keyboard(bot.MAIN_KEYBOARD, catalog)) == [
        "Услуги",
        "Прайс-лист",
        "Связаться с менеджером",
    ]
    assert "Химчистка дивана" in keyboard_labels(
        bot.get_keyboard(bot.SERVICES_KEYBOARD, catalog)
    )
    assert keyboard_labels(bot.get_keyboard(bot.SERVICE_KEYBOARD, catalog)) == [
        "Услуги",
        "Главное меню",
    ]


# --- Файлы настроек ----------------------------------------------------------


def test_gitignore_hides_env_and_venv():
    content = (BASE_DIR / ".gitignore").read_text(encoding="utf-8")
    assert ".env" in content
    assert ".venv" in content


def test_logging_backend_supports_opt():
    # vkbottle/tools/_runner.py вызывает logger.opt(...) при ошибке.
    # Если loguru не установлен, modules.py подставляет logging-адаптер
    # без метода .opt(), и настоящая ошибка маскируется AttributeError.
    import vkbottle.modules as vkbottle_modules

    assert hasattr(vkbottle_modules.logger, "opt")


def test_env_example_has_empty_values():
    content = (BASE_DIR / ".env.example").read_text(encoding="utf-8")
    assert "VK_TOKEN=" in content
    assert "MANAGER_CONTACT=" in content
    for line in content.splitlines():
        if line.startswith(("VK_TOKEN=", "MANAGER_CONTACT=")):
            assert line.strip().endswith("=")
