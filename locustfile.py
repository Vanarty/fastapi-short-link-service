"""Нагрузочное тестирование URL Shortener.

Запуск:
    locust -f locustfile.py --host http://localhost:8000

Или без UI:
    locust -f locustfile.py --host http://localhost:8000 \
           --headless -u 50 -r 10 --run-time 60s \
           --html report.html
"""

import uuid

from locust import HttpUser, between, tag, task


class LinkShortenerUser(HttpUser):
    # Интервал между запросами
    wait_time = between(0.5, 2)

    def on_start(self):
        # Генерируем случайное имя пользователя
        uid = uuid.uuid4().hex[:8]
        self.username = f"loaduser_{uid}"
        self.client.post(
            "/users/register",
            json={"username": self.username, "password": "loadtest123"},
        )
        resp = self.client.post(
            "/users/login",
            data={"username": self.username, "password": "loadtest123"},
        )
        self.token = resp.json().get("access_token", "")  # Токен авторизации
        # Список коротких кодов
        self.short_codes: list[str] = []
        # Счетчик для генерации уникальных URL
        self._counter = 0

    def _auth(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    # Задача для создания короткой ссылки
    # @task(n) - декоратор, где n - вес задачи (чем больше, тем чаще выполняется)
    @task(3)
    @tag("create")  # @tag() - для группировки и выборочного запуска задач
    def create_link(self):
        self._counter += 1
        resp = self.client.post(
            "/links/shorten",
            json={
                "original_url": (
                    f"https://loadtest.example.com/{self.username}/{self._counter}"
                )
            },
            headers=self._auth(),
            name="/links/shorten",
        )
        if resp.status_code == 201:
            self.short_codes.append(resp.json()["short_code"])

    # Задача для перенаправления на короткую ссылку
    @task(5)
    @tag("redirect")
    def redirect_link(self):
        if not self.short_codes:
            return
        code = self.short_codes[-1]
        self.client.get(
            f"/links/{code}",
            name="/links/[short_code]",
            allow_redirects=False,  # False - не следовать автоматически за редиректом
        )

    # Задача для получения статистики по короткой ссылке
    @task(2)
    @tag("stats")
    def get_stats(self):
        if not self.short_codes:
            return
        code = self.short_codes[-1]
        self.client.get(
            f"/links/{code}/stats",
            name="/links/[short_code]/stats",
        )

    # Задача для поиска ссылки по оригинальному URL
    @task(1)
    @tag("search")
    def search_link(self):
        if not self.short_codes:
            return
        self.client.get(
            "/links/search",
            params={
                "original_url": (f"https://loadtest.example.com/{self.username}/1")
            },
            name="/links/search",
        )
