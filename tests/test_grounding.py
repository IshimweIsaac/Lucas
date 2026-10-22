"""Tests for core/grounding — models, capture, atspi_tree, ocr, template,
vision_crop, verify. All hermetic: external deps (Atspi, pytesseract,
cv2, genai, mss, grim) are mocked."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

from core.grounding import (
    SOURCE_A11Y,
    SOURCE_NONE,
    SOURCE_OCR,
    SOURCE_TEMPLATE,
    SOURCE_VISION,
    SOURCES,
    GroundingResult,
    WordBox,
    clamp,
    verify_after_click,
)
from core.grounding import atspi_tree, capture, vision_crop
from core.grounding import sway_geometry


# ---------------------------------------------------------------------------
# models
# ---------------------------------------------------------------------------


def test_grounding_result_defaults():
    r = GroundingResult(found=False)
    assert r.source == SOURCE_NONE
    assert r.x == 0 and r.y == 0
    assert r.confidence == 0.0
    assert r.label == "" and r.note == ""


def test_grounding_result_found_fields():
    r = GroundingResult(found=True, source=SOURCE_A11Y, x=10, y=20, confidence=0.9, label="Save")
    assert r.found and r.x == 10 and r.y == 20 and r.label == "Save"


def test_sources_constant():
    assert SOURCES == (SOURCE_A11Y, SOURCE_OCR, SOURCE_TEMPLATE, SOURCE_VISION, SOURCE_NONE)


def test_wordbox_centroid():
    box = WordBox("Save", x=10, y=20, w=30, h=40)
    assert box.cx == 25
    assert box.cy == 40


# ---------------------------------------------------------------------------
# verify.clamp
# ---------------------------------------------------------------------------


def test_clamp_inside():
    assert clamp(10, 10, 1920, 1080) == (10, 10)


def test_clamp_out_of_bounds():
    assert clamp(-5, -5, 1920, 1080) == (0, 0)
    assert clamp(5000, 5000, 1920, 1080) == (1919, 1079)


def test_clamp_zero_screen():
    assert clamp(5, 5, 0, 0) == (0, 0)


# ---------------------------------------------------------------------------
# capture
# ---------------------------------------------------------------------------


def test_capture_screen_uses_grim_before_mss(monkeypatch):
    calls: list[str] = []

    def fake_grim():
        calls.append("grim")
        return None

    def fake_mss():
        calls.append("mss")
        img = SimpleNamespace(width=10, height=10, convert=lambda mode: "img")
        return img, 10, 10

    monkeypatch.setattr(capture, "_capture_grim", fake_grim)
    monkeypatch.setattr(capture, "_capture_mss", fake_mss)
    monkeypatch.setattr(capture, "_capture_pyautogui", lambda: (None, 0, 0))
    result = capture.capture_screen()
    assert calls == ["grim", "mss"]
    assert result[1] == 10 and result[2] == 10


def test_capture_screen_all_backends_fail(monkeypatch):
    monkeypatch.setattr(capture, "_capture_grim", lambda: None)
    monkeypatch.setattr(capture, "_capture_mss", lambda: None)
    monkeypatch.setattr(capture, "_capture_pyautogui", lambda: None)
    assert capture.capture_screen() is None


def test_capture_never_uses_gnome_screenshot(monkeypatch):
    called: list[str] = []

    monkeypatch.setattr(capture, "_capture_grim", lambda: called.append("grim") or None)
    monkeypatch.setattr(capture, "_capture_mss", lambda: called.append("mss") or None)
    monkeypatch.setattr(capture, "_capture_pyautogui", lambda: called.append("pyautogui") or None)
    capture.capture_screen()
    assert "gnome-screenshot" not in " ".join(called)


def test_screen_size_via_mss(monkeypatch):
    class FakeMss:
        def __init__(self):
            self.monitors = [{"width": 1920, "height": 1080}]

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(capture, "_MSS", True)
    monkeypatch.setattr(capture, "mss", SimpleNamespace(mss=FakeMss))
    assert capture.screen_size() == (1920, 1080)


def test_screen_size_none(monkeypatch):
    monkeypatch.setattr(capture, "_MSS", False)
    monkeypatch.setattr(capture, "_PYAUTOGUI", False)
    assert capture.screen_size() is None


class _FakeImage:
    def __init__(self):
        self.crop_box = None

    def crop(self, box):
        self.crop_box = box
        return self

    def convert(self, mode):
        return self


def test_capture_region_clamps_and_returns_origin(monkeypatch):
    fake_img = _FakeImage()
    monkeypatch.setattr(capture, "screen_size", lambda: (100, 100))
    monkeypatch.setattr(capture, "capture_screen", lambda: (fake_img, 100, 100))
    img, ox, oy = capture.capture_region((50, 50, 100, 100))  # extends past edge
    assert fake_img.crop_box == (50, 50, 100, 100)
    assert img is fake_img
    assert (ox, oy) == (50, 50)


def test_capture_region_fully_outside_returns_none(monkeypatch):
    monkeypatch.setattr(capture, "screen_size", lambda: (100, 100))
    monkeypatch.setattr(capture, "capture_screen", lambda: (_FakeImage(), 100, 100))
    assert capture.capture_region((200, 200, 10, 10)) is None


def test_swaymsg_window_rect_parse(monkeypatch):
    tree = {
        "nodes": [
            {
                "pid": 1,
                "rect": {"x": 0, "y": 0, "width": 1920, "height": 1080},
                "nodes": [
                    {"pid": 123, "rect": {"x": 100, "y": 50, "width": 800, "height": 600}}
                ],
            }
        ]
    }

    class _Proc:
        returncode = 0
        stdout = json.dumps(tree)

    monkeypatch.setattr(sway_geometry, "_which", lambda name: True)
    monkeypatch.setattr(sway_geometry, "subprocess", SimpleNamespace(run=lambda *a, **k: _Proc()))
    assert sway_geometry.swaymsg_window_rect(123) == (100, 50, 800, 600)


def test_swaymsg_window_rect_no_pid_match(monkeypatch):
    class _Proc:
        returncode = 0
        stdout = json.dumps({"nodes": [{"pid": 1}]})

    monkeypatch.setattr(sway_geometry, "_which", lambda name: True)
    monkeypatch.setattr(sway_geometry, "subprocess", SimpleNamespace(run=lambda *a, **k: _Proc()))
    assert sway_geometry.swaymsg_window_rect(999) is None


def test_swaymsg_window_rect_failure(monkeypatch):
    monkeypatch.setattr(sway_geometry, "_which", lambda name: True)
    monkeypatch.setattr(sway_geometry, "subprocess", SimpleNamespace(run=lambda *a, **k: SimpleNamespace(returncode=1, stdout="")))
    assert sway_geometry.swaymsg_window_rect(1) is None


def test_swaymsg_window_rect_no_binary(monkeypatch):
    monkeypatch.setattr(sway_geometry, "_which", lambda name: False)
    assert sway_geometry.swaymsg_window_rect(1) is None


# ---------------------------------------------------------------------------
# atspi_tree
# ---------------------------------------------------------------------------


class _FakeNode:
    def __init__(self, name="", role="", children=None, parent=None, clickable=True, extents=None, pid=None):
        self._name = name
        self._role = role
        self._children = children or []
        self._parent = parent
        self._clickable = clickable
        self.extents = extents or (0, 0, 0, 0)
        self.pid = pid

    def get_name(self):
        return self._name

    def get_child_count(self):
        return len(self._children)

    def get_child_at_index(self, i):
        return self._children[i]

    def get_parent(self):
        return self._parent

    def get_extents(self, coord):
        return self.extents

    def get_process_id(self):
        return self.pid


def _mk_tree(names):
    """Build a chain of parent->child nodes: root -> n0 -> n1 -> ..."""
    parent = None
    node = None
    for name in names:
        node = _FakeNode(name=name, parent=parent)
        if parent is not None:
            parent._children.append(node)
        parent = node
    return node


def test_a11y_unavailable_when_no_gi(monkeypatch):
    monkeypatch.setattr(atspi_tree, "_ATSPI", False)
    assert atspi_tree.a11y_available() is False
    assert atspi_tree.find_node("anything") is None


def test_a11y_available_with_desktop(monkeypatch):
    monkeypatch.setattr(atspi_tree, "_ATSPI", True)
    monkeypatch.setattr(atspi_tree.Atspi, "get_desktop", lambda idx: object())
    assert atspi_tree.a11y_available() is True


def test_find_node_matches_name(monkeypatch):
    desktop = _FakeNode(name="root")
    save = _FakeNode(name="Save Document")
    desktop._children.append(save)
    monkeypatch.setattr(atspi_tree, "_ATSPI", True)
    monkeypatch.setattr(atspi_tree, "a11y_available", lambda: True)
    monkeypatch.setattr(atspi_tree, "_desktop", lambda: desktop)
    node = atspi_tree.find_node("save")
    assert node is save


def test_find_node_respects_role(monkeypatch):
    desktop = _FakeNode(name="root")
    btn = _FakeNode(name="Save")
    desktop._children.append(btn)
    monkeypatch.setattr(atspi_tree, "_ATSPI", True)
    monkeypatch.setattr(atspi_tree, "a11y_available", lambda: True)
    monkeypatch.setattr(atspi_tree, "_desktop", lambda: desktop)
    monkeypatch.setattr(atspi_tree, "_node_role", lambda node: node._role or "unknown")
    assert atspi_tree.find_node("save", role="button") is None  # role mismatch
    btn._role = "push button"
    assert atspi_tree.find_node("save", role="button") is btn


def test_find_node_depth_cap(monkeypatch):
    desktop = _FakeNode(name="root")
    cur = desktop
    for i in range(10):
        child = _FakeNode(name=f"node-{i}")
        cur._children.append(child)
        cur = child
    monkeypatch.setattr(atspi_tree, "_ATSPI", True)
    monkeypatch.setattr(atspi_tree, "a11y_available", lambda: True)
    monkeypatch.setattr(atspi_tree, "_desktop", lambda: desktop)
    # depth 9 > cap 6 — must not be found
    assert atspi_tree.find_node("node-9") is None
    # shallow node found
    assert atspi_tree.find_node("node-1") is not None


def test_find_node_uses_window_hint(monkeypatch):
    desktop = _FakeNode(name="root")
    firefox = _FakeNode(name="Firefox — Shared")
    chrome = _FakeNode(name="Chrome")
    save_ff = _FakeNode(name="Save")
    save_chrome = _FakeNode(name="Save")
    firefox._children.append(save_ff)
    chrome._children.append(save_chrome)
    desktop._children.extend([firefox, chrome])
    monkeypatch.setattr(atspi_tree, "_ATSPI", True)
    monkeypatch.setattr(atspi_tree, "a11y_available", lambda: True)
    monkeypatch.setattr(atspi_tree, "_desktop", lambda: desktop)
    node = atspi_tree.find_node("save", window_hint="firefox")
    assert node is save_ff


class _ClickableNode(_FakeNode):
    pass


def test_node_global_center_x11(monkeypatch):
    node = _FakeNode(extents=(100, 150, 200, 100), clickable=True)
    monkeypatch.setattr(atspi_tree, "_ATSPI", True)
    monkeypatch.setattr(atspi_tree, "_is_wayland", lambda: False)
    monkeypatch.setattr(atspi_tree, "_is_clickable", lambda n: n._clickable)
    assert atspi_tree.node_global_center(node) == (200, 200)


def test_node_global_center_clickable_ancestor(monkeypatch):
    child = _FakeNode(extents=(0, 0, 0, 0), clickable=False)
    parent = _FakeNode(extents=(100, 100, 200, 200), clickable=True)
    child._parent = parent
    monkeypatch.setattr(atspi_tree, "_ATSPI", True)
    monkeypatch.setattr(atspi_tree, "_is_wayland", lambda: False)
    monkeypatch.setattr(atspi_tree, "_is_clickable", lambda n: n._clickable)
    assert atspi_tree.node_global_center(child) == (200, 200)


def test_node_global_center_wayland_compose(monkeypatch):
    root = _FakeNode(name="root")
    win = _FakeNode(name="window", parent=root, pid=424, clickable=False)
    node = _FakeNode(parent=win, extents=(20, 30, 100, 50), clickable=True)
    win._children.append(node)
    root._children.append(win)
    monkeypatch.setattr(atspi_tree, "_ATSPI", True)
    monkeypatch.setattr(atspi_tree, "_is_wayland", lambda: True)
    monkeypatch.setattr(atspi_tree, "_desktop", lambda: root)
    monkeypatch.setattr(atspi_tree, "_is_clickable", lambda n: n._clickable)
    monkeypatch.setattr(sway_geometry, "swaymsg_window_rect", lambda pid: (300, 200, 800, 600))
    assert atspi_tree.node_global_center(node) == (370, 255)


def test_node_global_center_wayland_pid_unmatchable(monkeypatch):
    root = _FakeNode(name="root")
    win = _FakeNode(name="win", parent=root, pid=12345, clickable=False)
    node = _FakeNode(parent=win, extents=(0, 0, 50, 50), clickable=True)
    win._children.append(node)
    monkeypatch.setattr(atspi_tree, "_ATSPI", True)
    monkeypatch.setattr(atspi_tree, "_is_wayland", lambda: True)
    monkeypatch.setattr(atspi_tree, "_desktop", lambda: root)
    monkeypatch.setattr(atspi_tree, "_is_clickable", lambda n: n._clickable)
    monkeypatch.setattr(sway_geometry, "swaymsg_window_rect", lambda pid: None)
    assert atspi_tree.node_global_center(node) is None


# ---------------------------------------------------------------------------
# ocr_grounding
# ---------------------------------------------------------------------------

from core.grounding import ocr_grounding as ocr_mod  # noqa: E402


def test_ocr_available_requires_both(monkeypatch):
    monkeypatch.setattr(ocr_mod, "_TESSERACT", True)
    monkeypatch.setattr(ocr_mod, "_TESSERACT_BIN", False)
    assert ocr_mod.ocr_available() is False
    monkeypatch.setattr(ocr_mod, "_TESSERACT", False)
    monkeypatch.setattr(ocr_mod, "_TESSERACT_BIN", True)
    assert ocr_mod.ocr_available() is False


def test_ocr_words_empty_when_unavailable(monkeypatch):
    monkeypatch.setattr(ocr_mod, "_TESSERACT", False)
    assert ocr_mod.ocr_words("img") == []


def test_ocr_words_parses_dict(monkeypatch):
    fake = SimpleNamespace(
        Output=SimpleNamespace(DICT="dict"),
        image_to_data=lambda image, lang, output_type: {
            "text": ["Save", "", "Open"],
            "left": [1, 2, 3],
            "top": [4, 5, 6],
            "width": [10, 20, 30],
            "height": [40, 50, 60],
            "conf": [90, -1, 30],
        },
    )
    monkeypatch.setattr(ocr_mod, "_TESSERACT", True)
    monkeypatch.setattr(ocr_mod, "_TESSERACT_BIN", True)
    monkeypatch.setattr(ocr_mod, "pytesseract", fake, raising=False)
    words = ocr_mod.ocr_words("img")
    assert len(words) == 2
    assert words[0].text == "Save"
    assert words[0].cx == 1 + 5
    assert words[0].cy == 4 + 20
    assert words[1].conf == 30.0


def test_match_words_exact_case_insensitive():
    words = [WordBox("save", 0, 0, 10, 10)]
    assert ocr_mod.match_words(words, "SAVE") is words[0]


def test_match_words_substring():
    words = [WordBox("Save Document", 0, 0, 10, 10)]
    assert ocr_mod.match_words(words, "save") is words[0]


def test_match_words_fuzzy(monkeypatch):
    monkeypatch.setattr(
        ocr_mod, "_fuzzy_ratio", lambda a, b: 0.9 if ("sav" in a and "sav" in b) else 0.0
    )
    words = [WordBox("sav button", 0, 0, 10, 10)]
    assert ocr_mod.match_words(words, "save button") is words[0]


def test_match_words_no_match():
    words = [WordBox("Cancel", 0, 0, 10, 10)]
    assert ocr_mod.match_words(words, "save") is None


def test_match_words_empty():
    assert ocr_mod.match_words([WordBox("Save", 0, 0, 10, 10)], "") is None


# ---------------------------------------------------------------------------
# template_grounding
# ---------------------------------------------------------------------------

from core.grounding import template_grounding as tpl_mod  # noqa: E402

PNG_1PX = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c626001000000ffff03000006000557"
    "bfabd40000000049454e44ae426082"
)


def test_template_unavailable_empty_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(tpl_mod, "_CV2", True)
    monkeypatch.setattr(tpl_mod, "_NP", True)
    monkeypatch.setattr(tpl_mod, "_TEMPLATE_DIR", tmp_path)
    assert tpl_mod.template_available() is False
    assert tpl_mod.template_match("img", "save") is None


def test_template_match_with_mock_cv2(monkeypatch, tmp_path):
    (tmp_path / "save_button.png").write_bytes(PNG_1PX)
    import numpy as np

    fake_cv2 = SimpleNamespace(
        cvtColor=lambda img, code: np.zeros((20, 30), dtype=np.uint8),
        imread=lambda path, flags: np.zeros((5, 5), dtype=np.uint8),
        matchTemplate=lambda img, tpl, method: np.zeros((16, 26), dtype=np.float32),
        minMaxLoc=lambda arr: (0.0, 0.9, (0, 0), (12, 10)),
        TM_CCOEFF_NORMED=1,
        IMREAD_GRAYSCALE=0,
        COLOR_RGB2GRAY=6,
    )
    monkeypatch.setattr(tpl_mod, "_CV2", True)
    monkeypatch.setattr(tpl_mod, "_NP", True)
    monkeypatch.setattr(tpl_mod, "_TEMPLATE_DIR", tmp_path)
    monkeypatch.setattr(tpl_mod, "cv2", fake_cv2)
    score, cx, cy = tpl_mod.template_match("img", "save button")
    assert score == 0.9
    assert (cx, cy) == (12 + 2, 10 + 2)


# ---------------------------------------------------------------------------
# vision_crop
# ---------------------------------------------------------------------------


def test_parse_vision_reply_valid():
    assert vision_crop._parse_vision_reply("CENTER 100 50") == ("CENTER", 100, 50)
    assert vision_crop._parse_vision_reply("POINT 5 6") == ("POINT", 5, 6)
    assert vision_crop._parse_vision_reply("not_found") == ("NOT_FOUND", 0, 0)
    assert vision_crop._parse_vision_reply("NOT_FOUND\n") == ("NOT_FOUND", 0, 0)


def test_parse_vision_reply_malformed():
    assert vision_crop._parse_vision_reply("100,50") is None
    assert vision_crop._parse_vision_reply("center x y") is None
    assert vision_crop._parse_vision_reply("CENTER 100") is None
    assert vision_crop._parse_vision_reply(None) is None
    assert vision_crop._parse_vision_reply("") is None


def test_vision_locate_requires_genai(monkeypatch):
    monkeypatch.setattr(vision_crop, "_GENAI", False)
    assert vision_crop.vision_locate("x") is None


def test_vision_locate_requires_key(monkeypatch):
    monkeypatch.setattr(vision_crop, "_GENAI", True)
    monkeypatch.setattr(vision_crop, "_PIL", True)
    monkeypatch.setattr(vision_crop, "get_gemini_key", lambda: None)
    assert vision_crop.vision_locate("x") is None


def test_vision_locate_success(monkeypatch):
    from PIL import Image as PILImage

    monkeypatch.setattr(vision_crop, "_GENAI", True)
    monkeypatch.setattr(vision_crop, "_PIL", True)
    monkeypatch.setattr(vision_crop, "get_gemini_key", lambda: "abc")
    monkeypatch.setattr(capture, "screen_size", lambda: (1920, 1080))

    img = PILImage.new("RGB", (100, 100), "white")
    monkeypatch.setattr(vision_crop, "capture_region", lambda box: (img, 400, 300))

    class Models:
        def generate_content(self, model, contents=None):
            return SimpleNamespace(text="CENTER 10 20")

    class Client:
        def __init__(self, api_key):
            self._key = api_key
            self.models = Models()

    monkeypatch.setattr(vision_crop, "genai", SimpleNamespace(Client=Client))
    assert vision_crop.vision_locate("save") == (410, 320)
    assert vision_crop._VISION_MODEL == "gemini-3.1-flash-lite-preview"


def test_vision_locate_out_of_bounds_retries_then_none(monkeypatch):
    from PIL import Image as PILImage

    monkeypatch.setattr(vision_crop, "_GENAI", True)
    monkeypatch.setattr(vision_crop, "_PIL", True)
    monkeypatch.setattr(vision_crop, "get_gemini_key", lambda: "abc")
    monkeypatch.setattr(capture, "screen_size", lambda: (1920, 1080))
    img = PILImage.new("RGB", (100, 100), "white")
    monkeypatch.setattr(vision_crop, "capture_region", lambda box: (img, 0, 0))

    calls = {"n": 0}

    class Models:
        def generate_content(self, model, contents=None):
            calls["n"] += 1
            return SimpleNamespace(text="CENTER 5000 5000")

    class Gen:
        def __init__(self, api_key):
            self.models = Models()

    monkeypatch.setattr(vision_crop, "genai", SimpleNamespace(Client=Gen))
    assert vision_crop.vision_locate("save") is None
    assert calls["n"] == 3


def test_vision_locate_malformed_retries_then_succeeds(monkeypatch):
    from PIL import Image as PILImage

    monkeypatch.setattr(vision_crop, "_GENAI", True)
    monkeypatch.setattr(vision_crop, "_PIL", True)
    monkeypatch.setattr(vision_crop, "get_gemini_key", lambda: "abc")
    monkeypatch.setattr(capture, "screen_size", lambda: (1920, 1080))
    img = PILImage.new("RGB", (100, 100), "white")
    monkeypatch.setattr(vision_crop, "capture_region", lambda box: (img, 400, 300))

    replies = iter(["garbage reply", "POINT 5 5"])

    class Models:
        def generate_content(self, model, contents=None):
            return SimpleNamespace(text=next(replies))

    class Gen:
        def __init__(self, api_key):
            self.models = Models()

    monkeypatch.setattr(vision_crop, "genai", SimpleNamespace(Client=Gen))
    assert vision_crop.vision_locate("save") == (405, 305)


# ---------------------------------------------------------------------------
# verify_after_click
# ---------------------------------------------------------------------------

from core.grounding import verify as verify_mod  # noqa: E402


def test_verify_skipped_for_non_a11y_ocr(monkeypatch):
    sleep = MagicMock()
    monkeypatch.setattr(verify_mod.time, "sleep", sleep)
    for source in (SOURCE_TEMPLATE, SOURCE_VISION, SOURCE_NONE):
        r = GroundingResult(found=True, source=source, x=1, y=2, label="Save")
        assert verify_after_click(r, delay_s=0.8) == ""
    sleep.assert_not_called()


def test_verify_a11y_still_present(monkeypatch):
    monkeypatch.setattr(verify_mod.time, "sleep", lambda s: None)
    monkeypatch.setattr(verify_mod, "a11y_available", lambda: True)
    monkeypatch.setattr(verify_mod, "find_node", lambda label: object())
    r = GroundingResult(found=True, source=SOURCE_A11Y, x=10, y=20, label="Save")
    advisory = verify_after_click(r)
    assert "element still present at (10, 20)" in advisory


def test_verify_a11y_gone(monkeypatch):
    monkeypatch.setattr(verify_mod.time, "sleep", lambda s: None)
    monkeypatch.setattr(verify_mod, "a11y_available", lambda: True)
    monkeypatch.setattr(verify_mod, "find_node", lambda label: None)
    r = GroundingResult(found=True, source=SOURCE_A11Y, x=10, y=20, label="Save")
    assert verify_after_click(r) == ""


def test_verify_ocr_still_present(monkeypatch):
    monkeypatch.setattr(verify_mod.time, "sleep", lambda s: None)
    monkeypatch.setattr(verify_mod, "screen_size", lambda: (1920, 1080))
    monkeypatch.setattr(verify_mod, "capture_region", lambda box: ("img", box[0], box[1]))
    monkeypatch.setattr(verify_mod, "ocr_words", lambda img: [WordBox("Save", 0, 0, 10, 10)])
    monkeypatch.setattr(verify_mod, "match_words", lambda words, target: words[0])
    r = GroundingResult(found=True, source=SOURCE_OCR, x=10, y=20, label="Save")
    assert "element still present at (10, 20)" in verify_after_click(r)


def test_verify_exception_returns_empty(monkeypatch):
    monkeypatch.setattr(verify_mod.time, "sleep", lambda s: (_ for _ in ()).throw(RuntimeError("boom")))
    r = GroundingResult(found=True, source=SOURCE_OCR, x=10, y=20, label="Save")
    assert verify_after_click(r) == ""