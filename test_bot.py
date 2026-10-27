import unittest
from pathlib import Path

from bot import (
    ConfigurationError,
    format_price_list,
    load_catalog,
    load_settings,
    reply_for,
)


class BotLogicTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = load_catalog()

    def test_catalog_has_four_services_and_demo_prices(self):
        self.assertEqual(len(self.catalog), 4)
        prices = format_price_list(self.catalog)
        for expected in ("2500 ₽", "1000 ₽", "1500 ₽", "300 ₽/м²"):
            self.assertIn(expected, prices)
        self.assertIn("демонстрационные", prices)

    def test_start_commands_and_menu_return(self):
        for command in ("Начать", "Старт", "Меню", "Главное меню"):
            with self.subTest(command=command):
                answer, keyboard = reply_for(command, self.catalog, "@manager")
                self.assertIn("Выберите раздел", answer)
                self.assertEqual(keyboard, "main")

    def test_service_selection_shows_name_description_and_price(self):
        answer, keyboard = reply_for("Химчистка дивана", self.catalog, "@manager")
        self.assertIn("Химчистка дивана", answer)
        self.assertIn("обивки дивана", answer)
        self.assertIn("2500 ₽", answer)
        self.assertEqual(keyboard, "back")

    def test_manager_contact_is_displayed_without_claiming_submission(self):
        answer, _ = reply_for("Связаться с менеджером", self.catalog, "@manager")
        self.assertIn("@manager", answer)
        self.assertNotIn("отправ", answer.casefold())

    def test_unknown_text_has_helpful_reply(self):
        answer, keyboard = reply_for("неизвестная команда", self.catalog, "@manager")
        self.assertIn("Не понял", answer)
        self.assertIn("Меню", answer)
        self.assertEqual(keyboard, "main")

    def test_missing_settings_name_only_missing_variables(self):
        with self.assertRaises(ConfigurationError) as context:
            load_settings({"VK_TOKEN": "", "MANAGER_CONTACT": ""})
        self.assertIn("VK_TOKEN", str(context.exception))
        self.assertIn("MANAGER_CONTACT", str(context.exception))
        self.assertNotIn("secret", str(context.exception))

    def test_invalid_catalog_is_rejected(self):
        path = Path(__file__).with_name("invalid-services.json")
        path.write_text("{}", encoding="utf-8")
        try:
            with self.assertRaisesRegex(ValueError, "непустым списком"):
                load_catalog(path)
        finally:
            path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
