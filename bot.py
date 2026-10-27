"""Учебный бот-каталог услуг химчистки для VK Community Long Poll."""

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from dotenv import load_dotenv
from vkbottle import Bot, Keyboard, Text


BASE_DIR = Path(__file__).resolve().parent
CATALOG_PATH = BASE_DIR / "services.json"
START_COMMANDS = {"начать", "старт", "меню"}
SERVICES_BUTTON = "Услуги"
PRICE_BUTTON = "Прайс-лист"
MANAGER_BUTTON = "Связаться с менеджером"
BACK_BUTTON = "Главное меню"


class ConfigurationError(ValueError):
    """Ошибка отсутствующих или некорректных настроек запуска."""


@dataclass(frozen=True)
class Settings:
    token: str
    manager_contact: str


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    """Загружает настройки, не включая их значения в текст ошибок."""
    values = os.environ if env is None else env
    missing = [
        name
        for name in ("VK_TOKEN", "MANAGER_CONTACT")
        if not values.get(name, "").strip()
    ]
    if missing:
        names = ", ".join(missing)
        raise ConfigurationError(
            f"Не заданы настройки: {names}. Заполните их в локальном файле .env "
            "по примеру .env.example и перезапустите бота."
        )
    return Settings(
        token=values["VK_TOKEN"].strip(),
        manager_contact=values["MANAGER_CONTACT"].strip(),
    )


def load_catalog(path: Path = CATALOG_PATH) -> list[dict[str, str]]:
    """Читает и проверяет каталог из JSON."""
    try:
        with path.open(encoding="utf-8") as catalog_file:
            catalog: Any = json.load(catalog_file)
    except FileNotFoundError as error:
        raise ValueError(f"Файл каталога не найден: {path.name}") from error
    except json.JSONDecodeError as error:
        raise ValueError(f"В файле {path.name} некорректный JSON.") from error

    if not isinstance(catalog, list) or not catalog:
        raise ValueError("Каталог должен быть непустым списком услуг.")

    required = {"id", "name", "description", "price"}
    ids: set[str] = set()
    for index, service in enumerate(catalog, start=1):
        if not isinstance(service, dict) or not required.issubset(service):
            raise ValueError(
                f"Услуга №{index} должна содержать поля: "
                + ", ".join(sorted(required))
                + "."
            )
        if any(not isinstance(service[field], str) or not service[field].strip() for field in required):
            raise ValueError(f"У услуги №{index} все поля должны быть непустыми строками.")
        if service["id"] in ids:
            raise ValueError(f"Повторяется идентификатор услуги: {service['id']}.")
        ids.add(service["id"])
    return catalog


def build_main_keyboard() -> Keyboard:
    keyboard = Keyboard(one_time=False)
    keyboard.add(Text(SERVICES_BUTTON)).row()
    keyboard.add(Text(PRICE_BUTTON)).row()
    keyboard.add(Text(MANAGER_BUTTON))
    return keyboard


def build_catalog_keyboard(catalog: list[dict[str, str]]) -> Keyboard:
    keyboard = Keyboard(one_time=False)
    for service in catalog:
        keyboard.add(Text(service["name"])).row()
    keyboard.add(Text(BACK_BUTTON))
    return keyboard


def build_back_keyboard() -> Keyboard:
    return Keyboard(one_time=False).add(Text(BACK_BUTTON))


def format_main_menu() -> str:
    return "Здравствуйте! Выберите раздел:"


def format_catalog(catalog: list[dict[str, str]]) -> str:
    return "Выберите услугу из каталога:"


def format_service(service: dict[str, str]) -> str:
    return (
        f"{service['name']}\n{service['description']}\n"
        f"Стоимость: {service['price']}\n\n"
        "Цены демонстрационные. Точную стоимость уточняйте у менеджера."
    )


def format_price_list(catalog: list[dict[str, str]]) -> str:
    lines = ["Прайс-лист (демонстрационные цены):"]
    lines.extend(f"• {service['name']} — {service['price']}" for service in catalog)
    lines.append("\nТочную стоимость уточняйте у менеджера.")
    return "\n".join(lines)


def reply_for(text: str | None, catalog: list[dict[str, str]], manager_contact: str) -> tuple[str, str]:
    """Возвращает текст ответа и тип клавиатуры для команды пользователя."""
    command = (text or "").strip().casefold()
    services_by_name = {service["name"].casefold(): service for service in catalog}

    if command in START_COMMANDS or command == BACK_BUTTON.casefold():
        return format_main_menu(), "main"
    if command == SERVICES_BUTTON.casefold():
        return format_catalog(catalog), "catalog"
    if command == PRICE_BUTTON.casefold():
        return format_price_list(catalog), "main"
    if command == MANAGER_BUTTON.casefold():
        return f"Связаться с менеджером: {manager_contact}", "main"
    if command in services_by_name:
        return format_service(services_by_name[command]), "back"
    return "Не понял сообщение. Выберите раздел на клавиатуре или напишите «Меню».", "main"


def create_bot(settings: Settings, catalog: list[dict[str, str]]) -> Bot:
    bot = Bot(token=settings.token)
    main_keyboard = build_main_keyboard()
    catalog_keyboard = build_catalog_keyboard(catalog)
    back_keyboard = build_back_keyboard()
    @bot.on.message()
    async def handle_message(message):
        answer, keyboard_type = reply_for(message.text, catalog, settings.manager_contact)
        keyboard = {
            "main": main_keyboard,
            "catalog": catalog_keyboard,
            "back": back_keyboard,
        }[keyboard_type]
        await message.answer(answer, keyboard=keyboard)

    return bot


def main() -> None:
    load_dotenv(BASE_DIR / ".env")
    try:
        settings = load_settings()
        catalog = load_catalog()
    except (ConfigurationError, ValueError) as error:
        raise SystemExit(f"Ошибка настройки бота: {error}") from None

    # Не печатать token или объект Bot: они могут содержать секретные данные.
    create_bot(settings, catalog).run_forever()


if __name__ == "__main__":
    main()
