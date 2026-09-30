from __future__ import annotations

from fastdrop.ui.theme import get_app_stylesheet


def test_app_theme_stylesheet_is_populated() -> None:
    stylesheet = get_app_stylesheet()
    assert "FastDrop" not in stylesheet
    assert "QPushButton" in stylesheet
    assert "QFrame#card" in stylesheet
    assert "QLineEdit" in stylesheet
    assert "QProgressBar" in stylesheet
