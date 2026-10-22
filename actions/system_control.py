"""Deep system control for Lucas — GNOME settings, WiFi, audio, display, media."""

from __future__ import annotations

from core import gnome_settings as gnome
from core import audio_control as audio
from core import network_manager as net
from core import services as svc
from core import bluetooth_control as bt
from core import disk_control as disk
from core import firewall_control as fw
from core import extensions_control as ext
from core import printer_control as printer
from core import package_control as pkg
from core import browser_debug as bdbg
from core import scheduler as sched
from core import file_watcher as fwch
from core import clipboard_history as cb
from core import user_accounts as uacct
from core import macro_recorder as macro
from core.logger import get_logger

logger = get_logger(__name__)

TOOL_SCHEMA = {
    "name": "system_control",
    "description": (
        "Deep system control for your PC — GNOME desktop settings, WiFi, "
        "audio devices, display layout, screen recording, notifications, "
        "media players, systemd services, Bluetooth, disk/ USB, firewall, "
        "GNOME extensions, printers, packages, browser CDP control, "
        "scheduled tasks, file watchers, clipboard history, user accounts, "
        "macro recording, and Docker container management. "
        "Use action=help to list all ~100+ actions."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": (
                    "help | wifi_status | wifi_on | wifi_off | scan_wifi | "
                    "connect_wifi | disconnect_wifi | list_connections | "
                    "list_sinks | list_sources | set_default_sink | "
                    "set_default_source | set_dark_mode | set_wallpaper | "
                    "set_night_light | set_accent_color | set_keyboard_layout | "
                    "set_touchpad | set_font | set_power_profile | "
                    "list_displays | start_recording | stop_recording | "
                    "now_playing | next_track | prev_track | list_players | "
                    "send_notification | "
                    "list_services | service_status | start_service | "
                    "stop_service | restart_service | enable_service | "
                    "disable_service | "
                    "list_paired_devices | scan_devices | connect_device | "
                    "disconnect_device | bluetooth_on | bluetooth_off | "
                    "device_info | "
                    "list_disks | disk_usage | mount_device | unmount_device | "
                    "safely_eject | disk_info | "
                    "list_zones | list_open_ports | list_fw_services | "
                    "add_port | remove_port | firewall_status | "
                    "list_extensions | list_all_extensions | enable_extension | "
                    "disable_extension | extension_info | "
                    "list_printers | printer_status | list_print_jobs | "
                    "cancel_job | "
                    "list_installed | check_updates | install_package | "
                    "remove_package | package_info | search_packages | "
                    "list_browser_tabs | close_browser_tab | "
                    "activate_browser_tab | navigate_tab | "
                    "list_scheduled_tasks | create_scheduled_task | "
                    "remove_scheduled_task | scheduled_task_status | "
                    "watch_directory | list_watchers | stop_watcher | "
                    "stop_all_watchers | "
                    "clipboard_get | clipboard_copy | clipboard_history | "
                    "clipboard_paste_history | clipboard_clear | "
                    "list_users | current_user | "
                    "macro_start_recording | macro_stop_recording | "
                    "macro_play | macro_list | macro_status | "
                    "docker_containers | docker_status | docker_start | "
                    "docker_stop | docker_restart | docker_images"
                ),
            },
            "name": {
                "type": "STRING",
                "description": (
                    "SSID for connect_wifi, sink/source name for "
                    "set_default_sink/source, touchpad setting name, "
                    "or container name for Docker actions"
                ),
            },
            "all": {
                "type": "BOOLEAN",
                "description": "Show all containers (including stopped) for docker_containers",
            },
            "password": {"type": "STRING", "description": "WiFi password"},
            "enabled": {
                "type": "BOOLEAN",
                "description": "Toggle true/false for dark_mode, night_light",
            },
            "path": {"type": "STRING", "description": "File path for set_wallpaper"},
            "color": {"type": "STRING", "description": "Accent color name"},
            "layout": {
                "type": "STRING",
                "description": "Keyboard layout code (us, fr, etc.)",
            },
            "setting": {"type": "STRING", "description": "Touchpad setting name"},
            "value": {"type": "STRING", "description": "Touchpad setting value"},
            "font_type": {
                "type": "STRING",
                "description": "interface | monospace | document",
            },
            "font_name": {
                "type": "STRING",
                "description": "Font name with size, e.g. 'Cantarell 11'",
            },
            "profile": {
                "type": "STRING",
                "description": "power-saver | balanced | performance",
            },
            "title": {"type": "STRING", "description": "Notification title"},
            "body": {"type": "STRING", "description": "Notification body text"},
            "duration": {
                "type": "INTEGER",
                "description": "Seconds for notification display",
            },
            "service_name": {
                "type": "STRING",
                "description": "Service name for systemd actions",
            },
            "mac": {
                "type": "STRING",
                "description": "Bluetooth MAC address (XX:XX:XX:XX:XX:XX)",
            },
            "device": {
                "type": "STRING",
                "description": "Device path like sda1 or /dev/sda1",
            },
            "port": {"type": "STRING", "description": "Port number for firewall"},
            "protocol": {
                "type": "STRING",
                "description": "tcp or udp",
            },
            "uuid": {
                "type": "STRING",
                "description": "GNOME extension UUID",
            },
            "package": {
                "type": "STRING",
                "description": "Package name for dnf",
            },
            "printer": {
                "type": "STRING",
                "description": "Printer name",
            },
            "job_id": {
                "type": "STRING",
                "description": "Print job ID",
            },
            "query": {
                "type": "STRING",
                "description": "Search query",
            },
            "filter": {
                "type": "STRING",
                "description": "Filter string for list_services or list_installed",
            },
            "browser": {
                "type": "STRING",
                "description": "Browser name: chrome, firefox, brave, edge",
            },
            "tab_id": {
                "type": "STRING",
                "description": "Browser tab CDP ID (from list_browser_tabs)",
            },
            "url": {
                "type": "STRING",
                "description": "URL for browser navigation",
            },
            "schedule": {
                "type": "STRING",
                "description": (
                    "Schedule: minutely, hourly, daily, weekly, or cron expression"
                ),
            },
            "command": {
                "type": "STRING",
                "description": "Shell command to execute on schedule",
            },
            "task_name": {
                "type": "STRING",
                "description": "Name for the scheduled task",
            },
            "pattern": {
                "type": "STRING",
                "description": "File glob pattern for watching (e.g., *.txt)",
            },
            "watcher_id": {
                "type": "STRING",
                "description": "File watcher ID from list_watchers",
            },
            "text": {
                "type": "STRING",
                "description": "Text to copy to clipboard",
            },
            "index": {
                "type": "INTEGER",
                "description": "Index for clipboard history access",
            },
            "macro_path": {
                "type": "STRING",
                "description": "Path to macro file for playback",
            },
        },
        "required": ["action"],
    },
}


# ---------------------------------------------------------------------------
# Handler helpers
# ---------------------------------------------------------------------------


def _bool_param(params: dict, key: str, default: bool = True) -> bool:
    """Extract a boolean parameter from params dict."""
    val = params.get(key)
    if val is None:
        return default
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.lower() in ("true", "1", "yes", "on", "enabled")
    return bool(val)


def _str_param(params: dict, key: str, default: str = "") -> str:
    return str(params.get(key, default) or "").strip()


# ---------------------------------------------------------------------------
# Handlers — one per action
# ---------------------------------------------------------------------------


def _handle_help(params: dict) -> str:
    actions = [
        "── WiFi / Network ──",
        "  wifi_status       — Show WiFi status (enabled, connected, signal)",
        "  wifi_on/off       — Enable/disable WiFi radio",
        "  scan_wifi         — Scan and list available networks",
        "  connect_wifi      — Connect to a WiFi network (name=SSID, password=?)",
        "  disconnect_wifi   — Disconnect from current WiFi",
        "  list_connections  — Show all saved NetworkManager connections",
        "",
        "── Audio ──",
        "  list_sinks        — List audio output devices",
        "  list_sources      — List audio input devices",
        "  set_default_sink  — Set default audio output (name=sink_name)",
        "  set_default_source — Set default audio input (name=source_name)",
        "",
        "── GNOME Desktop ──",
        "  set_dark_mode     — Toggle dark mode (enabled=true/false)",
        "  set_wallpaper     — Set desktop wallpaper (path=/path/to/image)",
        "  set_night_light   — Toggle night light (enabled=true/false)",
        "  set_accent_color  — Set accent color (color=blue|teal|green|...)",
        "  set_keyboard_layout — Set keyboard layout (layout=us|fr|de|...)",
        "  set_touchpad      — Set touchpad (setting=, value=)",
        "  set_font          — Set desktop font (font_type=, font_name=)",
        "  set_power_profile — Set power profile (profile=balanced|...)",
        "  list_displays     — List connected displays",
        "",
        "── Recording / Media ──",
        "  start_recording   — Start GNOME screen recording",
        "  stop_recording    — Stop current screen recording",
        "  now_playing       — Show currently playing media",
        "  next_track        — Skip to next track",
        "  prev_track        — Go to previous track",
        "  list_players      — List available media players",
        "",
        "── Notifications ──",
        "  send_notification — Send a desktop notification (title=, body=)",
        "",
        "── Services (systemd) ──",
        "  list_services     — List systemd services (filter=optional)",
        "  service_status    — Show service status (service_name=)",
        "  start_service     — Start a service (service_name=)",
        "  stop_service      — Stop a service (service_name=)",
        "  restart_service   — Restart a service (service_name=)",
        "  enable_service    — Enable service at boot (service_name=)",
        "  disable_service   — Disable service at boot (service_name=)",
        "",
        "── Bluetooth ──",
        "  list_paired_devices — List paired Bluetooth devices",
        "  scan_devices      — Scan for Bluetooth devices (timeout=5)",
        "  connect_device    — Connect to Bluetooth device (mac=)",
        "  disconnect_device — Disconnect Bluetooth device (mac=)",
        "  bluetooth_on      — Power on Bluetooth",
        "  bluetooth_off     — Power off Bluetooth",
        "  device_info       — Show Bluetooth device info (mac=)",
        "",
        "── Disk / Storage ──",
        "  list_disks        — List all block devices",
        "  disk_usage        — Show disk usage (df -h)",
        "  mount_device      — Mount a device (device=sda1)",
        "  unmount_device    — Unmount a device (device=sda1)",
        "  safely_eject      — Safely eject a device (device=sda)",
        "  disk_info         — Show device details (device=sda1)",
        "",
        "── Firewall ──",
        "  list_zones         — List all firewall zones",
        "  list_open_ports    — List open firewall ports",
        "  list_fw_services   — List allowed firewall services",
        "  add_port           — Open a port (port=, protocol=tcp|udp)",
        "  remove_port        — Close a port (port=, protocol=tcp|udp)",
        "  firewall_status    — Check if firewalld is running",
        "",
        "── GNOME Extensions ──",
        "  list_extensions      — List enabled extensions",
        "  list_all_extensions  — List all extensions",
        "  enable_extension     — Enable an extension (uuid=)",
        "  disable_extension    — Disable an extension (uuid=)",
        "  extension_info       — Show extension details (uuid=)",
        "",
        "── Printers ──",
        "  list_printers     — List configured printers",
        "  printer_status    — Show printer status (printer=)",
        "  list_print_jobs   — List print queue",
        "  cancel_job        — Cancel a print job (job_id=)",
        "",
        "── Packages (dnf) ──",
        "  list_installed    — List installed packages (filter=)",
        "  check_updates     — Check for available updates",
        "  install_package   — Install a package (package=)",
        "  remove_package    — Remove a package (package=)",
        "  package_info      — Show package details (package=)",
        "  search_packages   — Search packages (query=)",
        "",
        "── Browser CDP Control ──",
        "  list_browser_tabs   — List browser tabs via CDP (browser=chrome)",
        "  close_browser_tab   — Close a tab (tab_id=, browser=)",
        "  activate_browser_tab — Activate/focus a tab (tab_id=, browser=)",
        "  navigate_tab        — Navigate a tab to a URL (tab_id=, url=, browser=)",
        "",
        "── Scheduled Tasks ──",
        "  list_scheduled_tasks     — List systemd user timers",
        "  create_scheduled_task    — Create timer (task_name=, command=, schedule=)",
        "  remove_scheduled_task    — Remove timer (task_name=)",
        "  scheduled_task_status    — Show timer status (task_name=)",
        "",
        "── File Watchers ──",
        "  watch_directory    — Watch a dir for changes (path=, pattern=)",
        "  list_watchers      — List active file watchers",
        "  stop_watcher       — Stop a watcher (watcher_id=)",
        "  stop_all_watchers  — Stop all watchers",
        "",
        "── Clipboard History ──",
        "  clipboard_get         — Get current clipboard content",
        "  clipboard_copy        — Copy text to clipboard (text=)",
        "  clipboard_history     — Show last 20 clipboard entries",
        "  clipboard_paste_history — Copy history item to clipboard (index=)",
        "  clipboard_clear       — Clear clipboard history",
        "",
        "── User Accounts ──",
        "  list_users        — List human user accounts",
        "  current_user      — Show current username",
        "",
        "── Macro Recording ──",
        "  macro_start_recording — Start recording mouse/keyboard",
        "  macro_stop_recording  — Stop and save macro recording",
        "  macro_play            — Play a macro (macro_path=)",
        "  macro_list            — List saved macros",
        "  macro_status          — Show recording status",
        "",
        "── Docker ──",
        "  docker_containers  — List Docker containers (all=true for stopped)",
        "  docker_status      — Docker system info or container status (name=)",
        "  docker_start       — Start a Docker container (name=)",
        "  docker_stop        — Stop a Docker container (name=)",
        "  docker_restart     — Restart a Docker container (name=)",
        "  docker_images      — List Docker images",
    ]
    return "\n".join(actions)


def _handle_wifi_status(params: dict) -> str:
    return net.wifi_status()


def _handle_wifi_on(params: dict) -> str:
    return net.wifi_on()


def _handle_wifi_off(params: dict) -> str:
    return net.wifi_off()


def _handle_scan_wifi(params: dict) -> str:
    return net.scan_wifi()


def _handle_connect_wifi(params: dict) -> str:
    ssid = _str_param(params, "name")
    if not ssid:
        return "Provide name=SSID to connect to a WiFi network."
    password = _str_param(params, "password")
    return net.connect_wifi(ssid, password)


def _handle_disconnect_wifi(params: dict) -> str:
    return net.disconnect_wifi()


def _handle_list_connections(params: dict) -> str:
    return net.list_connections()


def _handle_list_sinks(params: dict) -> str:
    return audio.list_sinks()


def _handle_list_sources(params: dict) -> str:
    return audio.list_sources()


def _handle_set_default_sink(params: dict) -> str:
    name = _str_param(params, "name")
    if not name:
        return "Provide name=sink_name to set default audio output."
    return audio.set_default_sink(name)


def _handle_set_default_source(params: dict) -> str:
    name = _str_param(params, "name")
    if not name:
        return "Provide name=source_name to set default audio input."
    return audio.set_default_source(name)


def _handle_set_dark_mode(params: dict) -> str:
    enabled = _bool_param(params, "enabled", True)
    return gnome.set_dark_mode(enabled)


def _handle_set_wallpaper(params: dict) -> str:
    path = _str_param(params, "path")
    if not path:
        return "Provide path=/path/to/image to set wallpaper."
    return gnome.set_wallpaper(path)


def _handle_set_night_light(params: dict) -> str:
    enabled = _bool_param(params, "enabled", True)
    return gnome.set_night_light(enabled)


def _handle_set_accent_color(params: dict) -> str:
    color = _str_param(params, "color")
    if not color:
        return "Provide color=accent_color_name to set accent color."
    return gnome.set_accent_color(color)


def _handle_set_keyboard_layout(params: dict) -> str:
    layout = _str_param(params, "layout")
    if not layout:
        return "Provide layout=keyboard_layout_code (e.g. 'us', 'fr')."
    return gnome.set_keyboard_layout(layout)


def _handle_set_touchpad(params: dict) -> str:
    setting = _str_param(params, "setting")
    value = _str_param(params, "value")
    if not setting:
        return (
            "Provide setting=touchpad_setting_name and value= to change "
            "touchpad. Example: setting=natural-scroll value=true"
        )
    if not value:
        return "Provide value= for the touchpad setting."
    return gnome.set_touchpad_setting(setting, value)


def _handle_set_font(params: dict) -> str:
    font_type = _str_param(params, "font_type")
    font_name = _str_param(params, "font_name")
    if not font_type or not font_name:
        return (
            "Provide font_type=(interface|monospace|document) and "
            "font_name='Font Name Size'. Example: font_type=interface "
            "font_name='Cantarell 11'"
        )
    return gnome.set_font(font_type, font_name)


def _handle_set_power_profile(params: dict) -> str:
    profile = _str_param(params, "profile")
    if not profile:
        return "Provide profile=(power-saver|balanced|performance)."
    return gnome.set_power_profile(profile)


def _handle_list_displays(params: dict) -> str:
    displays = gnome.list_displays()
    if not displays:
        return "No displays detected."
    lines = [f"Displays ({len(displays)}):"]
    for i, d in enumerate(displays, 1):
        name = d.get("name", "Unknown")
        res = d.get("resolution", "")
        scale = d.get("scale", "")
        parts = [f"  {i}. {name}"]
        if res:
            parts.append(res)
        if scale:
            parts.append(f"@{scale}")
        lines.append(" ".join(parts))
    return "\n".join(lines)


def _handle_start_recording(params: dict) -> str:
    return gnome.start_screen_recording()


def _handle_stop_recording(params: dict) -> str:
    return gnome.stop_screen_recording()


def _handle_now_playing(params: dict) -> str:
    return gnome.now_playing()


def _handle_next_track(params: dict) -> str:
    return gnome.media_control("next")


def _handle_prev_track(params: dict) -> str:
    return gnome.media_control("previous")


def _handle_list_players(params: dict) -> str:
    return gnome.list_players()


def _handle_send_notification(params: dict) -> str:
    title = _str_param(params, "title", "Lucas")
    body = _str_param(params, "body", "")
    if not body:
        return "Provide body=notification_text to send a notification."
    duration = params.get("duration")
    if duration is not None:
        duration = int(duration)
    else:
        duration = 5
    return gnome.send_notification(title, body, duration)


# ---------------------------------------------------------------------------
# Services (systemd) handlers
# ---------------------------------------------------------------------------


def _handle_list_services(params: dict) -> str:
    filter_str = _str_param(params, "filter")
    return svc.list_services(filter_str)


def _handle_service_status(params: dict) -> str:
    name = _str_param(params, "service_name")
    if not name:
        return "Provide service_name= for the service."
    return svc.service_status(name)


def _handle_start_service(params: dict) -> str:
    name = _str_param(params, "service_name")
    if not name:
        return "Provide service_name= for the service."
    return svc.start_service(name)


def _handle_stop_service(params: dict) -> str:
    name = _str_param(params, "service_name")
    if not name:
        return "Provide service_name= for the service."
    return svc.stop_service(name)


def _handle_restart_service(params: dict) -> str:
    name = _str_param(params, "service_name")
    if not name:
        return "Provide service_name= for the service."
    return svc.restart_service(name)


def _handle_enable_service(params: dict) -> str:
    name = _str_param(params, "service_name")
    if not name:
        return "Provide service_name= for the service."
    return svc.enable_service(name)


def _handle_disable_service(params: dict) -> str:
    name = _str_param(params, "service_name")
    if not name:
        return "Provide service_name= for the service."
    return svc.disable_service(name)


# ---------------------------------------------------------------------------
# Bluetooth handlers
# ---------------------------------------------------------------------------


def _handle_list_paired_devices(params: dict) -> str:
    return bt.list_paired_devices()


def _handle_scan_devices(params: dict) -> str:
    timeout = params.get("timeout", 5)
    if timeout is not None:
        timeout = int(timeout)
    else:
        timeout = 5
    return bt.scan_devices(timeout)


def _handle_connect_device(params: dict) -> str:
    mac = _str_param(params, "mac")
    if not mac:
        return "Provide mac= for the Bluetooth device address."
    return bt.connect_device(mac)


def _handle_disconnect_device(params: dict) -> str:
    mac = _str_param(params, "mac")
    if not mac:
        return "Provide mac= for the Bluetooth device address."
    return bt.disconnect_device(mac)


def _handle_bluetooth_on(params: dict) -> str:
    return bt.bluetooth_on()


def _handle_bluetooth_off(params: dict) -> str:
    return bt.bluetooth_off()


def _handle_device_info(params: dict) -> str:
    mac = _str_param(params, "mac")
    if not mac:
        return "Provide mac= for the Bluetooth device address."
    return bt.device_info(mac)


# ---------------------------------------------------------------------------
# Disk / Storage handlers
# ---------------------------------------------------------------------------


def _handle_list_disks(params: dict) -> str:
    return disk.list_disks()


def _handle_disk_usage(params: dict) -> str:
    return disk.disk_usage()


def _handle_mount_device(params: dict) -> str:
    device = _str_param(params, "device")
    if not device:
        return "Provide device= (e.g. sda1 or /dev/sda1)."
    return disk.mount_device(device)


def _handle_unmount_device(params: dict) -> str:
    device = _str_param(params, "device")
    if not device:
        return "Provide device= (e.g. sda1 or /dev/sda1)."
    return disk.unmount_device(device)


def _handle_safely_eject(params: dict) -> str:
    device = _str_param(params, "device")
    if not device:
        return "Provide device= (e.g. sda or /dev/sda)."
    return disk.safely_eject(device)


def _handle_disk_info(params: dict) -> str:
    device = _str_param(params, "device")
    if not device:
        return "Provide device= (e.g. sda1 or /dev/sda1)."
    return disk.disk_info(device)


# ---------------------------------------------------------------------------
# Firewall handlers
# ---------------------------------------------------------------------------


def _handle_list_zones(params: dict) -> str:
    return fw.list_zones()


def _handle_list_open_ports(params: dict) -> str:
    return fw.list_open_ports()


def _handle_list_fw_services(params: dict) -> str:
    return fw.list_services()


def _handle_add_port(params: dict) -> str:
    port = _str_param(params, "port")
    if not port:
        return "Provide port= (number) to open."
    protocol = _str_param(params, "protocol", "tcp")
    return fw.add_port(port, protocol)


def _handle_remove_port(params: dict) -> str:
    port = _str_param(params, "port")
    if not port:
        return "Provide port= (number) to close."
    protocol = _str_param(params, "protocol", "tcp")
    return fw.remove_port(port, protocol)


def _handle_firewall_status(params: dict) -> str:
    return fw.firewall_status()


# ---------------------------------------------------------------------------
# GNOME Extensions handlers
# ---------------------------------------------------------------------------


def _handle_list_extensions(params: dict) -> str:
    return ext.list_extensions()


def _handle_list_all_extensions(params: dict) -> str:
    return ext.list_all_extensions()


def _handle_enable_extension(params: dict) -> str:
    uuid = _str_param(params, "uuid")
    if not uuid:
        return "Provide uuid= for the extension."
    return ext.enable_extension(uuid)


def _handle_disable_extension(params: dict) -> str:
    uuid = _str_param(params, "uuid")
    if not uuid:
        return "Provide uuid= for the extension."
    return ext.disable_extension(uuid)


def _handle_extension_info(params: dict) -> str:
    uuid = _str_param(params, "uuid")
    if not uuid:
        return "Provide uuid= for the extension."
    return ext.extension_info(uuid)


# ---------------------------------------------------------------------------
# Printer handlers
# ---------------------------------------------------------------------------


def _handle_list_printers(params: dict) -> str:
    return printer.list_printers()


def _handle_printer_status(params: dict) -> str:
    name = _str_param(params, "printer")
    if not name:
        return "Provide printer= for the printer name."
    return printer.printer_status(name)


def _handle_list_print_jobs(params: dict) -> str:
    return printer.list_print_jobs()


def _handle_cancel_job(params: dict) -> str:
    job_id = _str_param(params, "job_id")
    if not job_id:
        return "Provide job_id= for the print job."
    return printer.cancel_job(job_id)


# ---------------------------------------------------------------------------
# Package (dnf) handlers
# ---------------------------------------------------------------------------


def _handle_list_installed(params: dict) -> str:
    filter_str = _str_param(params, "filter")
    return pkg.list_installed(filter_str)


def _handle_check_updates(params: dict) -> str:
    return pkg.check_updates()


def _handle_install_package(params: dict) -> str:
    package = _str_param(params, "package")
    if not package:
        return "Provide package= name to install."
    return pkg.install_package(package)


def _handle_remove_package(params: dict) -> str:
    package = _str_param(params, "package")
    if not package:
        return "Provide package= name to remove."
    return pkg.remove_package(package)


def _handle_package_info(params: dict) -> str:
    package = _str_param(params, "package")
    if not package:
        return "Provide package= name."
    return pkg.package_info(package)


def _handle_search_packages(params: dict) -> str:
    query = _str_param(params, "query")
    if not query:
        return "Provide query= for the package search."
    return pkg.search_packages(query)


# ---------------------------------------------------------------------------
# Phase 3 — Browser CDP Control handlers
# ---------------------------------------------------------------------------


def _handle_list_browser_tabs(params: dict) -> str:
    browser = _str_param(params, "browser", "chrome")
    return bdbg.list_browser_tabs(browser)


def _handle_close_browser_tab(params: dict) -> str:
    tab_id = _str_param(params, "tab_id")
    if not tab_id:
        return "Provide tab_id= from list_browser_tabs."
    browser = _str_param(params, "browser", "chrome")
    return bdbg.close_browser_tab(tab_id, browser)


def _handle_activate_browser_tab(params: dict) -> str:
    tab_id = _str_param(params, "tab_id")
    if not tab_id:
        return "Provide tab_id= from list_browser_tabs."
    browser = _str_param(params, "browser", "chrome")
    return bdbg.activate_browser_tab(tab_id, browser)


def _handle_navigate_tab(params: dict) -> str:
    tab_id = _str_param(params, "tab_id")
    url = _str_param(params, "url")
    if not tab_id:
        return "Provide tab_id= from list_browser_tabs."
    if not url:
        return "Provide url= to navigate to."
    browser = _str_param(params, "browser", "chrome")
    return bdbg.navigate_tab(tab_id, url, browser)


# ---------------------------------------------------------------------------
# Phase 3 — Scheduled Task handlers
# ---------------------------------------------------------------------------


def _handle_list_scheduled_tasks(params: dict) -> str:
    return sched.list_scheduled_tasks()


def _handle_create_scheduled_task(params: dict) -> str:
    name = _str_param(params, "task_name")
    command = _str_param(params, "command")
    schedule = _str_param(params, "schedule")
    if not name:
        return "Provide task_name= for the scheduled task."
    if not command:
        return "Provide command= (shell command) for the scheduled task."
    if not schedule:
        return (
            "Provide schedule= — minutely, hourly, daily, weekly, or cron expression."
        )
    return sched.create_scheduled_task(name, command, schedule)


def _handle_remove_scheduled_task(params: dict) -> str:
    name = _str_param(params, "task_name")
    if not name:
        return "Provide task_name= for the scheduled task to remove."
    return sched.remove_scheduled_task(name)


def _handle_scheduled_task_status(params: dict) -> str:
    name = _str_param(params, "task_name")
    if not name:
        return "Provide task_name= for the scheduled task."
    return sched.scheduled_task_status(name)


# ---------------------------------------------------------------------------
# Phase 3 — File Watcher handlers
# ---------------------------------------------------------------------------


def _handle_watch_directory(params: dict) -> str:
    path = _str_param(params, "path")
    if not path:
        return "Provide path= to the directory to watch."
    pattern = _str_param(params, "pattern", "*")
    return fwch.watch_directory(path, pattern)


def _handle_list_watchers(params: dict) -> str:
    return fwch.list_watchers()


def _handle_stop_watcher(params: dict) -> str:
    watcher_id = _str_param(params, "watcher_id")
    if not watcher_id:
        return "Provide watcher_id= from list_watchers."
    return fwch.stop_watcher(watcher_id)


def _handle_stop_all_watchers(params: dict) -> str:
    return fwch.stop_all_watchers()


# ---------------------------------------------------------------------------
# Phase 3 — Clipboard History handlers
# ---------------------------------------------------------------------------


def _handle_clipboard_get(params: dict) -> str:
    return cb.clipboard_get()


def _handle_clipboard_copy(params: dict) -> str:
    text = _str_param(params, "text")
    if not text:
        return "Provide text= to copy to clipboard."
    return cb.clipboard_copy(text)


def _handle_clipboard_history(params: dict) -> str:
    return cb.clipboard_history()


def _handle_clipboard_paste_history(params: dict) -> str:
    index = params.get("index")
    if index is None:
        return (
            "Provide index= for clipboard history (use clipboard_history to see items)."
        )
    try:
        idx = int(index)
    except (ValueError, TypeError):
        return "Provide a valid numeric index= for clipboard history."
    return cb.clipboard_paste_history(idx)


def _handle_clipboard_clear(params: dict) -> str:
    cb.clear_history()
    return "Clipboard history cleared."


# ---------------------------------------------------------------------------
# Phase 3 — User Account handlers
# ---------------------------------------------------------------------------


def _handle_list_users(params: dict) -> str:
    return uacct.list_users()


def _handle_current_user(params: dict) -> str:
    return uacct.current_user()


# ---------------------------------------------------------------------------
# Phase 3 — Macro Recording handlers
# ---------------------------------------------------------------------------


def _handle_macro_start_recording(params: dict) -> str:
    path = _str_param(params, "macro_path")
    return macro.start_recording(path)


def _handle_macro_stop_recording(params: dict) -> str:
    path = _str_param(params, "macro_path")
    return macro.stop_recording(path)


def _handle_macro_play(params: dict) -> str:
    path = _str_param(params, "macro_path")
    if not path:
        return "Provide macro_path= to the macro file."
    return macro.play_macro(path)


def _handle_macro_list(params: dict) -> str:
    return macro.list_macros()


def _handle_macro_status(params: dict) -> str:
    return macro.recording_status()


# ---------------------------------------------------------------------------
# Docker handler functions
# ---------------------------------------------------------------------------


def _handle_docker_containers(parameters: dict) -> str:
    """List Docker containers."""
    from core.docker_control import list_containers

    return list_containers(all_containers=parameters.get("all", False))


def _handle_docker_status(parameters: dict) -> str:
    """Get Docker status / container status."""
    container = (parameters.get("name") or "").strip()
    if container:
        from core.docker_control import container_status

        return container_status(container)
    from core.docker_control import docker_info

    return docker_info()


def _handle_docker_start(parameters: dict) -> str:
    """Start a Docker container."""
    from core.docker_control import start_container

    name = (parameters.get("name") or "").strip()
    if not name:
        return "container name is required."
    return start_container(name)


def _handle_docker_stop(parameters: dict) -> str:
    """Stop a Docker container."""
    from core.docker_control import stop_container

    name = (parameters.get("name") or "").strip()
    if not name:
        return "container name is required."
    return stop_container(name)


def _handle_docker_restart(parameters: dict) -> str:
    """Restart a Docker container."""
    from core.docker_control import restart_container

    name = (parameters.get("name") or "").strip()
    if not name:
        return "container name is required."
    return restart_container(name)


def _handle_docker_images(parameters: dict) -> str:
    """List Docker images."""
    from core.docker_control import list_images

    return list_images()


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

HANDLERS = {
    "help": _handle_help,
    "wifi_status": _handle_wifi_status,
    "wifi_on": _handle_wifi_on,
    "wifi_off": _handle_wifi_off,
    "scan_wifi": _handle_scan_wifi,
    "connect_wifi": _handle_connect_wifi,
    "disconnect_wifi": _handle_disconnect_wifi,
    "list_connections": _handle_list_connections,
    "list_sinks": _handle_list_sinks,
    "list_sources": _handle_list_sources,
    "set_default_sink": _handle_set_default_sink,
    "set_default_source": _handle_set_default_source,
    "set_dark_mode": _handle_set_dark_mode,
    "set_wallpaper": _handle_set_wallpaper,
    "set_night_light": _handle_set_night_light,
    "set_accent_color": _handle_set_accent_color,
    "set_keyboard_layout": _handle_set_keyboard_layout,
    "set_touchpad": _handle_set_touchpad,
    "set_font": _handle_set_font,
    "set_power_profile": _handle_set_power_profile,
    "list_displays": _handle_list_displays,
    "start_recording": _handle_start_recording,
    "stop_recording": _handle_stop_recording,
    "now_playing": _handle_now_playing,
    "next_track": _handle_next_track,
    "prev_track": _handle_prev_track,
    "list_players": _handle_list_players,
    "send_notification": _handle_send_notification,
    # Services
    "list_services": _handle_list_services,
    "service_status": _handle_service_status,
    "start_service": _handle_start_service,
    "stop_service": _handle_stop_service,
    "restart_service": _handle_restart_service,
    "enable_service": _handle_enable_service,
    "disable_service": _handle_disable_service,
    # Bluetooth
    "list_paired_devices": _handle_list_paired_devices,
    "scan_devices": _handle_scan_devices,
    "connect_device": _handle_connect_device,
    "disconnect_device": _handle_disconnect_device,
    "bluetooth_on": _handle_bluetooth_on,
    "bluetooth_off": _handle_bluetooth_off,
    "device_info": _handle_device_info,
    # Disk
    "list_disks": _handle_list_disks,
    "disk_usage": _handle_disk_usage,
    "mount_device": _handle_mount_device,
    "unmount_device": _handle_unmount_device,
    "safely_eject": _handle_safely_eject,
    "disk_info": _handle_disk_info,
    # Firewall
    "list_zones": _handle_list_zones,
    "list_open_ports": _handle_list_open_ports,
    "list_fw_services": _handle_list_fw_services,
    "add_port": _handle_add_port,
    "remove_port": _handle_remove_port,
    "firewall_status": _handle_firewall_status,
    # Extensions
    "list_extensions": _handle_list_extensions,
    "list_all_extensions": _handle_list_all_extensions,
    "enable_extension": _handle_enable_extension,
    "disable_extension": _handle_disable_extension,
    "extension_info": _handle_extension_info,
    # Printers
    "list_printers": _handle_list_printers,
    "printer_status": _handle_printer_status,
    "list_print_jobs": _handle_list_print_jobs,
    "cancel_job": _handle_cancel_job,
    # Packages
    "list_installed": _handle_list_installed,
    "check_updates": _handle_check_updates,
    "install_package": _handle_install_package,
    "remove_package": _handle_remove_package,
    "package_info": _handle_package_info,
    "search_packages": _handle_search_packages,
    # Browser CDP
    "list_browser_tabs": _handle_list_browser_tabs,
    "close_browser_tab": _handle_close_browser_tab,
    "activate_browser_tab": _handle_activate_browser_tab,
    "navigate_tab": _handle_navigate_tab,
    # Scheduled tasks
    "list_scheduled_tasks": _handle_list_scheduled_tasks,
    "create_scheduled_task": _handle_create_scheduled_task,
    "remove_scheduled_task": _handle_remove_scheduled_task,
    "scheduled_task_status": _handle_scheduled_task_status,
    # File watchers
    "watch_directory": _handle_watch_directory,
    "list_watchers": _handle_list_watchers,
    "stop_watcher": _handle_stop_watcher,
    "stop_all_watchers": _handle_stop_all_watchers,
    # Clipboard
    "clipboard_get": _handle_clipboard_get,
    "clipboard_copy": _handle_clipboard_copy,
    "clipboard_history": _handle_clipboard_history,
    "clipboard_paste_history": _handle_clipboard_paste_history,
    "clipboard_clear": _handle_clipboard_clear,
    # User accounts
    "list_users": _handle_list_users,
    "current_user": _handle_current_user,
    # Macro recording
    "macro_start_recording": _handle_macro_start_recording,
    "macro_stop_recording": _handle_macro_stop_recording,
    "macro_play": _handle_macro_play,
    "macro_list": _handle_macro_list,
    "macro_status": _handle_macro_status,
    # Docker
    "docker_containers": _handle_docker_containers,
    "docker_status": _handle_docker_status,
    "docker_start": _handle_docker_start,
    "docker_stop": _handle_docker_stop,
    "docker_restart": _handle_docker_restart,
    "docker_images": _handle_docker_images,
}


def system_control(parameters: dict, player=None) -> str:
    """Execute a system control action."""
    action = (parameters.get("action") or "").lower().strip()

    if player:
        player.write_log(f"[SystemControl] {action}")

    if not action:
        return "No action provided. Use action=help to list all available actions."

    handler = HANDLERS.get(action)
    if handler is None:
        return (
            f"Unknown action: '{action}'. Use action=help to list all "
            f"~100+ available actions."
        )

    try:
        return handler(parameters)
    except Exception as e:
        logger.error("system_control action '%s' failed: %s", action, e)
        return f"Action '{action}' failed: {e}"
