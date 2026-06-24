from backend.app.core.config import settings
from backend.app.services.video_generation import _task_url_to_local_path


def test_task_url_to_local_path_rejects_task_directory(monkeypatch):
    monkeypatch.setattr(settings, "money_printer_project_dir", "D:/workplace/MoneyPrinterTurbo")

    assert _task_url_to_local_path("abc123", "http://moneyprinter/api/v1/tasks/abc123") == ""


def test_task_url_to_local_path_maps_task_file(monkeypatch):
    monkeypatch.setattr(settings, "money_printer_project_dir", "D:/workplace/MoneyPrinterTurbo")

    local_path = _task_url_to_local_path(
        "abc123",
        "http://moneyprinter/storage/tasks/abc123/final.mp4",
    )

    normalized = local_path.replace("\\", "/")
    assert normalized.endswith("/storage/tasks/abc123/final.mp4")


def test_task_url_to_local_path_returns_empty_when_project_dir_missing(monkeypatch):
    monkeypatch.setattr(settings, "money_printer_project_dir", "")

    local_path = _task_url_to_local_path("abc123", "http://moneyprinter/storage/tasks/abc123/final.mp4")

    assert local_path == ""
