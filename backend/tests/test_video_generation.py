from backend.app.core.config import settings
import httpx

from backend.app.services.video_generation import (
    _task_url_to_local_path,
    cleanup_money_printer_video_materials,
    money_printer_health,
    money_printer_payload,
)


def test_money_printer_payload_uses_local_materials():
    payload = money_printer_payload("新中式宣传片", materials=["living-room.mp4", " cabinet.png "])

    assert payload["video_source"] == "local"
    assert payload["video_materials"] == [
        {"provider": "local", "url": "living-room.mp4", "duration": 0},
        {"provider": "local", "url": "cabinet.png", "duration": 0},
    ]


def test_cleanup_money_printer_video_materials_deletes_local_files(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "money_printer_project_dir", str(tmp_path))
    local_videos = tmp_path / "storage" / "local_videos"
    local_videos.mkdir(parents=True)
    material = local_videos / "clip.mp4"
    material.write_bytes(b"video")

    result = cleanup_money_printer_video_materials(["clip.mp4"])

    assert result["deleted"] == ["clip.mp4"]
    assert not material.exists()


def test_cleanup_money_printer_video_materials_uses_filename_only(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "money_printer_project_dir", str(tmp_path))
    local_videos = tmp_path / "storage" / "local_videos"
    local_videos.mkdir(parents=True)
    outside = tmp_path / "outside.mp4"
    outside.write_bytes(b"keep")

    result = cleanup_money_printer_video_materials(["../outside.mp4"])

    assert result["deleted"] == []
    assert outside.exists()


def test_money_printer_health_counts_local_materials(monkeypatch):
    client_factory = httpx.Client

    def handler(request):
        assert str(request.url).endswith("/video_materials")
        return httpx.Response(200, json={"data": {"files": [{"file": "a.mp4"}, {"file": "b.png"}]}})

    monkeypatch.setattr(httpx, "Client", lambda **_: client_factory(transport=httpx.MockTransport(handler)))

    result = money_printer_health()

    assert result["ok"] is True
    assert result["localMaterials"] == 2


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
