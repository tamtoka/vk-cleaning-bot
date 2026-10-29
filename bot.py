"""Учебный бот ВКонтакте для каталога услуг химчистки.

Бот работает через Long Poll API (библиотека vkbottle) и умеет:
- показывать главное меню по командам «Начать», «Старт», «Меню»;
- показывать каталог услуг и карточку выбранной услуги;
- показывать прайс-лист;
- показывать контакт менеджера из настроек;
- понятно отвечать на неизвестные сообщения и возвращать в меню.

Токен и контакт менеджера читаются из локального файла .env.
Токен никогда не выводится в консоль и не запрашивается в переписке.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from dotenv import load_dotenv
from vkbottle import Keyboard, Text
from vkbottle.bot import Bot, Message

BASE_DIR = Path(__file__).resolve().parent
CATALOG_PATH = BASE_DIR / "catalog.json"
ENV_PATH = BASE_DIR / ".env"

# Команды, которые открывают главное меню.
MENU_TRIGGERS = {"начать", "старт", "меню", "/start", "/menu"}
# Возврат в главное меню.
BACK_TRIGGERS = {"назад", "в меню", "главное меню"}
# Кнопки разделов.
SERVICES_TRIGGERS = {"услуги"}
PRICE_TRIGGERS = {"прайс-лист", "прайс", "цены"}
MANAGER_TRIGGERS = {"связаться с менеджером", "менеджер", "связаться"}
REQUEST_TRIGGERS = {"оставить заявку", "оформить заявку", "заявка"}
CANCEL_TRIGGERS = {"отмена", "отменить"}
CONFIRM_TRIGGERS = {"подтвердить заявку", "подтвердить"}

MANAGER_CONTACT_MISSING = "Контакт менеджера пока не указан"

# Ключи клавиатур, которые возвращает route_message.
MAIN_KEYBOARD = "main"
SERVICES_KEYBOARD = "services"
SERVICE_KEYBOARD = "service"


class SettingsError(Exception):
    """Настройки отсутствуют или заполнены неверно."""


@dataclass(frozen=True)
class Service:
    """Одна услуга из каталога."""

    id: str
    name: str
    description: str
    price: str


@dataclass(frozen=True)
class Settings:
    """Настройки бота из файла .env."""

    token: str
    manager_contact: str


@dataclass(frozen=True)
class Reply:
    """Ответ бота: текст и какую клавиатуру показать."""

    text: str
    keyboard: str


def load_settings(env_path: Path = ENV_PATH) -> Settings:
    """Читает .env и возвращает настройки.

    Без VK_TOKEN работа невозможна, поэтому выбрасывается SettingsError.
    Пустой MANAGER_CONTACT допустим.
    """
    load_dotenv(env_path)
    token = (os.getenv("VK_TOKEN") or "").strip()
    contact = (os.getenv("MANAGER_CONTACT") or "").strip()

    if not token:
        raise SettingsError(
            "Не найден VK_TOKEN. Скопируйте файл .env.example в .env "
            "и заполните в нём VK_TOKEN ключом доступа сообщества."
        )
    if token != os.getenv("VK_TOKEN"):
        # На всякий случай: значения с пробелами по краям считаем ошибкой ввода.
        raise SettingsError(
            "VK_TOKEN содержит лишние пробелы по краям. Уберите пробелы в файле .env."
        )

    return Settings(token=token, manager_contact=contact)


def load_catalog(path: Path = CATALOG_PATH) -> list[Service]:
    """Загружает и проверяет каталог услуг из JSON-файла."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SettingsError(f"Не найден файл каталога: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SettingsError(
            f"Файл каталога {path.name} содержит некорректный JSON: {exc}"
        ) from exc

    if not isinstance(raw, list) or not raw:
        raise SettingsError(
            f"Файл каталога {path.name} должен содержать непустой список услуг."
        )

    services: list[Service] = []
    seen_ids: set[str] = set()
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            raise SettingsError(
                f"Услуга №{index} в каталоге должна быть объектом с полями "
                "id, name, description, price."
            )
        missing = [
            field
            for field in ("id", "name", "description", "price")
            if not str(item.get(field, "")).strip()
        ]
        if missing:
            raise SettingsError(
                f"В услуге №{index} каталога не заполнены поля: {', '.join(missing)}."
            )
        service_id = str(item["id"]).strip()
        if service_id in seen_ids:
            raise SettingsError(f"В каталоге повторяется id услуги: {service_id}.")
        seen_ids.add(service_id)
        services.append(
            Service(
                id=service_id,
                name=str(item["name"]).strip(),
                description=str(item["description"]).strip(),
                price=str(item["price"]).strip(),
            )
        )

    return services


def normalize(text: str) -> str:
    """Приводит текст к нижнему регистру и убирает лишние пробелы.

    Благодаря этому «Начать», «начать» и «НАЧАТЬ» обрабатываются одинаково.
    """
    return " ".join(text.strip().casefold().split())


def main_menu_text() -> str:
    return (
        "Здравствуйте! Это бот химчистки.\n\n"
        "Выберите раздел с помощью кнопок внизу:\n"
        "• Услуги\n"
        "• Прайс-лист\n"
        "• Связаться с менеджером\n"
        "• Оставить заявку"
    )


def services_text(catalog: list[Service]) -> str:
    lines = ["Каталог услуг:"]
    lines.extend(f"• {service.name} — {service.price}" for service in catalog)
    lines.append("")
    lines.append("Нажмите на нужную услугу, чтобы узнать подробности.")
    return "\n".join(lines)


def service_card_text(service: Service) -> str:
    return f"{service.name}\n\n{service.description}\n\nЦена: {service.price}"


def price_list_text(catalog: list[Service]) -> str:
    lines = ["Прайс-лист (демонстрационные цены):"]
    lines.extend(f"• {service.name} — {service.price}" for service in catalog)
    return "\n".join(lines)


def manager_text(manager_contact: str) -> str:
    if not manager_contact:
        return MANAGER_CONTACT_MISSING
    return f"Связаться с менеджером:\n{manager_contact}"


def unknown_text() -> str:
    return (
        "Я не понял это сообщение.\n\n"
        "Пожалуйста, воспользуйтесь кнопками ниже "
        "или напишите «Меню», чтобы вернуться в главное меню."
    )


def route_message(
    raw_text: str,
    catalog: list[Service],
    manager_contact: str = "",
) -> Reply:
    """Определяет ответ бота по тексту сообщения.

    Функция не зависит от ВКонтакте, поэтому её легко проверять тестами.
    """
    text = normalize(raw_text)

    if text in MENU_TRIGGERS or text in BACK_TRIGGERS:
        return Reply(main_menu_text(), MAIN_KEYBOARD)
    if text in SERVICES_TRIGGERS:
        return Reply(services_text(catalog), SERVICES_KEYBOARD)
    if text in PRICE_TRIGGERS:
        return Reply(price_list_text(catalog), MAIN_KEYBOARD)
    if text in MANAGER_TRIGGERS:
        return Reply(manager_text(manager_contact), MAIN_KEYBOARD)
    if text in REQUEST_TRIGGERS:
        return Reply("Чтобы оформить заявку, нажмите кнопку «Оставить заявку».", MAIN_KEYBOARD)

    services_by_name = {normalize(service.name): service for service in catalog}
    if text in services_by_name:
        return Reply(service_card_text(services_by_name[text]), SERVICE_KEYBOARD)

    return Reply(unknown_text(), MAIN_KEYBOARD)


def main_keyboard() -> Keyboard:
    keyboard = Keyboard(one_time=False, inline=False)
    keyboard.add(Text("Услуги"))
    keyboard.row()
    keyboard.add(Text("Прайс-лист"))
    keyboard.row()
    keyboard.add(Text("Связаться с менеджером"))
    keyboard.row()
    keyboard.add(Text("Оставить заявку"))
    return keyboard


def services_keyboard(catalog: list[Service]) -> Keyboard:
    keyboard = Keyboard(one_time=False, inline=False)
    for service in catalog:
        keyboard.add(Text(service.name))
        keyboard.row()
    keyboard.add(Text("Прайс-лист"))
    keyboard.row()
    keyboard.add(Text("Главное меню"))
    return keyboard


def service_keyboard() -> Keyboard:
    keyboard = Keyboard(one_time=False, inline=False)
    keyboard.add(Text("Услуги"))
    keyboard.row()
    keyboard.add(Text("Главное меню"))
    return keyboard




def request_services_keyboard(catalog: list[Service]) -> Keyboard:
    """Показывает услуги для оформления заявки и кнопку отмены."""
    keyboard = Keyboard(one_time=False, inline=False)
    for service in catalog:
        keyboard.add(Text(service.name))
        keyboard.row()
    keyboard.add(Text("Отмена"))
    return keyboard


def request_cancel_keyboard() -> Keyboard:
    """Клавиатура для шага заявки с вводом текста."""
    return Keyboard(one_time=False, inline=False).add(Text("Отмена"))


def request_confirm_keyboard() -> Keyboard:
    keyboard = Keyboard(one_time=False, inline=False)
    keyboard.add(Text("Подтвердить заявку"))
    keyboard.row()
    keyboard.add(Text("Отмена"))
    return keyboard


def request_summary(service: Service, preferred_time: str, customer_contact: str) -> str:
    return (
        "Заявка на химчистку\n"
        f"Услуга: {service.name}\n"
        f"Когда удобно: {preferred_time}\n"
        f"Контакт для ответа: {customer_contact}"
    )


def request_mailto_link(manager_contact: str, summary: str) -> str | None:
    """Создаёт письмо в почтовом приложении, не отправляя его автоматически."""
    recipient = manager_contact.strip()
    if "@" not in recipient:
        return None
    subject = quote("Заявка на химчистку", safe="")
    body = quote(summary, safe="")
    return f"mailto:{recipient}?subject={subject}&body={body}"

def get_keyboard(key: str, catalog: list[Service]) -> Keyboard:
    """Возвращает клавиатуру по её ключу из route_message."""
    if key == SERVICES_KEYBOARD:
        return services_keyboard(catalog)
    if key == SERVICE_KEYBOARD:
        return service_keyboard()
    return main_keyboard()


def build_bot(settings: Settings, catalog: list[Service]) -> Bot:
    """Создаёт бота и регистрирует обработчик сообщений."""
    bot = Bot(settings.token)
    request_sessions: dict[int, dict[str, str]] = {}

    @bot.on.message()
    async def handle_message(message: Message) -> None:
        raw_text = message.text or ""
        text = normalize(raw_text)
        user_id = int(message.from_id or 0)

        if text in MENU_TRIGGERS or text in BACK_TRIGGERS:
            request_sessions.pop(user_id, None)
            reply = route_message(raw_text, catalog, settings.manager_contact)
            await message.answer(reply.text, keyboard=get_keyboard(reply.keyboard, catalog))
            return

        if text in CANCEL_TRIGGERS and user_id in request_sessions:
            request_sessions.pop(user_id, None)
            await message.answer("Оформление заявки отменено.", keyboard=main_keyboard())
            return

        if text in REQUEST_TRIGGERS:
            request_sessions[user_id] = {"step": "service"}
            await message.answer(
                "Давайте оформим заявку. Выберите услугу:",
                keyboard=request_services_keyboard(catalog),
            )
            return

        session = request_sessions.get(user_id)
        if session:
            step = session.get("step")

            if step == "service":
                services_by_name = {normalize(service.name): service for service in catalog}
                service = services_by_name.get(text)
                if service is None:
                    await message.answer(
                        "Выберите услугу кнопкой или напишите «Отмена».",
                        keyboard=request_services_keyboard(catalog),
                    )
                    return
                session["service_id"] = service.id
                session["step"] = "preferred_time"
                await message.answer(
                    f"Когда вам удобно провести услугу «{service.name}»? Напишите дату "
                    "или примерный период, например «в выходные».",
                    keyboard=request_cancel_keyboard(),
                )
                return

            if step == "preferred_time":
                preferred_time = raw_text.strip()
                if len(preferred_time) < 2:
                    await message.answer(
                        "Напишите дату или примерный период, например «в выходные».",
                        keyboard=request_cancel_keyboard(),
                    )
                    return
                session["preferred_time"] = preferred_time
                session["step"] = "customer_contact"
                await message.answer(
                    "Оставьте телефон или email, чтобы менеджер мог ответить. "
                    "Для отмены напишите «Отмена».",
                    keyboard=request_cancel_keyboard(),
                )
                return

            if step == "customer_contact":
                customer_contact = raw_text.strip()
                if len(customer_contact) < 3:
                    await message.answer(
                        "Укажите телефон или email для ответа менеджера.",
                        keyboard=request_cancel_keyboard(),
                    )
                    return
                session["customer_contact"] = customer_contact
                session["step"] = "confirm"
                service = next(
                    (item for item in catalog if item.id == session.get("service_id")),
                    None,
                )
                if service is None:
                    request_sessions.pop(user_id, None)
                    await message.answer(
                        "Не получилось найти услугу. Начните оформление заявки заново.",
                        keyboard=main_keyboard(),
                    )
                    return
                summary = request_summary(
                    service,
                    session["preferred_time"],
                    session["customer_contact"],
                )
                await message.answer(
                    f"Проверьте заявку:\n\n{summary}\n\n"
                    "Если всё верно, нажмите «Подтвердить заявку».",
                    keyboard=request_confirm_keyboard(),
                )
                return

            if step == "confirm":
                if text not in CONFIRM_TRIGGERS:
                    await message.answer(
                        "Подтвердите заявку кнопкой или напишите «Отмена».",
                        keyboard=request_confirm_keyboard(),
                    )
                    return
                service = next(
                    (item for item in catalog if item.id == session.get("service_id")),
                    None,
                )
                if service is None:
                    request_sessions.pop(user_id, None)
                    await message.answer(
                        "Не получилось найти услугу. Начните оформление заявки заново.",
                        keyboard=main_keyboard(),
                    )
                    return
                summary = request_summary(
                    service,
                    session["preferred_time"],
                    session["customer_contact"],
                )
                mailto = request_mailto_link(settings.manager_contact, summary)
                if mailto:
                    answer = (
                        "Заявка подготовлена. Откройте ссылку, чтобы создать письмо "
                        "и отправить его менеджеру:\n"
                        f"{mailto}\n\n"
                        f"Кому: {settings.manager_contact}\n\n"
                        f"{summary}\n\n"
                        "Письмо отправится только после вашего подтверждения "
                        "в почтовом приложении."
                    )
                else:
                    contact = settings.manager_contact or MANAGER_CONTACT_MISSING
                    answer = (
                        "Заявка собрана:\n\n"
                        f"{summary}\n\n"
                        f"Контакт менеджера: {contact}"
                    )
                request_sessions.pop(user_id, None)
                await message.answer(answer, keyboard=main_keyboard())
                return

        reply = route_message(raw_text, catalog, settings.manager_contact)
        await message.answer(reply.text, keyboard=get_keyboard(reply.keyboard, catalog))

    return bot

def _setup_console() -> None:
    """Делает вывод кириллицы читаемым в консоли Windows."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


def main() -> int:
    _setup_console()
    try:
        settings = load_settings()
        catalog = load_catalog()
    except SettingsError as exc:
        print(f"Ошибка настроек: {exc}")
        return 1

    bot = build_bot(settings, catalog)
    print("Запускаю бота…")
    bot.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
