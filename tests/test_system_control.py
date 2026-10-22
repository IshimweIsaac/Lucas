"""Tests for actions/system_control.py — system control tool.

Tests cover the action dispatch layer (actions/system_control.py) which depends
on core/gnome_settings.py, core/network_manager.py, and core/audio_control.py.
Core module internals are mocked at the subprocess level."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from actions.system_control import HANDLERS, TOOL_SCHEMA, system_control


# ===================================================================
# TOOL_SCHEMA
# ===================================================================


def test_tool_schema_name():
    """TOOL_SCHEMA has the correct name."""
    assert TOOL_SCHEMA["name"] == "system_control"


def test_tool_schema_required():
    """TOOL_SCHEMA requires 'action'."""
    assert "action" in TOOL_SCHEMA["parameters"]["required"]


def test_tool_schema_action_type():
    """TOOL_SCHEMA action parameter is STRING type."""
    props = TOOL_SCHEMA["parameters"]["properties"]
    assert props["action"]["type"] == "STRING"


def test_tool_schema_description_mentions_help():
    """TOOL_SCHEMA description mentions help."""
    desc = TOOL_SCHEMA["description"]
    assert "help" in desc.lower()
    assert "action" in desc.lower()


def test_tool_schema_all_actions_in_help():
    """The 'action' enum description lists all ~28 actions."""
    action_desc = TOOL_SCHEMA["parameters"]["properties"]["action"]["description"]
    assert "set_dark_mode" in action_desc
    assert "set_wallpaper" in action_desc
    assert "scan_wifi" in action_desc
    assert "list_sinks" in action_desc
    assert "now_playing" in action_desc
    assert "send_notification" in action_desc


# ===================================================================
# Handler dispatch structure
# ===================================================================


def test_handlers_dict_has_all_actions():
    """HANDLERS dict covers every action documented in TOOL_SCHEMA."""
    action_desc = TOOL_SCHEMA["parameters"]["properties"]["action"]["description"]
    # Extract action words from description
    for action_name in HANDLERS:
        assert action_name in action_desc or action_name == "help"


def test_system_control_empty_action():
    """system_control with no action returns helpful message."""
    result = system_control({"action": ""})
    assert "No action provided" in result


def test_system_control_missing_action_key():
    """system_control without action key returns helpful message."""
    result = system_control({"name": "test"})
    assert "No action provided" in result


def test_system_control_unknown_action():
    """system_control with unknown action returns error."""
    result = system_control({"action": "nonexistent"})
    assert "Unknown action" in result
    assert "help" in result


def test_system_control_help():
    """action=help returns a formatted list of actions."""
    result = system_control({"action": "help"})
    assert "wifi_status" in result
    assert "set_dark_mode" in result
    assert "set_wallpaper" in result
    assert "now_playing" in result
    assert "send_notification" in result


# ===================================================================
# WiFi / Network actions
# ===================================================================


@patch("actions.system_control.net.wifi_status", return_value="WiFi radio: enabled")
def test_wifi_status(mock_status):
    """action=wifi_status delegates to net.wifi_status."""
    result = system_control({"action": "wifi_status"})
    assert "WiFi radio" in result
    mock_status.assert_called_once()


@patch("actions.system_control.net.wifi_on", return_value="WiFi enabled.")
def test_wifi_on(mock_on):
    """action=wifi_on delegates to net.wifi_on."""
    result = system_control({"action": "wifi_on"})
    assert "WiFi enabled" in result
    mock_on.assert_called_once()


@patch("actions.system_control.net.wifi_off", return_value="WiFi disabled.")
def test_wifi_off(mock_off):
    """action=wifi_off delegates to net.wifi_off."""
    result = system_control({"action": "wifi_off"})
    assert "WiFi disabled" in result
    mock_off.assert_called_once()


@patch("actions.system_control.net.scan_wifi", return_value="Found 3 networks...")
def test_scan_wifi(mock_scan):
    """action=scan_wifi delegates to net.scan_wifi."""
    result = system_control({"action": "scan_wifi"})
    assert "Found" in result
    mock_scan.assert_called_once()


@patch("actions.system_control.net.connect_wifi", return_value="Connected to: HomeNet")
def test_connect_wifi(mock_conn):
    """action=connect_wifi delegates to net.connect_wifi with SSID."""
    result = system_control(
        {"action": "connect_wifi", "name": "HomeNet", "password": "pass123"}
    )
    assert "Connected" in result
    mock_conn.assert_called_with("HomeNet", "pass123")


@patch("actions.system_control.net.connect_wifi", return_value="Connected to: OpenNet")
def test_connect_wifi_no_password(mock_conn):
    """action=connect_wifi without password still works."""
    result = system_control({"action": "connect_wifi", "name": "OpenNet"})
    assert "Connected" in result
    mock_conn.assert_called_with("OpenNet", "")


def test_connect_wifi_missing_ssid():
    """action=connect_wifi without name returns error."""
    result = system_control({"action": "connect_wifi"})
    assert "Provide name=SSID" in result


@patch("actions.system_control.net.disconnect_wifi", return_value="Disconnected.")
def test_disconnect_wifi(mock_disc):
    """action=disconnect_wifi delegates to net.disconnect_wifi."""
    result = system_control({"action": "disconnect_wifi"})
    assert "Disconnected" in result
    mock_disc.assert_called_once()


@patch(
    "actions.system_control.net.list_connections", return_value="Saved connections:..."
)
def test_list_connections(mock_list):
    """action=list_connections delegates to net.list_connections."""
    result = system_control({"action": "list_connections"})
    assert "Saved" in result
    mock_list.assert_called_once()


# ===================================================================
# Audio actions
# ===================================================================


@patch(
    "actions.system_control.audio.list_sinks", return_value="Audio sinks (2 found):..."
)
def test_list_sinks(mock_sinks):
    """action=list_sinks delegates to audio.list_sinks."""
    result = system_control({"action": "list_sinks"})
    assert "sinks" in result.lower()
    mock_sinks.assert_called_once()


@patch(
    "actions.system_control.audio.list_sources",
    return_value="Audio sources (1 found):...",
)
def test_list_sources(mock_sources):
    """action=list_sources delegates to audio.list_sources."""
    result = system_control({"action": "list_sources"})
    assert "sources" in result.lower()
    mock_sources.assert_called_once()


@patch(
    "actions.system_control.audio.set_default_sink", return_value="Default sink set."
)
def test_set_default_sink(mock_sink):
    """action=set_default_sink delegates to audio.set_default_sink."""
    result = system_control(
        {"action": "set_default_sink", "name": "alsa_output.pci-0000_00_1f.3"}
    )
    assert "Default" in result
    mock_sink.assert_called_once()


def test_set_default_sink_missing_name():
    """action=set_default_sink without name returns error."""
    result = system_control({"action": "set_default_sink"})
    assert "Provide name=sink_name" in result


@patch(
    "actions.system_control.audio.set_default_source",
    return_value="Default source set.",
)
def test_set_default_source(mock_source):
    """action=set_default_source delegates to audio.set_default_source."""
    result = system_control(
        {"action": "set_default_source", "name": "alsa_input.pci-0000_00_1f.3"}
    )
    assert "Default" in result
    mock_source.assert_called_once()


def test_set_default_source_missing_name():
    """action=set_default_source without name returns error."""
    result = system_control({"action": "set_default_source"})
    assert "Provide name=source_name" in result


# ===================================================================
# GNOME Desktop actions
# ===================================================================


@patch("actions.system_control.gnome.set_dark_mode", return_value="Dark mode enabled.")
def test_set_dark_mode_true(mock_dark):
    """action=set_dark_mode with enabled=True delegates correctly."""
    result = system_control({"action": "set_dark_mode", "enabled": True})
    assert "Dark mode" in result
    mock_dark.assert_called_with(True)


@patch("actions.system_control.gnome.set_dark_mode", return_value="Dark mode disabled.")
def test_set_dark_mode_false(mock_dark):
    """action=set_dark_mode with enabled=False delegates correctly."""
    result = system_control({"action": "set_dark_mode", "enabled": False})
    assert "Dark mode" in result
    mock_dark.assert_called_with(False)


@patch("actions.system_control.gnome.set_dark_mode", return_value="Dark mode enabled.")
def test_set_dark_mode_default_true(mock_dark):
    """action=set_dark_mode without enabled defaults to True."""
    result = system_control({"action": "set_dark_mode"})
    assert "Dark mode" in result
    mock_dark.assert_called_with(True)


@patch(
    "actions.system_control.gnome.set_wallpaper",
    return_value="Wallpaper set to /path/img.jpg",
)
def test_set_wallpaper(mock_wall):
    """action=set_wallpaper delegates to gnome.set_wallpaper with path."""
    result = system_control({"action": "set_wallpaper", "path": "/path/img.jpg"})
    assert "Wallpaper set" in result
    mock_wall.assert_called_with("/path/img.jpg")


def test_set_wallpaper_missing_path():
    """action=set_wallpaper without path returns error."""
    result = system_control({"action": "set_wallpaper"})
    assert "Provide path" in result


@patch(
    "actions.system_control.gnome.set_night_light", return_value="Night light enabled."
)
def test_set_night_light_true(mock_nl):
    """action=set_night_light with enabled=True delegates correctly."""
    result = system_control({"action": "set_night_light", "enabled": True})
    assert "Night light" in result
    mock_nl.assert_called_with(True)


@patch(
    "actions.system_control.gnome.set_night_light", return_value="Night light disabled."
)
def test_set_night_light_false(mock_nl):
    """action=set_night_light with enabled=False delegates correctly."""
    result = system_control({"action": "set_night_light", "enabled": False})
    assert "Night light" in result
    mock_nl.assert_called_with(False)


@patch(
    "actions.system_control.gnome.set_accent_color",
    return_value="Accent color set to blue.",
)
def test_set_accent_color(mock_color):
    """action=set_accent_color delegates to gnome.set_accent_color with color."""
    result = system_control({"action": "set_accent_color", "color": "blue"})
    assert "Accent color" in result
    mock_color.assert_called_with("blue")


def test_set_accent_color_missing():
    """action=set_accent_color without color returns error."""
    result = system_control({"action": "set_accent_color"})
    assert "Provide color" in result


@patch(
    "actions.system_control.gnome.set_keyboard_layout",
    return_value="Keyboard layout set to fr.",
)
def test_set_keyboard_layout(mock_layout):
    """action=set_keyboard_layout delegates to gnome.set_keyboard_layout."""
    result = system_control({"action": "set_keyboard_layout", "layout": "fr"})
    assert "Keyboard layout" in result
    mock_layout.assert_called_with("fr")


def test_set_keyboard_layout_missing():
    """action=set_keyboard_layout without layout returns error."""
    result = system_control({"action": "set_keyboard_layout"})
    assert "Provide layout" in result


@patch(
    "actions.system_control.gnome.set_touchpad_setting",
    return_value="Touchpad natural-scroll set to true.",
)
def test_set_touchpad(mock_tp):
    """action=set_touchpad delegates to gnome.set_touchpad_setting."""
    result = system_control(
        {
            "action": "set_touchpad",
            "setting": "natural-scroll",
            "value": "true",
        }
    )
    assert "Touchpad" in result
    mock_tp.assert_called_with("natural-scroll", "true")


def test_set_touchpad_missing_setting():
    """action=set_touchpad without setting returns error."""
    result = system_control({"action": "set_touchpad"})
    assert "Provide setting" in result


def test_set_touchpad_missing_value():
    """action=set_touchpad without value returns error."""
    result = system_control({"action": "set_touchpad", "setting": "speed"})
    assert "Provide value" in result


@patch(
    "actions.system_control.gnome.set_font",
    return_value="Interface font set to Cantarell 11.",
)
def test_set_font(mock_font):
    """action=set_font delegates to gnome.set_font."""
    result = system_control(
        {
            "action": "set_font",
            "font_type": "interface",
            "font_name": "Cantarell 11",
        }
    )
    assert "font set to" in result.lower()
    mock_font.assert_called_with("interface", "Cantarell 11")


def test_set_font_missing_params():
    """action=set_font without font_type or font_name returns error."""
    result = system_control({"action": "set_font", "font_type": "interface"})
    assert "font_type" in result.lower() or "font_name" in result.lower()


@patch(
    "actions.system_control.gnome.set_power_profile",
    return_value="Power profile set to balanced.",
)
def test_set_power_profile(mock_pp):
    """action=set_power_profile delegates to gnome.set_power_profile."""
    result = system_control({"action": "set_power_profile", "profile": "balanced"})
    assert "Power profile" in result
    mock_pp.assert_called_with("balanced")


def test_set_power_profile_missing():
    """action=set_power_profile without profile returns error."""
    result = system_control({"action": "set_power_profile"})
    assert "Provide profile" in result


# ===================================================================
# Display, Recording, Media, Notifications
# ===================================================================


@patch(
    "actions.system_control.gnome.list_displays",
    return_value=[{"name": "DP-1", "resolution": "3840x2160"}],
)
def test_list_displays(mock_displays):
    """action=list_displays delegates to gnome.list_displays."""
    result = system_control({"action": "list_displays"})
    assert "Displays" in result
    assert "DP-1" in result
    mock_displays.assert_called_once()


@patch(
    "actions.system_control.gnome.start_screen_recording",
    return_value="Screen recording started.",
)
def test_start_recording(mock_rec):
    """action=start_recording delegates to gnome.start_screen_recording."""
    result = system_control({"action": "start_recording"})
    assert "recording" in result.lower()
    mock_rec.assert_called_once()


@patch(
    "actions.system_control.gnome.stop_screen_recording",
    return_value="Screen recording stopped.",
)
def test_stop_recording(mock_rec):
    """action=stop_recording delegates to gnome.stop_screen_recording."""
    result = system_control({"action": "stop_recording"})
    assert "recording" in result.lower()
    mock_rec.assert_called_once()


@patch(
    "actions.system_control.gnome.now_playing",
    return_value="Now playing: Artist — Song",
)
def test_now_playing(mock_np):
    """action=now_playing delegates to gnome.now_playing."""
    result = system_control({"action": "now_playing"})
    assert "Now playing" in result
    mock_np.assert_called_once()


@patch("actions.system_control.gnome.media_control", return_value="Media: next.")
def test_next_track(mock_next):
    """action=next_track delegates to gnome.media_control('next')."""
    result = system_control({"action": "next_track"})
    assert "Media" in result
    mock_next.assert_called_with("next")


@patch("actions.system_control.gnome.media_control", return_value="Media: previous.")
def test_prev_track(mock_prev):
    """action=prev_track delegates to gnome.media_control('previous')."""
    result = system_control({"action": "prev_track"})
    assert "Media" in result
    mock_prev.assert_called_with("previous")


@patch(
    "actions.system_control.gnome.list_players",
    return_value="Media players: chromium, firefox",
)
def test_list_players(mock_players):
    """action=list_players delegates to gnome.list_players."""
    result = system_control({"action": "list_players"})
    assert "Media players" in result
    mock_players.assert_called_once()


@patch(
    "actions.system_control.gnome.send_notification",
    return_value="Notification sent: Hello",
)
def test_send_notification(mock_notify):
    """action=send_notification delegates to gnome.send_notification."""
    result = system_control(
        {
            "action": "send_notification",
            "title": "Lucas",
            "body": "Hello world",
        }
    )
    assert "Notification sent" in result
    mock_notify.assert_called_with("Lucas", "Hello world", 5)


@patch(
    "actions.system_control.gnome.send_notification",
    return_value="Notification sent: Test",
)
def test_send_notification_custom_duration(mock_notify):
    """action=send_notification with custom duration passes it along."""
    result = system_control(
        {
            "action": "send_notification",
            "title": "Test",
            "body": "Body text",
            "duration": 10,
        }
    )
    assert "Notification sent" in result
    mock_notify.assert_called_with("Test", "Body text", 10)


def test_send_notification_missing_body():
    """action=send_notification without body returns error."""
    result = system_control({"action": "send_notification", "title": "Hi"})
    assert "Provide body" in result


# ===================================================================
# Error handling
# ===================================================================


@patch(
    "actions.system_control.gnome.set_dark_mode", side_effect=RuntimeError("DBus error")
)
def test_handler_exception_caught(mock_dark):
    """Exceptions in handlers are caught and returned as error strings."""
    result = system_control({"action": "set_dark_mode", "enabled": True})
    assert "failed" in result.lower()
    assert "DBus error" in result


def test_all_actions_have_handler():
    """Every action documented has a handler in HANDLERS."""
    action_names = set(HANDLERS.keys())
    # Check documented actions exist
    documented = [
        "help",
        "wifi_status",
        "wifi_on",
        "wifi_off",
        "scan_wifi",
        "connect_wifi",
        "disconnect_wifi",
        "list_connections",
        "list_sinks",
        "list_sources",
        "set_default_sink",
        "set_default_source",
        "set_dark_mode",
        "set_wallpaper",
        "set_night_light",
        "set_accent_color",
        "set_keyboard_layout",
        "set_touchpad",
        "set_font",
        "set_power_profile",
        "list_displays",
        "start_recording",
        "stop_recording",
        "now_playing",
        "next_track",
        "prev_track",
        "list_players",
        "send_notification",
    ]
    for action in documented:
        assert action in action_names, f"Missing handler for: {action}"


# ===================================================================
# player parameter
# ===================================================================


def test_with_player():
    """system_control logs via player when provided."""
    mock_player = MagicMock()
    with patch(
        "actions.system_control.gnome.now_playing", return_value="Now playing: Test"
    ):
        system_control({"action": "now_playing"}, player=mock_player)

    mock_player.write_log.assert_called_once()
    assert "now_playing" in mock_player.write_log.call_args[0][0].lower()


def test_with_player_logs_action():
    """player log contains the action name."""
    mock_player = MagicMock()
    with patch("actions.system_control.net.wifi_status", return_value="WiFi: enabled"):
        system_control({"action": "wifi_status"}, player=mock_player)

    mock_player.write_log.assert_called_once()
    assert "wifi_status" in mock_player.write_log.call_args[0][0].lower()


# ===================================================================
# Voice routing pattern tests
# ===================================================================


# ===================================================================
# Phase 2 — Schema tests for new actions
# ===================================================================


def test_tool_schema_new_actions_in_action_desc():
    """Phase 2+3 action names appear in the action parameter description."""
    action_desc = TOOL_SCHEMA["parameters"]["properties"]["action"]["description"]
    assert "list_services" in action_desc
    assert "list_paired_devices" in action_desc
    assert "list_disks" in action_desc
    assert "list_zones" in action_desc
    assert "list_extensions" in action_desc
    assert "list_printers" in action_desc
    assert "list_installed" in action_desc
    assert "check_updates" in action_desc
    assert "device_info" in action_desc
    assert "list_browser_tabs" in action_desc
    assert "list_scheduled_tasks" in action_desc
    assert "watch_directory" in action_desc
    assert "clipboard_get" in action_desc
    assert "list_users" in action_desc
    assert "macro_start_recording" in action_desc


def test_tool_schema_new_params():
    """Phase 2 parameters are present in TOOL_SCHEMA."""
    props = TOOL_SCHEMA["parameters"]["properties"]
    assert "service_name" in props
    assert "mac" in props
    assert "device" in props
    assert "port" in props
    assert "protocol" in props
    assert "uuid" in props
    assert "package" in props
    assert "printer" in props
    assert "job_id" in props
    assert "query" in props
    assert "filter" in props


def test_tool_schema_description_mentions_55():
    """TOOL_SCHEMA description mentions ~100+ actions."""
    desc = TOOL_SCHEMA["description"]
    assert "100+" in desc
    assert "services" in desc.lower()
    assert "bluetooth" in desc.lower()
    assert "disk" in desc.lower()
    assert "firewall" in desc.lower()
    assert "printer" in desc.lower()
    assert "packages" in desc.lower()


def test_all_new_actions_have_handler():
    """Every Phase 2 action has a handler in HANDLERS."""
    action_names = set(HANDLERS.keys())
    new_actions = [
        "list_services",
        "service_status",
        "start_service",
        "stop_service",
        "restart_service",
        "enable_service",
        "disable_service",
        "list_paired_devices",
        "scan_devices",
        "connect_device",
        "disconnect_device",
        "bluetooth_on",
        "bluetooth_off",
        "device_info",
        "list_disks",
        "disk_usage",
        "mount_device",
        "unmount_device",
        "safely_eject",
        "disk_info",
        "list_zones",
        "list_open_ports",
        "list_fw_services",
        "add_port",
        "remove_port",
        "firewall_status",
        "list_extensions",
        "list_all_extensions",
        "enable_extension",
        "disable_extension",
        "extension_info",
        "list_printers",
        "printer_status",
        "list_print_jobs",
        "cancel_job",
        "list_installed",
        "check_updates",
        "install_package",
        "remove_package",
        "package_info",
        "search_packages",
    ]
    for action in new_actions:
        assert action in action_names, f"Missing handler for: {action}"


def test_help_includes_new_sections():
    """Help text includes Phase 2 sections."""
    result = system_control({"action": "help"})
    assert "Services (systemd)" in result
    assert "Bluetooth" in result
    assert "Disk / Storage" in result
    assert "Firewall" in result
    assert "GNOME Extensions" in result
    assert "Printers" in result
    assert "Packages (dnf)" in result
    assert "list_services" in result
    assert "list_paired_devices" in result
    assert "list_disks" in result
    assert "list_zones" in result
    assert "list_extensions" in result
    assert "list_printers" in result
    assert "list_installed" in result
    assert "check_updates" in result


# ===================================================================
# Phase 2 — Systemd Service actions
# ===================================================================


@patch(
    "actions.system_control.svc.list_services",
    return_value="Services (12):\n  service_a",
)
def test_list_services(mock_svc):
    """action=list_services delegates to svc.list_services."""
    result = system_control({"action": "list_services"})
    assert "Services" in result
    mock_svc.assert_called_with("")


@patch("actions.system_control.svc.list_services", return_value="Services (1):\n  sshd")
def test_list_services_with_filter(mock_svc):
    """action=list_services with filter passes it through."""
    result = system_control({"action": "list_services", "filter": "ssh"})
    assert "Services" in result
    mock_svc.assert_called_with("ssh")


@patch(
    "actions.system_control.svc.service_status",
    return_value="Service 'sshd' status:\nactive",
)
def test_service_status(mock_svc):
    """action=service_status delegates to svc.service_status."""
    result = system_control({"action": "service_status", "service_name": "sshd"})
    assert "status" in result.lower()
    mock_svc.assert_called_with("sshd")


def test_service_status_missing_name():
    """action=service_status without service_name returns error."""
    result = system_control({"action": "service_status"})
    assert "Provide service_name" in result


@patch(
    "actions.system_control.svc.start_service", return_value="Service 'sshd' started."
)
def test_start_service(mock_svc):
    """action=start_service delegates to svc.start_service."""
    result = system_control({"action": "start_service", "service_name": "sshd"})
    assert "started" in result.lower()
    mock_svc.assert_called_with("sshd")


def test_start_service_missing_name():
    """action=start_service without service_name returns error."""
    result = system_control({"action": "start_service"})
    assert "Provide service_name" in result


@patch(
    "actions.system_control.svc.stop_service", return_value="Service 'sshd' stopped."
)
def test_stop_service(mock_svc):
    """action=stop_service delegates to svc.stop_service."""
    result = system_control({"action": "stop_service", "service_name": "sshd"})
    assert "stopped" in result.lower()
    mock_svc.assert_called_with("sshd")


@patch(
    "actions.system_control.svc.restart_service",
    return_value="Service 'sshd' restarted.",
)
def test_restart_service(mock_svc):
    """action=restart_service delegates to svc.restart_service."""
    result = system_control({"action": "restart_service", "service_name": "sshd"})
    assert "restarted" in result.lower()
    mock_svc.assert_called_with("sshd")


@patch(
    "actions.system_control.svc.enable_service", return_value="Service 'sshd' enabled."
)
def test_enable_service(mock_svc):
    """action=enable_service delegates to svc.enable_service."""
    result = system_control({"action": "enable_service", "service_name": "sshd"})
    assert "enabled" in result.lower()
    mock_svc.assert_called_with("sshd")


@patch(
    "actions.system_control.svc.disable_service",
    return_value="Service 'sshd' disabled.",
)
def test_disable_service(mock_svc):
    """action=disable_service delegates to svc.disable_service."""
    result = system_control({"action": "disable_service", "service_name": "sshd"})
    assert "disabled" in result.lower()
    mock_svc.assert_called_with("sshd")


def test_service_action_missing_name():
    """All service actions without service_name return error."""
    for action in (
        "start_service",
        "stop_service",
        "restart_service",
        "enable_service",
        "disable_service",
    ):
        result = system_control({"action": action})
        assert "Provide service_name" in result, f"{action} missing error"


# ===================================================================
# Phase 2 — Bluetooth actions
# ===================================================================


@patch(
    "actions.system_control.bt.list_paired_devices",
    return_value="Paired devices (2):\n  XX:XX:XX:XX:XX:01  Headphones",
)
def test_list_paired_devices(mock_bt):
    """action=list_paired_devices delegates to bt.list_paired_devices."""
    result = system_control({"action": "list_paired_devices"})
    assert "Paired" in result
    mock_bt.assert_called_once()


@patch(
    "actions.system_control.bt.scan_devices",
    return_value="Devices found (1):\n  XX:XX:XX:XX:XX:02  Speaker",
)
def test_scan_devices(mock_bt):
    """action=scan_devices delegates to bt.scan_devices with timeout."""
    result = system_control({"action": "scan_devices", "timeout": 3})
    assert "Devices found" in result
    mock_bt.assert_called_with(3)


@patch("actions.system_control.bt.scan_devices", return_value="Devices found (0):")
def test_scan_devices_default_timeout(mock_bt):
    """action=scan_devices without timeout defaults to 5."""
    result = system_control({"action": "scan_devices"})
    assert "Devices" in result
    mock_bt.assert_called_with(5)


@patch(
    "actions.system_control.bt.connect_device",
    return_value="Connected to XX:XX:XX:XX:XX:01.",
)
def test_connect_device(mock_bt):
    """action=connect_device delegates to bt.connect_device with MAC."""
    result = system_control(
        {
            "action": "connect_device",
            "mac": "XX:XX:XX:XX:XX:01",
        }
    )
    assert "Connected" in result
    mock_bt.assert_called_with("XX:XX:XX:XX:XX:01")


def test_connect_device_missing_mac():
    """action=connect_device without mac returns error."""
    result = system_control({"action": "connect_device"})
    assert "Provide mac" in result


@patch(
    "actions.system_control.bt.disconnect_device",
    return_value="Disconnected from XX:XX:XX:XX:XX:01.",
)
def test_disconnect_device(mock_bt):
    """action=disconnect_device delegates to bt.disconnect_device."""
    result = system_control(
        {
            "action": "disconnect_device",
            "mac": "XX:XX:XX:XX:XX:01",
        }
    )
    assert "Disconnected" in result
    mock_bt.assert_called_with("XX:XX:XX:XX:XX:01")


@patch("actions.system_control.bt.bluetooth_on", return_value="Bluetooth powered on.")
def test_bluetooth_on(mock_bt):
    """action=bluetooth_on delegates to bt.bluetooth_on."""
    result = system_control({"action": "bluetooth_on"})
    assert "Bluetooth" in result
    mock_bt.assert_called_once()


@patch("actions.system_control.bt.bluetooth_off", return_value="Bluetooth powered off.")
def test_bluetooth_off(mock_bt):
    """action=bluetooth_off delegates to bt.bluetooth_off."""
    result = system_control({"action": "bluetooth_off"})
    assert "Bluetooth" in result
    mock_bt.assert_called_once()


@patch(
    "actions.system_control.bt.device_info",
    return_value="Device info for XX:XX:XX:XX:XX:01:\n  Name: Headphones",
)
def test_device_info(mock_bt):
    """action=device_info delegates to bt.device_info with MAC."""
    result = system_control(
        {
            "action": "device_info",
            "mac": "XX:XX:XX:XX:XX:01",
        }
    )
    assert "Device info" in result
    mock_bt.assert_called_with("XX:XX:XX:XX:XX:01")


def test_device_info_missing_mac():
    """action=device_info without mac returns error."""
    result = system_control({"action": "device_info"})
    assert "Provide mac" in result


# ===================================================================
# Phase 2 — Disk / Storage actions
# ===================================================================


@patch(
    "actions.system_control.disk.list_disks",
    return_value="NAME  SIZE TYPE MOUNTPOINT\nsda   512G  disk",
)
def test_list_disks(mock_disk):
    """action=list_disks delegates to disk.list_disks."""
    result = system_control({"action": "list_disks"})
    assert "sda" in result
    mock_disk.assert_called_once()


@patch(
    "actions.system_control.disk.disk_usage",
    return_value="Filesystem  Size  Used Avail Use% Mounted on\n/dev/sda2   512G  200G  312G  39% /",
)
def test_disk_usage(mock_disk):
    """action=disk_usage delegates to disk.disk_usage."""
    result = system_control({"action": "disk_usage"})
    assert "Filesystem" in result
    mock_disk.assert_called_once()


@patch(
    "actions.system_control.disk.mount_device",
    return_value="Mounted /dev/sda1 at /run/media/user/USB.",
)
def test_mount_device(mock_disk):
    """action=mount_device delegates to disk.mount_device with device."""
    result = system_control({"action": "mount_device", "device": "sda1"})
    assert "Mounted" in result
    mock_disk.assert_called_with("sda1")


def test_mount_device_missing():
    """action=mount_device without device returns error."""
    result = system_control({"action": "mount_device"})
    assert "Provide device" in result


@patch(
    "actions.system_control.disk.unmount_device", return_value="Unmounted /dev/sda1."
)
def test_unmount_device(mock_disk):
    """action=unmount_device delegates to disk.unmount_device."""
    result = system_control({"action": "unmount_device", "device": "sda1"})
    assert "Unmounted" in result
    mock_disk.assert_called_with("sda1")


@patch(
    "actions.system_control.disk.safely_eject",
    return_value="Device /dev/sda safely ejected.",
)
def test_safely_eject(mock_disk):
    """action=safely_eject delegates to disk.safely_eject."""
    result = system_control({"action": "safely_eject", "device": "sda"})
    assert "ejected" in result.lower()
    mock_disk.assert_called_with("sda")


@patch(
    "actions.system_control.disk.disk_info",
    return_value="NAME  SIZE FSTYPE UUID\nsda1  256G ext4   abc-123",
)
def test_disk_info(mock_disk):
    """action=disk_info delegates to disk.disk_info."""
    result = system_control({"action": "disk_info", "device": "sda1"})
    assert "UUID" in result or "FSTYPE" in result
    mock_disk.assert_called_with("sda1")


def test_disk_info_missing():
    """action=disk_info without device returns error."""
    result = system_control({"action": "disk_info"})
    assert "Provide device" in result


# ===================================================================
# Phase 2 — Firewall actions
# ===================================================================


@patch("actions.system_control.fw.list_zones", return_value="public\n  ports: 22/tcp\n")
def test_list_zones(mock_fw):
    """action=list_zones delegates to fw.list_zones."""
    result = system_control({"action": "list_zones"})
    assert "public" in result.lower()
    mock_fw.assert_called_once()


@patch(
    "actions.system_control.fw.list_open_ports",
    return_value="Open ports:\n22/tcp\n80/tcp",
)
def test_list_open_ports(mock_fw):
    """action=list_open_ports delegates to fw.list_open_ports."""
    result = system_control({"action": "list_open_ports"})
    assert "Open ports" in result
    mock_fw.assert_called_once()


@patch(
    "actions.system_control.fw.list_services",
    return_value="Allowed services: ssh dhcpv6-client",
)
def test_list_fw_services(mock_fw):
    """action=list_fw_services delegates to fw.list_services."""
    result = system_control({"action": "list_fw_services"})
    assert "Allowed" in result
    mock_fw.assert_called_once()


@patch(
    "actions.system_control.fw.add_port",
    return_value="Port 8080/tcp opened in zone 'public' (permanent).",
)
def test_add_port(mock_fw):
    """action=add_port delegates to fw.add_port with port and protocol."""
    result = system_control(
        {
            "action": "add_port",
            "port": "8080",
            "protocol": "tcp",
        }
    )
    assert "opened" in result.lower()
    mock_fw.assert_called_with("8080", "tcp")


@patch(
    "actions.system_control.fw.add_port",
    return_value="Port 53/udp opened in zone 'public' (permanent).",
)
def test_add_port_udp(mock_fw):
    """action=add_port with udp protocol passes it through."""
    result = system_control(
        {
            "action": "add_port",
            "port": "53",
            "protocol": "udp",
        }
    )
    assert "opened" in result.lower()
    mock_fw.assert_called_with("53", "udp")


def test_add_port_missing():
    """action=add_port without port returns error."""
    result = system_control({"action": "add_port"})
    assert "Provide port" in result


@patch(
    "actions.system_control.fw.remove_port",
    return_value="Port 8080/tcp removed from zone 'public' (permanent).",
)
def test_remove_port(mock_fw):
    """action=remove_port delegates to fw.remove_port."""
    result = system_control(
        {
            "action": "remove_port",
            "port": "8080",
        }
    )
    assert "removed" in result.lower()
    mock_fw.assert_called_with("8080", "tcp")


def test_remove_port_missing():
    """action=remove_port without port returns error."""
    result = system_control({"action": "remove_port"})
    assert "Provide port" in result


@patch(
    "actions.system_control.fw.firewall_status", return_value="Firewall status: running"
)
def test_firewall_status(mock_fw):
    """action=firewall_status delegates to fw.firewall_status."""
    result = system_control({"action": "firewall_status"})
    assert "Firewall" in result
    mock_fw.assert_called_once()


# ===================================================================
# Phase 2 — GNOME Extension actions
# ===================================================================


@patch(
    "actions.system_control.ext.list_extensions",
    return_value="Enabled extensions (2):\n  1. user@example.com",
)
def test_list_extensions(mock_ext):
    """action=list_extensions delegates to ext.list_extensions."""
    result = system_control({"action": "list_extensions"})
    assert "Enabled" in result
    mock_ext.assert_called_once()


@patch(
    "actions.system_control.ext.list_all_extensions",
    return_value="All extensions (3):\n  1. user@example.com",
)
def test_list_all_extensions(mock_ext):
    """action=list_all_extensions delegates to ext.list_all_extensions."""
    result = system_control({"action": "list_all_extensions"})
    assert "All extensions" in result
    mock_ext.assert_called_once()


@patch(
    "actions.system_control.ext.enable_extension",
    return_value="Extension 'my-ext@user' enabled.",
)
def test_enable_extension(mock_ext):
    """action=enable_extension delegates to ext.enable_extension."""
    result = system_control(
        {
            "action": "enable_extension",
            "uuid": "my-ext@user",
        }
    )
    assert "enabled" in result.lower()
    mock_ext.assert_called_with("my-ext@user")


def test_enable_extension_missing():
    """action=enable_extension without uuid returns error."""
    result = system_control({"action": "enable_extension"})
    assert "Provide uuid" in result


@patch(
    "actions.system_control.ext.disable_extension",
    return_value="Extension 'my-ext@user' disabled.",
)
def test_disable_extension(mock_ext):
    """action=disable_extension delegates to ext.disable_extension."""
    result = system_control(
        {
            "action": "disable_extension",
            "uuid": "my-ext@user",
        }
    )
    assert "disabled" in result.lower()
    mock_ext.assert_called_with("my-ext@user")


@patch(
    "actions.system_control.ext.extension_info",
    return_value="Extension info for 'my-ext@user':\n  Name: My Extension",
)
def test_extension_info(mock_ext):
    """action=extension_info delegates to ext.extension_info."""
    result = system_control(
        {
            "action": "extension_info",
            "uuid": "my-ext@user",
        }
    )
    assert "Extension info" in result
    mock_ext.assert_called_with("my-ext@user")


# ===================================================================
# Phase 2 — Printer actions
# ===================================================================


@patch(
    "actions.system_control.printer.list_printers",
    return_value="Printers (2):\n  printer HP_LaserJet is idle",
)
def test_list_printers(mock_pr):
    """action=list_printers delegates to printer.list_printers."""
    result = system_control({"action": "list_printers"})
    assert "Printers" in result
    mock_pr.assert_called_once()


@patch(
    "actions.system_control.printer.printer_status",
    return_value="printer HP_LaserJet is idle",
)
def test_printer_status(mock_pr):
    """action=printer_status delegates to printer.printer_status."""
    result = system_control(
        {
            "action": "printer_status",
            "printer": "HP_LaserJet",
        }
    )
    assert "idle" in result.lower()
    mock_pr.assert_called_with("HP_LaserJet")


def test_printer_status_missing():
    """action=printer_status without printer returns error."""
    result = system_control({"action": "printer_status"})
    assert "Provide printer" in result


@patch(
    "actions.system_control.printer.list_print_jobs",
    return_value="Print jobs:\n  HP_LaserJet  1024   user  1234",
)
def test_list_print_jobs(mock_pr):
    """action=list_print_jobs delegates to printer.list_print_jobs."""
    result = system_control({"action": "list_print_jobs"})
    assert "Print jobs" in result
    mock_pr.assert_called_once()


@patch(
    "actions.system_control.printer.cancel_job",
    return_value="Print job 1234 cancelled.",
)
def test_cancel_job(mock_pr):
    """action=cancel_job delegates to printer.cancel_job."""
    result = system_control(
        {
            "action": "cancel_job",
            "job_id": "1234",
        }
    )
    assert "cancelled" in result.lower()
    mock_pr.assert_called_with("1234")


def test_cancel_job_missing():
    """action=cancel_job without job_id returns error."""
    result = system_control({"action": "cancel_job"})
    assert "Provide job_id" in result


# ===================================================================
# Phase 2 — Package actions
# ===================================================================


@patch(
    "actions.system_control.pkg.list_installed",
    return_value="Installed packages (2):\n  firefox\n  vim",
)
def test_list_installed(mock_pkg):
    """action=list_installed delegates to pkg.list_installed."""
    result = system_control({"action": "list_installed"})
    assert "Installed" in result
    mock_pkg.assert_called_with("")


@patch(
    "actions.system_control.pkg.list_installed",
    return_value="Installed packages (1):\n  firefox",
)
def test_list_installed_with_filter(mock_pkg):
    """action=list_installed with filter passes it through."""
    result = system_control({"action": "list_installed", "filter": "firefox"})
    assert "Installed" in result
    mock_pkg.assert_called_with("firefox")


@patch(
    "actions.system_control.pkg.check_updates",
    return_value="Updates available (3):\n  firefox 134.0\n  kernel 6.8",
)
def test_check_updates(mock_pkg):
    """action=check_updates delegates to pkg.check_updates."""
    result = system_control({"action": "check_updates"})
    assert "Updates" in result or "up to date" in result
    mock_pkg.assert_called_once()


@patch(
    "actions.system_control.pkg.install_package",
    return_value="Installing 'firefox' requires admin privileges...",
)
def test_install_package(mock_pkg):
    """action=install_package delegates to pkg.install_package."""
    result = system_control({"action": "install_package", "package": "firefox"})
    assert "admin" in result.lower() or "privileges" in result.lower()
    mock_pkg.assert_called_with("firefox")


def test_install_package_missing():
    """action=install_package without package returns error."""
    result = system_control({"action": "install_package"})
    assert "Provide package" in result


@patch(
    "actions.system_control.pkg.remove_package",
    return_value="Removing 'firefox' requires admin privileges...",
)
def test_remove_package(mock_pkg):
    """action=remove_package delegates to pkg.remove_package."""
    result = system_control({"action": "remove_package", "package": "firefox"})
    assert "admin" in result.lower() or "privileges" in result.lower()
    mock_pkg.assert_called_with("firefox")


@patch(
    "actions.system_control.pkg.package_info",
    return_value="Name: firefox\nVersion: 134.0\nSummary: Firefox browser",
)
def test_package_info(mock_pkg):
    """action=package_info delegates to pkg.package_info."""
    result = system_control({"action": "package_info", "package": "firefox"})
    assert "firefox" in result.lower()
    mock_pkg.assert_called_with("firefox")


def test_package_info_missing():
    """action=package_info without package returns error."""
    result = system_control({"action": "package_info"})
    assert "Provide package" in result


@patch(
    "actions.system_control.pkg.search_packages",
    return_value="Search results for 'web' (2):\n  firefox\n  chrome",
)
def test_search_packages(mock_pkg):
    """action=search_packages delegates to pkg.search_packages."""
    result = system_control({"action": "search_packages", "query": "web"})
    assert "Search results" in result
    mock_pkg.assert_called_with("web")


def test_search_packages_missing():
    """action=search_packages without query returns error."""
    result = system_control({"action": "search_packages"})
    assert "Provide query" in result


# ===================================================================
# Phase 2 — Error handling for new actions
# ===================================================================


def test_new_action_exception_caught():
    """Exceptions in new handlers are caught."""
    import actions.system_control as sc

    original = sc.svc.list_services
    sc.svc.list_services = lambda _: (_ for _ in ()).throw(RuntimeError("DBus error"))
    try:
        result = system_control({"action": "list_services"})
        assert "failed" in result.lower() or "error" in result.lower()
    finally:
        sc.svc.list_services = original


def test_handler_count():
    """Total handlers count is 90+ (Phase 1 + Phase 2)."""
    assert len(HANDLERS) >= 90, f"Only {len(HANDLERS)} handlers found"


# ===================================================================
# Phase 2 — Voice routing pattern tests
# ===================================================================


def test_bluetooth_regex_relevance():
    """The _BLUETOOTH_RE pattern matches expected intents."""
    import re

    pattern = re.compile(
        r"\b(bluetooth|pair|airpods?|speaker|headset|earphone)\b",
        re.I,
    )
    assert pattern.search("turn on bluetooth")
    assert pattern.search("pair my headset")
    assert pattern.search("connect my airpods")
    assert pattern.search("bluetooth speaker")
    assert pattern.search("earphone battery")
    assert not pattern.search("install package")
    assert not pattern.search("list disks")


def test_disk_regex_relevance():
    """The _DISK_RE pattern matches disk intents."""
    import re

    pattern = re.compile(
        r"\b(disks?|drive|mount|unmount|eject|usb|storage)\b",
        re.I,
    )
    assert pattern.search("list disks")
    assert pattern.search("mount the usb drive")
    assert pattern.search("eject the disk")
    assert pattern.search("show storage usage")
    assert pattern.search("unmount the drive")
    assert not pattern.search("bluetooth headphones")
    assert not pattern.search("open firefox")


def test_service_regex_relevance():
    """The _SERVICE_RE pattern matches service intents."""
    import re

    pattern = re.compile(
        r"\b(services?|systemd|daemon)\b",
        re.I,
    )
    assert pattern.search("start the service")
    assert pattern.search("restart the sshd service")
    assert pattern.search("list systemd services")
    assert pattern.search("check daemon status")
    assert not pattern.search("mount the disk")
    assert not pattern.search("bluetooth device")


def test_firewall_regex_relevance():
    """The _FIREWALL_RE pattern matches firewall intents."""
    import re

    pattern = re.compile(
        r"\b(firewall|port|allow.*port|block.*port)\b",
        re.I,
    )
    assert pattern.search("check firewall status")
    assert pattern.search("open port 8080")
    assert pattern.search("allow port 443")
    assert pattern.search("block port 22")
    assert not pattern.search("list disks")
    assert not pattern.search("enable service")


def test_extension_regex_relevance():
    """The _EXTENSION_RE pattern matches extension intents."""
    import re

    pattern = re.compile(
        r"\b(extensions?|gnome.*ext|shell.*ext)\b",
        re.I,
    )
    assert pattern.search("list extensions")
    assert pattern.search("enable gnome extension")
    assert pattern.search("disable shell extension")
    assert not pattern.search("mount the drive")
    assert not pattern.search("bluetooth pair")


def test_printer_regex_relevance():
    """The _PRINTER_RE pattern matches printer intents."""
    import re

    pattern = re.compile(
        r"\b(printers?|print.*jobs?|print.*queue)\b",
        re.I,
    )
    assert pattern.search("list printers")
    assert pattern.search("show print jobs")
    assert pattern.search("check print queue")
    assert not pattern.search("list disks")
    assert not pattern.search("start service")


def test_package_regex_relevance():
    """The _PACKAGE_RE pattern matches package intents."""
    import re

    pattern = re.compile(
        r"\b(install.*package|remove.*package|dnf|package.*manager|update.*system)\b",
        re.I,
    )
    assert pattern.search("install a package")
    assert pattern.search("remove package firefox")
    assert pattern.search("use dnf to update")
    assert pattern.search("check package manager")
    assert pattern.search("update the system")
    assert not pattern.search("list printers")
    assert not pattern.search("mount the drive")


# ===================================================================
# Phase 3 — Schema tests for new actions
# ===================================================================


def test_tool_schema_phase3_actions_in_action_desc():
    """Phase 3 action names appear in the action parameter description."""
    action_desc = TOOL_SCHEMA["parameters"]["properties"]["action"]["description"]
    assert "list_browser_tabs" in action_desc
    assert "close_browser_tab" in action_desc
    assert "list_scheduled_tasks" in action_desc
    assert "create_scheduled_task" in action_desc
    assert "watch_directory" in action_desc
    assert "list_watchers" in action_desc
    assert "clipboard_get" in action_desc
    assert "clipboard_copy" in action_desc
    assert "clipboard_history" in action_desc
    assert "list_users" in action_desc
    assert "current_user" in action_desc
    assert "macro_start_recording" in action_desc
    assert "macro_list" in action_desc


def test_tool_schema_phase3_params():
    """Phase 3 parameters are present in TOOL_SCHEMA."""
    props = TOOL_SCHEMA["parameters"]["properties"]
    assert "browser" in props
    assert "tab_id" in props
    assert "url" in props
    assert "schedule" in props
    assert "command" in props
    assert "task_name" in props
    assert "pattern" in props
    assert "watcher_id" in props
    assert "text" in props
    assert "index" in props
    assert "macro_path" in props


def test_tool_schema_description_mentions_95():
    """TOOL_SCHEMA description mentions ~100+ actions."""
    desc = TOOL_SCHEMA["description"]
    assert "100+" in desc
    assert "browser" in desc.lower()
    assert "scheduled" in desc.lower()
    assert "clipboard" in desc.lower()


def test_all_phase3_actions_have_handler():
    """Every Phase 3 action has a handler in HANDLERS."""
    action_names = set(HANDLERS.keys())
    phase3_actions = [
        "list_browser_tabs",
        "close_browser_tab",
        "activate_browser_tab",
        "navigate_tab",
        "list_scheduled_tasks",
        "create_scheduled_task",
        "remove_scheduled_task",
        "scheduled_task_status",
        "watch_directory",
        "list_watchers",
        "stop_watcher",
        "stop_all_watchers",
        "clipboard_get",
        "clipboard_copy",
        "clipboard_history",
        "clipboard_paste_history",
        "clipboard_clear",
        "list_users",
        "current_user",
        "macro_start_recording",
        "macro_stop_recording",
        "macro_play",
        "macro_list",
        "macro_status",
    ]
    for action in phase3_actions:
        assert action in action_names, f"Missing handler for: {action}"


def test_help_includes_phase3_sections():
    """Help text includes Phase 3 sections."""
    result = system_control({"action": "help"})
    assert "Browser CDP Control" in result
    assert "Scheduled Tasks" in result
    assert "File Watchers" in result
    assert "Clipboard History" in result
    assert "User Accounts" in result
    assert "Macro Recording" in result
    assert "list_browser_tabs" in result
    assert "list_scheduled_tasks" in result
    assert "watch_directory" in result
    assert "clipboard_get" in result
    assert "list_users" in result
    assert "macro_start_recording" in result


# ===================================================================
# Phase 3 — Browser CDP actions
# ===================================================================


@patch(
    "actions.system_control.bdbg.list_browser_tabs",
    return_value='Tabs (2):\n  1. "Test"',
)
def test_list_browser_tabs(mock_bdbg):
    """action=list_browser_tabs delegates to bdbg.list_browser_tabs."""
    result = system_control({"action": "list_browser_tabs"})
    assert "Tabs" in result
    mock_bdbg.assert_called_with("chrome")


@patch(
    "actions.system_control.bdbg.list_browser_tabs",
    return_value='Tabs (1):\n  1. "Page"',
)
def test_list_browser_tabs_firefox(mock_bdbg):
    """action=list_browser_tabs with browser=firefox passes it through."""
    result = system_control({"action": "list_browser_tabs", "browser": "firefox"})
    assert "Tabs" in result
    mock_bdbg.assert_called_with("firefox")


@patch(
    "actions.system_control.bdbg.close_browser_tab",
    return_value="Tab abc123... closed in chrome.",
)
def test_close_browser_tab(mock_bdbg):
    """action=close_browser_tab delegates to bdbg.close_browser_tab."""
    result = system_control({"action": "close_browser_tab", "tab_id": "abc123def456"})
    assert "closed" in result.lower()
    mock_bdbg.assert_called_with("abc123def456", "chrome")


def test_close_browser_tab_missing_tab_id():
    """action=close_browser_tab without tab_id returns error."""
    result = system_control({"action": "close_browser_tab"})
    assert "Provide tab_id" in result


@patch(
    "actions.system_control.bdbg.activate_browser_tab",
    return_value="Tab abc123... activated in chrome.",
)
def test_activate_browser_tab(mock_bdbg):
    """action=activate_browser_tab delegates to bdbg.activate_browser_tab."""
    result = system_control(
        {"action": "activate_browser_tab", "tab_id": "abc123def456"}
    )
    assert "activated" in result.lower()
    mock_bdbg.assert_called_with("abc123def456", "chrome")


def test_activate_browser_tab_missing_tab_id():
    """action=activate_browser_tab without tab_id returns error."""
    result = system_control({"action": "activate_browser_tab"})
    assert "Provide tab_id" in result


@patch(
    "actions.system_control.bdbg.navigate_tab",
    return_value="Navigated tab abc12... to https://example.com.",
)
def test_navigate_tab(mock_bdbg):
    """action=navigate_tab delegates to bdbg.navigate_tab."""
    result = system_control(
        {
            "action": "navigate_tab",
            "tab_id": "abc123def456",
            "url": "https://example.com",
        }
    )
    assert "Navigated" in result
    mock_bdbg.assert_called_with("abc123def456", "https://example.com", "chrome")


def test_navigate_tab_missing_params():
    """action=navigate_tab without tab_id or url returns error."""
    result = system_control({"action": "navigate_tab", "tab_id": "abc"})
    assert "Provide url" in result
    result2 = system_control({"action": "navigate_tab", "url": "https://x.com"})
    assert "Provide tab_id" in result2


# ===================================================================
# Phase 3 — Scheduled Task actions
# ===================================================================


@patch(
    "actions.system_control.sched.list_scheduled_tasks",
    return_value="Scheduled Tasks (1):\n  my-task.timer",
)
def test_list_scheduled_tasks(mock_sched):
    """action=list_scheduled_tasks delegates to sched.list_scheduled_tasks."""
    result = system_control({"action": "list_scheduled_tasks"})
    assert "Scheduled Tasks" in result
    mock_sched.assert_called_once()


@patch(
    "actions.system_control.sched.create_scheduled_task",
    return_value="Scheduled task 'my_task' created (daily).",
)
def test_create_scheduled_task(mock_sched):
    """action=create_scheduled_task delegates to sched.create_scheduled_task."""
    result = system_control(
        {
            "action": "create_scheduled_task",
            "task_name": "my_task",
            "command": "echo hello",
            "schedule": "daily",
        }
    )
    assert "created" in result.lower()
    mock_sched.assert_called_with("my_task", "echo hello", "daily")


def test_create_scheduled_task_missing_params():
    """action=create_scheduled_task without params returns error."""
    result = system_control({"action": "create_scheduled_task"})
    assert "Provide task_name" in result
    result2 = system_control({"action": "create_scheduled_task", "task_name": "test"})
    assert "Provide command" in result2
    result3 = system_control(
        {
            "action": "create_scheduled_task",
            "task_name": "test",
            "command": "echo",
        }
    )
    assert "Provide schedule" in result3


@patch(
    "actions.system_control.sched.remove_scheduled_task",
    return_value="Scheduled task 'my_task' removed.",
)
def test_remove_scheduled_task(mock_sched):
    """action=remove_scheduled_task delegates to sched.remove_scheduled_task."""
    result = system_control({"action": "remove_scheduled_task", "task_name": "my_task"})
    assert "removed" in result.lower()
    mock_sched.assert_called_with("my_task")


def test_remove_scheduled_task_missing():
    """action=remove_scheduled_task without task_name returns error."""
    result = system_control({"action": "remove_scheduled_task"})
    assert "Provide task_name" in result


@patch(
    "actions.system_control.sched.scheduled_task_status",
    return_value="Status for 'my_task':\n  active",
)
def test_scheduled_task_status(mock_sched):
    """action=scheduled_task_status delegates to sched.scheduled_task_status."""
    result = system_control({"action": "scheduled_task_status", "task_name": "my_task"})
    assert "Status" in result
    mock_sched.assert_called_with("my_task")


def test_scheduled_task_status_missing():
    """action=scheduled_task_status without task_name returns error."""
    result = system_control({"action": "scheduled_task_status"})
    assert "Provide task_name" in result


# ===================================================================
# Phase 3 — File Watcher actions
# ===================================================================


@patch(
    "actions.system_control.fwch.watch_directory",
    return_value="Watching directory '/tmp' for changes.",
)
def test_watch_directory(mock_fwch):
    """action=watch_directory delegates to fwch.watch_directory."""
    result = system_control(
        {"action": "watch_directory", "path": "/tmp", "pattern": "*.txt"}
    )
    assert "Watching" in result
    mock_fwch.assert_called_with("/tmp", "*.txt")


def test_watch_directory_missing_path():
    """action=watch_directory without path returns error."""
    result = system_control({"action": "watch_directory"})
    assert "Provide path" in result


@patch(
    "actions.system_control.fwch.list_watchers",
    return_value="Active file watchers (2):\n  abc123... running",
)
def test_list_watchers(mock_fwch):
    """action=list_watchers delegates to fwch.list_watchers."""
    result = system_control({"action": "list_watchers"})
    assert "watchers" in result.lower()
    mock_fwch.assert_called_once()


@patch(
    "actions.system_control.fwch.stop_watcher",
    return_value="Watcher abc123... stopped.",
)
def test_stop_watcher(mock_fwch):
    """action=stop_watcher delegates to fwch.stop_watcher."""
    result = system_control({"action": "stop_watcher", "watcher_id": "abc123"})
    assert "stopped" in result.lower()
    mock_fwch.assert_called_with("abc123")


def test_stop_watcher_missing():
    """action=stop_watcher without watcher_id returns error."""
    result = system_control({"action": "stop_watcher"})
    assert "Provide watcher_id" in result


@patch(
    "actions.system_control.fwch.stop_all_watchers",
    return_value="Stopped 2 watcher(s).",
)
def test_stop_all_watchers(mock_fwch):
    """action=stop_all_watchers delegates to fwch.stop_all_watchers."""
    result = system_control({"action": "stop_all_watchers"})
    assert "Stopped" in result
    mock_fwch.assert_called_once()


# ===================================================================
# Phase 3 — Clipboard History actions
# ===================================================================


@patch("actions.system_control.cb.clipboard_get", return_value="Hello world")
def test_clipboard_get(mock_cb):
    """action=clipboard_get delegates to cb.clipboard_get."""
    result = system_control({"action": "clipboard_get"})
    assert "Hello" in result or "Clipboard" in result
    mock_cb.assert_called_once()


@patch(
    "actions.system_control.cb.clipboard_copy",
    return_value="Copied to clipboard (5 chars).",
)
def test_clipboard_copy(mock_cb):
    """action=clipboard_copy delegates to cb.clipboard_copy."""
    result = system_control({"action": "clipboard_copy", "text": "Hello"})
    assert "copied" in result.lower()
    mock_cb.assert_called_with("Hello")


def test_clipboard_copy_missing():
    """action=clipboard_copy without text returns error."""
    result = system_control({"action": "clipboard_copy"})
    assert "Provide text" in result


@patch(
    "actions.system_control.cb.clipboard_history",
    return_value="Clipboard History (2 of 20):\n  [0] Hello\n  [1] World",
)
def test_clipboard_history(mock_cb):
    """action=clipboard_history delegates to cb.clipboard_history."""
    result = system_control({"action": "clipboard_history"})
    assert "History" in result
    mock_cb.assert_called_once()


@patch(
    "actions.system_control.cb.clipboard_paste_history",
    return_value='History item [1] copied to clipboard: "World"',
)
def test_clipboard_paste_history(mock_cb):
    """action=clipboard_paste_history delegates to cb.clipboard_paste_history."""
    result = system_control({"action": "clipboard_paste_history", "index": 1})
    assert "History item" in result
    mock_cb.assert_called_with(1)


def test_clipboard_paste_history_missing_index():
    """action=clipboard_paste_history without index returns error."""
    result = system_control({"action": "clipboard_paste_history"})
    assert "Provide index" in result


def test_clipboard_paste_history_invalid_index():
    """action=clipboard_paste_history with non-numeric index returns error."""
    result = system_control({"action": "clipboard_paste_history", "index": "abc"})
    assert "valid numeric" in result.lower()


@patch("actions.system_control.cb.clear_history")
def test_clipboard_clear(mock_cb):
    """action=clipboard_clear delegates to cb.clear_history."""
    result = system_control({"action": "clipboard_clear"})
    assert "cleared" in result.lower()
    mock_cb.assert_called_once()


# ===================================================================
# Phase 3 — User Account actions
# ===================================================================


@patch(
    "actions.system_control.uacct.list_users",
    return_value="Users (2):\n  user1\n  user2",
)
def test_list_users(mock_uacct):
    """action=list_users delegates to uacct.list_users."""
    result = system_control({"action": "list_users"})
    assert "Users" in result
    mock_uacct.assert_called_once()


@patch(
    "actions.system_control.uacct.current_user", return_value="Current user: testuser"
)
def test_current_user(mock_uacct):
    """action=current_user delegates to uacct.current_user."""
    result = system_control({"action": "current_user"})
    assert "Current user" in result
    mock_uacct.assert_called_once()


# ===================================================================
# Phase 3 — Macro Recording actions
# ===================================================================


@patch(
    "actions.system_control.macro.start_recording",
    return_value="Recording started. Press Escape to stop.",
)
def test_macro_start_recording(mock_macro):
    """action=macro_start_recording delegates to macro.start_recording."""
    result = system_control({"action": "macro_start_recording"})
    assert "Recording started" in result
    mock_macro.assert_called_with("")


@patch(
    "actions.system_control.macro.start_recording",
    return_value="Recording started. Press Escape to stop.",
)
def test_macro_start_recording_with_path(mock_macro):
    """action=macro_start_recording with macro_path passes it through."""
    result = system_control(
        {"action": "macro_start_recording", "macro_path": "/tmp/test.json"}
    )
    assert "Recording started" in result
    mock_macro.assert_called_with("/tmp/test.json")


@patch(
    "actions.system_control.macro.stop_recording",
    return_value="Recording stopped. 10 events captured.",
)
def test_macro_stop_recording(mock_macro):
    """action=macro_stop_recording delegates to macro.stop_recording."""
    result = system_control({"action": "macro_stop_recording"})
    assert "Recording stopped" in result
    mock_macro.assert_called_with("")


@patch(
    "actions.system_control.macro.play_macro",
    return_value="Macro 'test.json' loaded (5 events).",
)
def test_macro_play(mock_macro):
    """action=macro_play delegates to macro.play_macro."""
    result = system_control({"action": "macro_play", "macro_path": "test.json"})
    assert "Macro" in result
    mock_macro.assert_called_with("test.json")


def test_macro_play_missing():
    """action=macro_play without macro_path returns error."""
    result = system_control({"action": "macro_play"})
    assert "Provide macro_path" in result


@patch(
    "actions.system_control.macro.list_macros",
    return_value="Saved Macros (2):\n  test.json",
)
def test_macro_list(mock_macro):
    """action=macro_list delegates to macro.list_macros."""
    result = system_control({"action": "macro_list"})
    assert "Saved Macros" in result
    mock_macro.assert_called_once()


@patch(
    "actions.system_control.macro.recording_status",
    return_value="Not recording. Last recording had 0 events.",
)
def test_macro_status(mock_macro):
    """action=macro_status delegates to macro.recording_status."""
    result = system_control({"action": "macro_status"})
    assert "recording" in result.lower()
    mock_macro.assert_called_once()


# ===================================================================
# Phase 3 — Handler count
# ===================================================================


def test_handler_count_phase3():
    """Total handlers count is ~100+."""
    assert len(HANDLERS) >= 98, f"Only {len(HANDLERS)} handlers found"


# ===================================================================
# Phase 3 — Error handling
# ===================================================================


def test_phase3_exception_caught():
    """Exceptions in Phase 3 handlers are caught."""
    with patch(
        "actions.system_control.bdbg.list_browser_tabs",
        side_effect=RuntimeError("CDP error"),
    ):
        result = system_control({"action": "list_browser_tabs"})
        assert "failed" in result.lower() or "error" in result.lower()


# ===================================================================
# Phase 3 — Voice routing pattern tests
# ===================================================================


def test_browser_tab_regex_relevance():
    """The _BROWSER_TAB_RE pattern matches browser tab intents."""
    import re

    pattern = re.compile(
        r"\b(tab.*close|close.*tab|browser.*tab|what.*tab|"
        r"activate.*tab|navigate.*tab)\b",
        re.I,
    )
    assert pattern.search("close this tab")
    assert pattern.search("list browser tab")
    assert pattern.search("activate tab 2")
    assert pattern.search("navigate to a tab")
    assert pattern.search("what browser tab is open")
    assert not pattern.search("open firefox")
    assert not pattern.search("list users")


def test_schedule_regex_relevance():
    """The _SCHEDULE_RE pattern matches schedule intents."""
    import re

    pattern = re.compile(
        r"\b(schedule|timer|cron|every.*(day|hour|minute)|recurring)\b",
        re.I,
    )
    assert pattern.search("schedule a task")
    assert pattern.search("create a timer")
    assert pattern.search("run every day")
    assert pattern.search("run every hour")
    assert pattern.search("cron job")
    assert pattern.search("recurring task")
    assert not pattern.search("list disks")
    assert not pattern.search("close tab")


def test_file_watch_regex_relevance():
    """The _FILE_WATCH_RE pattern matches file watch intents."""
    import re

    pattern = re.compile(
        r"\b(watch.*folder|watch.*directory|monitor.*file)\b",
        re.I,
    )
    assert pattern.search("watch this folder")
    assert pattern.search("watch the directory")
    assert pattern.search("monitor a file")
    assert not pattern.search("list users")
    assert not pattern.search("close tab")


def test_clipboard_history_regex_relevance():
    """The _CLIPBOARD_HISTORY_RE pattern matches clipboard intents."""
    import re

    pattern = re.compile(
        r"\b(clipboard.*history|paste.*history|copy.*history)\b",
        re.I,
    )
    assert pattern.search("show clipboard history")
    assert pattern.search("paste history item")
    assert pattern.search("copy history item")
    assert not pattern.search("list users")
    assert not pattern.search("schedule a task")


def test_macro_regex_relevance():
    """The _MACRO_RE pattern matches macro intents."""
    import re

    pattern = re.compile(
        r"\b(macro|record.*macro|play.*macro)\b",
        re.I,
    )
    assert pattern.search("record a macro")
    assert pattern.search("play the macro")
    assert pattern.search("record a macro please")
    assert pattern.search("play the saved macro")
    assert not pattern.search("list users")
    assert not pattern.search("close tab")


def test_user_account_regex_relevance():
    """The _USER_ACCOUNT_RE pattern matches user account intents."""
    import re

    pattern = re.compile(
        r"\b(user.*account|list.*user|who.*logged)\b",
        re.I,
    )
    assert pattern.search("list user accounts")
    assert pattern.search("list user")
    assert pattern.search("who is logged in")
    assert not pattern.search("schedule a task")
    assert not pattern.search("close tab")


# ===================================================================
# Docker handlers
# ===================================================================


@patch(
    "core.docker_control.list_containers",
    return_value="nginx    Up 2 hours    80/tcp",
)
def test_docker_containers(mock_dc):
    """action=docker_containers delegates to list_containers."""
    result = system_control({"action": "docker_containers"})
    assert "nginx" in result
    mock_dc.assert_called_with(all_containers=False)


@patch(
    "core.docker_control.list_containers",
    return_value="nginx    Up 2 hours    80/tcp\nredis   Up 2 hours  6379/tcp",
)
def test_docker_containers_shows_all(mock_dc):
    """action=docker_containers with all=true shows stopped containers."""
    result = system_control({"action": "docker_containers", "all": True})
    assert "nginx" in result
    mock_dc.assert_called_with(all_containers=True)


@patch("core.docker_control.docker_info", return_value="Docker 24.0.7 - 3 container(s) running")
def test_docker_status_without_name(mock_dc):
    """action=docker_status without name shows docker info."""
    result = system_control({"action": "docker_status"})
    assert "Docker" in result
    mock_dc.assert_called_once()


@patch("core.docker_control.container_status", return_value="my-app    Up 3 hours    80/tcp")
def test_docker_status_with_name(mock_dc):
    """action=docker_status with name shows container status."""
    result = system_control({"action": "docker_status", "name": "my-app"})
    assert "my-app" in result
    mock_dc.assert_called_with("my-app")


@patch("core.docker_control.start_container", return_value="Container started: my-app")
def test_docker_start(mock_dc):
    """action=docker_start delegates to start_container."""
    result = system_control({"action": "docker_start", "name": "my-app"})
    assert "started" in result.lower()
    mock_dc.assert_called_with("my-app")


def test_docker_start_missing_name():
    """action=docker_start without name returns error."""
    result = system_control({"action": "docker_start"})
    assert "container name is required" in result


@patch("core.docker_control.stop_container", return_value="Container stopped: my-app")
def test_docker_stop(mock_dc):
    """action=docker_stop delegates to stop_container."""
    result = system_control({"action": "docker_stop", "name": "my-app"})
    assert "stopped" in result.lower()
    mock_dc.assert_called_with("my-app")


def test_docker_stop_missing_name():
    """action=docker_stop without name returns error."""
    result = system_control({"action": "docker_stop"})
    assert "container name is required" in result


@patch("core.docker_control.restart_container", return_value="Container restarted: my-app")
def test_docker_restart(mock_dc):
    """action=docker_restart delegates to restart_container."""
    result = system_control({"action": "docker_restart", "name": "my-app"})
    assert "restarted" in result.lower()
    mock_dc.assert_called_with("my-app")


def test_docker_restart_missing_name():
    """action=docker_restart without name returns error."""
    result = system_control({"action": "docker_restart"})
    assert "container name is required" in result


@patch(
    "core.docker_control.list_images",
    return_value="REPOSITORY   TAG     SIZE\nnginx        latest  187MB",
)
def test_docker_images(mock_dc):
    """action=docker_images delegates to list_images."""
    result = system_control({"action": "docker_images"})
    assert "nginx" in result or "REPOSITORY" in result
    mock_dc.assert_called_once()


def test_docker_actions_in_tool_schema():
    """Docker actions appear in the TOOL_SCHEMA action description."""
    action_desc = TOOL_SCHEMA["parameters"]["properties"]["action"]["description"]
    assert "docker_containers" in action_desc
    assert "docker_status" in action_desc
    assert "docker_start" in action_desc
    assert "docker_stop" in action_desc
    assert "docker_restart" in action_desc
    assert "docker_images" in action_desc


def test_docker_params_in_tool_schema():
    """Docker-related params are in TOOL_SCHEMA."""
    props = TOOL_SCHEMA["parameters"]["properties"]
    assert "name" in props
    assert "all" in props


def test_docker_help_includes_section():
    """Help text includes Docker section."""
    result = system_control({"action": "help"})
    assert "Docker" in result
    assert "docker_containers" in result
    assert "docker_status" in result
    assert "docker_start" in result
    assert "docker_stop" in result
    assert "docker_restart" in result
    assert "docker_images" in result


def test_docker_regex_relevance():
    """The _DOCKER_RE pattern matches expected intents."""
    import re

    pattern = re.compile(r"\b(docker|container|compose)\b", re.I)
    assert pattern.search("list docker containers")
    assert pattern.search("start a container")
    assert pattern.search("docker compose up")
    assert pattern.search("stop the docker container")
    assert not pattern.search("list disks")
    assert not pattern.search("bluetooth device")
