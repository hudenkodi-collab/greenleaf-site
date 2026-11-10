#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверка качества статического сайта перед публикацией.

Скрипт запускается в CI перед деплоем и проверяет:
  * наличие обязательных файлов index.html и style.css;
  * базовую структуру HTML (doctype, lang, charset, viewport, title);
  * подключение внешней таблицы стилей и отсутствие inline-стилей;
  * баланс фигурных скобок в CSS;
  * существование локальных файлов, на которые ссылаются src и href;
  * существование якорей, на которые ведут внутренние ссылки.

Возвращает код 0, если ошибок нет, и код 1 при найденных проблемах.
"""

from __future__ import annotations

import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlparse

BASE_DIR = Path(__file__).resolve().parent.parent
HTML_FILE = BASE_DIR / "index.html"
CSS_FILE = BASE_DIR / "style.css"

errors: list[str] = []
checks: list[str] = []


class SiteParser(HTMLParser):
    """Собирает идентификаторы, ссылки и признаки структуры страницы."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.ids: set[str] = set()
        self.refs: list[str] = []
        self.has_style_tag = False
        self.has_title = False
        self.has_charset = False
        self.has_viewport = False
        self.has_css_link = False
        self._inside_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        data = dict(attrs)

        if "id" in data and data["id"]:
            self.ids.add(data["id"])

        if tag == "style":
            self.has_style_tag = True
        if tag == "title":
            self._inside_title = True
        if tag == "meta":
            if (data.get("charset") or "").lower() == "utf-8":
                self.has_charset = True
            if (data.get("name") or "").lower() == "viewport":
                self.has_viewport = True
        if tag == "link":
            rel = (data.get("rel") or "").lower()
            href = data.get("href") or ""
            if "stylesheet" in rel and href == "style.css":
                self.has_css_link = True
        if tag in {"a", "img", "script", "link"}:
            ref = data.get("href") or data.get("src")
            if ref:
                self.refs.append(ref)

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._inside_title = False

    def handle_data(self, data: str) -> None:
        if self._inside_title and data.strip():
            self.has_title = True


def check(condition: bool, ok_message: str, error_message: str) -> None:
    if condition:
        checks.append(ok_message)
    else:
        errors.append(error_message)


def is_local_reference(ref: str) -> bool:
    parsed = urlparse(ref)
    if parsed.scheme or parsed.netloc:
        return False
    if ref.startswith(("#", "mailto:", "tel:", "data:", "javascript:")):
        return False
    return True


def main() -> int:
    check(HTML_FILE.is_file(), "index.html найден", "Не найден файл index.html")
    check(CSS_FILE.is_file(), "style.css найден", "Не найден файл style.css")

    if not HTML_FILE.is_file() or not CSS_FILE.is_file():
        for message in errors:
            print(f"ОШИБКА: {message}")
        return 1

    html = HTML_FILE.read_text(encoding="utf-8")
    css = CSS_FILE.read_text(encoding="utf-8")

    check(html.lstrip().lower().startswith("<!doctype html>"),
          "Указан HTML5 doctype", "Не указан <!DOCTYPE html>")
    check(re.search(r'<html[^>]+lang="ru"', html, re.I) is not None,
          "Указан язык страницы lang=\"ru\"", "В теге <html> не указан lang=\"ru\"")

    parser = SiteParser()
    parser.feed(html)
    parser.close()

    check(parser.has_charset, "Указана кодировка UTF-8", "Не указана кодировка UTF-8")
    check(parser.has_viewport, "Указан viewport для мобильных устройств",
          "Не указан meta viewport")
    check(parser.has_title, "Заголовок страницы заполнен", "Пустой или отсутствующий <title>")
    check(parser.has_css_link, "Подключён внешний файл style.css",
          "Нет подключения style.css через <link rel=\"stylesheet\">")
    check(not parser.has_style_tag, "Inline-стили отсутствуют",
          "В HTML остались inline-стили <style>")

    check(css.strip() != "", "style.css не пустой", "Файл style.css пустой")
    check(css.count("{") == css.count("}"),
          "Фигурные скобки в CSS сбалансированы",
          "В style.css нарушен баланс фигурных скобок")

    missing_files = []
    broken_anchors = []
    for ref in parser.refs:
        if ref.startswith("#"):
            anchor = unquote(ref[1:])
            if anchor and anchor not in parser.ids:
                broken_anchors.append(ref)
        elif is_local_reference(ref):
            path = unquote(urlparse(ref).path)
            if path and not (BASE_DIR / path).exists():
                missing_files.append(ref)

    check(not missing_files, "Все локальные файлы существуют",
          "Не найдены локальные файлы: " + ", ".join(sorted(set(missing_files))))
    check(not broken_anchors, "Все внутренние якоря существуют",
          "Не найдены якоря: " + ", ".join(sorted(set(broken_anchors))))

    for message in checks:
        print(f"OK: {message}")

    if errors:
        print()
        for message in errors:
            print(f"ОШИБКА: {message}")
        print(f"\nПроверка не пройдена: ошибок — {len(errors)}.")
        return 1

    print(f"\nПроверка пройдена: {len(checks)} проверок, ошибок нет.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
