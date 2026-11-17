from __future__ import annotations

import asyncio

from backend.api.v1 import finance


def _assert_export_is_deleted_after_response(tmp_path, monkeypatch, exporter_name, endpoint):
    export_path = tmp_path / "temporary-export.xlsx"
    export_path.write_bytes(b"xlsx")
    monkeypatch.setattr(
        finance,
        exporter_name,
        lambda _month: (str(export_path), "download.xlsx"),
    )

    response = asyncio.run(endpoint("2026-08"))

    assert export_path.exists()
    assert response.background is not None
    asyncio.run(response.background())
    assert not export_path.exists()


def test_inventory_age_export_deletes_temporary_file_after_send(tmp_path, monkeypatch):
    _assert_export_is_deleted_after_response(
        tmp_path,
        monkeypatch,
        "export_inventory_age_details",
        finance.get_inventory_age_detail_export,
    )


def test_performance_source_export_deletes_temporary_file_after_send(tmp_path, monkeypatch):
    _assert_export_is_deleted_after_response(
        tmp_path,
        monkeypatch,
        "export_amz_performance_source",
        finance.get_amz_performance_source_export,
    )
