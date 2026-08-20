from __future__ import annotations

from pathlib import Path
import importlib
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from backend.image_sop.config import Settings
from backend.image_sop.services.excel_service import ExcelService
from backend.image_sop.services.lingxing_service import LingxingService


def test_resolve_store_id_prefers_selected_sid() -> None:
    service = LingxingService(
        Settings(lingxing_publish_store_id=99, lingxing_default_sid=7)
    )
    assert service._resolve_store_id(12) == 12
    assert service._resolve_store_id(None) == 99
    assert service._resolve_store_id(0) == 99


def test_resolve_store_id_falls_back_to_default_sid() -> None:
    service = LingxingService(
        Settings(lingxing_publish_store_id=0, lingxing_default_sid=7)
    )
    assert service._resolve_store_id(None) == 7
    assert service._resolve_store_id(0) == 7


def test_excel_convert_missing_file_raises(tmp_path: Path) -> None:
    service = ExcelService(tmp_path)
    with pytest.raises(ValueError, match="无法转为 JPEG"):
        service._convert_file_map_or_raise(
            {"broken.jpg": tmp_path / "missing.jpg"},
            "参考图",
        )


def test_excel_convert_corrupt_file_raises(tmp_path: Path) -> None:
    service = ExcelService(tmp_path)
    bad = tmp_path / "bad.jpg"
    bad.write_bytes(b"not-an-image")
    with pytest.raises(ValueError, match="无法转为 JPEG"):
        service._convert_file_map_or_raise({"bad.jpg": bad}, "参考图")
    assert bad.exists()


def test_excel_convert_valid_jpeg_keeps_file(tmp_path: Path) -> None:
    from PIL import Image

    service = ExcelService(tmp_path)
    src = tmp_path / "ok.png"
    Image.new("RGB", (8, 8), color=(20, 80, 160)).save(src)
    converted = service._convert_file_map_or_raise({"ok.png": src}, "参考图")
    assert converted["ok.png"].suffix.lower() == ".jpg"
    assert converted["ok.png"].exists()


def test_web_search_only_has_baidu_engine() -> None:
    from backend.image_sop.services import web_image_search_service as module
    from backend.image_sop.services.web_image_search_service import WebImageSearchService

    assert hasattr(WebImageSearchService, "_search_baidu")
    assert not hasattr(WebImageSearchService, "_search_bing")
    assert not hasattr(WebImageSearchService, "_search_google")
    assert not hasattr(WebImageSearchService, "_engine_order")
    assert not hasattr(module, "BING_SEARCH_URL")


def test_nas_raw_and_refined_dir_helpers() -> None:
    from backend.image_sop.services.nas_image_service import NasImageService as Nas

    assert Nas._is_raw_dir("RAW")
    assert Nas._is_raw_dir("原始文件")
    assert not Nas._is_raw_dir("jpg")
    assert Nas._is_refined_dir("jpg")
    assert Nas._is_refined_dir("白底精修")
    assert not Nas._is_refined_dir("RAW")
    assert Nas._is_raw_file("shot.tif")
    assert not Nas._is_raw_file("7.jpg")


def test_nas_likely_main_only_in_design_dept() -> None:
    from backend.image_sop.services.nas_image_service import NasImageService as Nas

    design = "/JMH/供应链中心/设计部/FCA-50411-0412"
    month = "/JMH/供应链中心/2024.9/FCA-50411-0412"
    assert Nas._is_likely_main_image("7.jpg", design)
    assert Nas._is_likely_main_image("8 拷贝.jpg", design)
    assert not Nas._is_likely_main_image("7.jpg", month)
    assert not Nas._is_likely_main_image("白底.jpg", design)
    assert Nas._is_white_bg_image("白底.jpg")


def test_image_sop_api_requires_internal_token_and_erp_identity(monkeypatch) -> None:
    module = importlib.import_module("backend.image_sop.app")
    monkeypatch.setattr(
        module,
        "platform_settings",
        SimpleNamespace(python_internal_api_token="unit-secret"),
    )
    client = TestClient(module.app)

    direct = client.get(
        "/api/sop/generation-status",
        headers={"Referer": "http://testserver/image-sop/"},
    )
    assert direct.status_code == 401

    no_identity = client.get(
        "/api/sop/generation-status",
        headers={"X-Internal-Token": "unit-secret"},
    )
    assert no_identity.status_code == 401

    trusted = client.get(
        "/api/sop/generation-status",
        headers={
            "X-Internal-Token": "unit-secret",
            "X-ERP-User-ID": "101",
            "X-ERP-Username-B64": "bGVpeW9uZ3l1",
        },
    )
    assert trusted.status_code == 200
    assert trusted.json()["per_user_limit"] == 1
