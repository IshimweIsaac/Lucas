"""Guards and hints for Live tool calls — reduce wrong tool / over-planning."""

from __future__ import annotations

import re
from pathlib import Path

_LUCAS_REPO = str(Path(__file__).resolve().parent.parent)

_SIMPLE_DIRECT_RE = re.compile(
    r"\b(remind|reminder|calendar|weather|volume|brightness|wifi|open\s+\w+|"
    r"briefing|snooze|heartbeat|battery|charge|mute|tab)\b",
    re.I,
)

_RESTART_LUCAS_RE = re.compile(
    r"^\s*restart\s*\.?\s*$|restart\s+lucas|restart\s+lukas|reboot\s+lucas|"
    r"restart\s+(yourself|the\s+assistant|lucas|lukas)\b",
    re.I,
)

_TIME_DATE_RE = re.compile(
    r"\b(what\s+time|current\s+time|tell\s+me\s+the\s+time|what\s+is\s+the\s+time|"
    r"what\s+date|today'?s\s+date|what\s+day\s+is\s+it|check\s+the\s+time)\b",
    re.I,
)

_PC_CONTROL_RE = re.compile(
    r"\b(volume|brightness|mute|battery|charge|plug in|close\s+(chrome|firefox|app)|"
    r"focus\s+(chrome|firefox|browser)|next tab|previous tab|close tab|pause|play|"
    r"brightness|louder|quieter|dim|brighter)\b",
    re.I,
)
_REPO_FIX_RE = re.compile(
    r"\b(fix|patch|edit|refactor|debug|test|pytest|ruff|repo|lucas\s+code)\b",
    re.I,
)
_LUMINA_RE = re.compile(r"\blumina\b", re.I)
_WIFI_RE = re.compile(r"\b(wifi|wi.?fi|wireless|network|connect.*wifi)\b", re.I)
_DISPLAY_RE = re.compile(r"\b(display|monitor|screen.*record|resolution)\b", re.I)
_GNOME_RE = re.compile(
    r"\b(dark mode|wallpaper|night light|accent color|layout|touchpad|font)\b", re.I
)
_AUDIO_RE = re.compile(
    r"\b(sink|source|audio device|default.*audio|switch.*audio)\b", re.I
)
_MEDIA_RE = re.compile(
    r"\b(now playing|what.*playing|current.*track|media.*player)\b", re.I
)
_NOTES_RE = re.compile(r"\b(note|notebook|notes|journal|diary)\b", re.I)

_BLUETOOTH_RE = re.compile(
    r"\b(bluetooth|pair|airpods?|speaker|headset|earphone)\b", re.I
)
_DISK_RE = re.compile(r"\b(disks?|drive|mount|unmount|eject|usb|storage)\b", re.I)
_SERVICE_RE = re.compile(r"\b(services?|systemd|daemon)\b", re.I)
_FIREWALL_RE = re.compile(r"\b(firewall|port|allow.*port|block.*port)\b", re.I)
_EXTENSION_RE = re.compile(r"\b(extensions?|gnome.*ext|shell.*ext)\b", re.I)
_PRINTER_RE = re.compile(r"\b(printers?|print.*jobs?|print.*queue)\b", re.I)
_PACKAGE_RE = re.compile(
    r"\b(install.*package|remove.*package|dnf|package.*manager|update.*system)\b", re.I
)
_SYSTEM_CONTROL_RE = re.compile(
    r"\b(wifi|display|wallpaper|dark mode|night light|recording|screen.*record)\b", re.I
)
_BROWSER_TAB_RE = re.compile(
    r"\b(tab.*close|close.*tab|browser.*tab|what.*tab|activate.*tab|"
    r"navigate.*tab)\b",
    re.I,
)
_SCHEDULE_RE = re.compile(
    r"\b(schedule|timer|cron|every.*(day|hour|minute)|recurring)\b", re.I
)
_FILE_WATCH_RE = re.compile(r"\b(watch.*folder|watch.*directory|monitor.*file)\b", re.I)
_DOCKER_RE = re.compile(r"\b(docker|container|compose)\b", re.I)
_LPM_RE = re.compile(
    r"\b(projects?|tasks?|labels?|sprints?|"
    r"board|lpm|blocked|blocking)\b",
    re.I,
)

_CLIPBOARD_HISTORY_RE = re.compile(
    r"\b(clipboard.*history|paste.*history|copy.*history)\b", re.I
)
_MACRO_RE = re.compile(r"\b(macro|record.*macro|play.*macro)\b", re.I)
_USER_ACCOUNT_RE = re.compile(r"\b(user.*account|list.*user|who.*logged)\b", re.I)

# ---- Phase 4 — Context awareness routing guards ----
_CONTEXT_RE = re.compile(
    r"\b(context|what.*doing|environment|am.*doing|should.*do|what.*up)\b", re.I
)
_PREDICT_RE = re.compile(
    r"\b(predict|patterns?|suggest|usually|always.*do|next.*action|"
    r"what.*usually)\b",
    re.I,
)
_AUDIO_ROUTE_RE = re.compile(
    r"\b(route.*audio|audio.*route|audio.*output|pipewire|mute.*app|"
    r"move.*audio|switch.*audio.*output)\b",
    re.I,
)
_CONTROLLER_RE = re.compile(
    r"\b(controllers?|gamepad|joystick|input.*devices?)\b", re.I
)

_HABITS_RE = re.compile(r"\b(habits?|goals?|streaks?|log.*habit|tracker)\b", re.I)

_PRESENTATION_RE = re.compile(
    r"\b(presentations?|slides?|show.*slide|dashboard|briefing|show me|display|present|visual)\b",
    re.I,
)

_OPENCODE_WS_RE = re.compile(
    r"(?i)(opencode\s+(agent|code|work|send|task|status|cancel|spawn|trace)|"
    r"opencode|"
    r"ask\s+opencode|"
    r"tell\s+opencode|"
    r"use\s+opencode)"
)

_EMAIL_RE = re.compile(
    r"\b(email|mail|inbox|send.*email|compose.*email|check.*mail|unread)\b", re.I
)

_OPENCODE_TRACE_RE = re.compile(
    r"(?i)(what\s+(did|has)\s+opencode|"
    r"show\s+(me\s+)?(the\s+)?(opencode\s+)?(trace|tree|agents|spawned)|"
    r"what\s+agents?\s+(did\s+)?(opencode\s+)?spawn|"
    r"opencode\s+(summary|report|recap)|"
    r"how\s+(is|are)\s+opencode|"
    r"opencode\s+(progress|status))"
)

# Desktop Sway workspace intent — always carries a number. This must stay
# before _WS_SWITCH_RE so "switch to workspace 3" is not swallowed by the
# OpenCode coding-workspace redirect. Uses \bworkspaces?\b / \bdesktops?\b
# (the \bworkspace\b plural gotcha).
_SWAY_WS_RE = re.compile(
    r"\b(go|switch|move|change|set|jump)\s+(to\s+)?(the\s+)?"
    r"(workspaces?|desktops?)\s+\d+\b"
    r"|\bpresent\s+(on|in|to)\s+(the\s+)?workspaces?\s+\d+\b",
    re.I,
)

# Present-on-workspace clause ONLY (a subset of _SWAY_WS_RE). presentation_control
# has its own `workspace` param that switches Sway before opening, so this
# intent must NOT be redirected to sway_control when the model picked it.
_PRESENT_ON_WS_RE = re.compile(
    r"\bpresent\s+(on|in|to)\s+(the\s+)?workspaces?\s+\d+\b",
    re.I,
)

# Workspace switch/set intent. Note the plural gotcha: `\bworkspace\b` does NOT
# match "workspaces", so the regex uses `\bworkspaces?\b`.
_WS_SWITCH_RE = re.compile(
    r"\b(switch|set|change|use)\s+(the\s+)?(opencode\s+)?(workspaces?|repos?|projects?)\b"
    r"|\bworkspaces?\b.*\b(repo|project|path)\b",
    re.I,
)

_FIX_IMPROVE_REPO_RE = re.compile(
    r"\b(fix|improve|refactor|patch)\s+(this|the)\s+repo\b",
    re.I,
)


def guard_tool_call(name: str, args: dict) -> str | None:
    """
    Return a user-visible result string to short-circuit a bad tool call,
    or None to proceed normally.
    """
    goal = (
        args.get("goal") or args.get("description") or args.get("query") or ""
    ).strip()
    goal_low = goal.lower()

    if name == "computer_control":
        act = (args.get("action") or "").lower().strip()
        if act == "execute":
            return (
                "computer_control cannot run shell commands. "
                "Use pc_controller action=time or action=date."
            )

    if _TIME_DATE_RE.search(goal) and name != "pc_controller":
        return (
            "Call pc_controller with action=time or action=date for the real clock — "
            "do not guess or reuse old times from the session brief."
        )

    if name == "computer_settings":
        desc = (args.get("description") or goal or "").strip()
        if _RESTART_LUCAS_RE.search(desc):
            return (
                "Use restart_lucas to restart the Lucas assistant immediately — "
                "not computer_settings."
            )

    if _PC_CONTROL_RE.search(goal) and name not in (
        "pc_controller",
        "computer_settings",
    ):
        return (
            "Use pc_controller for volume, brightness, battery status, app focus, "
            "browser tabs, and media. Example: pc_controller action=volume_set value=30."
        )

    if name == "agent_task":
        if goal and len(goal) < 140 and _SIMPLE_DIRECT_RE.search(goal):
            return (
                "Use a direct tool instead of agent_task for this, sir — e.g. "
                "pc_controller, reminder, calendar_manager, weather_report, or open_app."
            )
        if goal and _REPO_FIX_RE.search(goal) and "lumina" not in goal_low:
            return (
                "For Lucas repo fixes use coding_workspace with grep→read→patch, "
                "not agent_task. Say: set workspace to Lucas then patch the file."
            )

    if name == "file_controller" and goal:
        action = (args.get("action") or "").lower()
        path = (args.get("path") or "").lower()
        if action in ("read", "list") and any(
            x in path for x in ("/lucas", "/lumina", "documents/lucas")
        ):
            if _REPO_FIX_RE.search(goal):
                return (
                    "For code changes use coding_workspace (grep, read, patch), "
                    "not file_controller."
                )

    if name == "coding_workspace":
        action = (args.get("action") or "task").lower()
        if action == "run" and not (args.get("command") or "").strip():
            ws = (args.get("workspace_path") or "").lower()
            if "lumina" in ws or _LUMINA_RE.search(goal):
                return (
                    "For Lumina/shell commands use coding_workspace run with "
                    "command= (e.g. git describe --tags, cargo check). "
                    "run without command only runs verify (pytest/cargo check)."
                )

    # ---- Desktop Sway workspace intent -> sway_control --------------------
    # presentation_control is exempt for present-on-workspace goals: it has its
    # own `workspace` param that switches Sway before opening the slides.
    if (
        name != "sway_control"
        and not (name == "presentation_control" and _PRESENT_ON_WS_RE.search(goal))
        and _SWAY_WS_RE.search(goal)
    ):
        return (
            "Use sway_control action=switch_workspace with number= to switch "
            "the Sway desktop workspace — not this tool."
        )

    # ---- Workspace switch intent (repo) -> opencode_control ----------------
    # Desktop workspace numbering is handled by the _SWAY_WS_RE guard above;
    # this redirect handles OpenCode repo/coding workspace switching only.
    if name not in ("opencode_control", "sway_control") and _WS_SWITCH_RE.search(goal):
        return (
            "Use opencode_control action=switch_workspace (or set_workspace) with "
            "workspace_path= to switch the OpenCode coding workspace — not this tool."
        )

    # ---- "fix this repo" -> opencode_control on the active workspace ------
    if name != "opencode_control" and _FIX_IMPROVE_REPO_RE.search(goal):
        return (
            "Use opencode_control action=send with the fix goal and "
            "workspace_path= set to the active repo — not this tool."
        )

    # ---- OpenCode routing guard ----
    if name != "opencode_control" and _OPENCODE_WS_RE.search(goal):
        return (
            "Use opencode_control for OpenCode tasks. "
            "Set action=send and include workspace_path= for the project folder."
        )

    # ---- OpenCode trace/status queries ----
    if _OPENCODE_TRACE_RE.search(goal):
        return (
            "Use opencode_control action=trace_voice to get a speakable summary. "
            "Use opencode_control action=trace_deep for the full recursive agent tree. "
            "Use opencode_control action=status for server status."
        )

    # ---- Route coding_workspace to opencode_control for complex tasks ----
    if (
        name == "coding_workspace"
        and len(goal) > 50  # Long tasks are complex
        and (
            "refactor" in goal.lower()
            or "implement" in goal.lower()
            or "debug" in goal.lower()
        )
    ):
        return (
            "This task is complex — consider using opencode_control action=send "
            "with the full goal for better multi-agent handling."
        )

    # ---- System Control routing guards ----
    if name != "system_control" and _SYSTEM_CONTROL_RE.search(goal):
        return (
            "Use system_control for deep system settings — WiFi, display, "
            "dark mode, wallpaper, screen recording, notifications, "
            "media players, audio devices, and power profiles."
        )

    # ---- Audio device redirect from pc_controller ----
    if name == "pc_controller" and _AUDIO_RE.search(goal):
        return (
            "For audio device management (sinks, sources, switching devices) "
            "use system_control action=list_sinks or set_default_sink."
        )

    # ---- Bluetooth routing guard ----
    if name != "system_control" and _BLUETOOTH_RE.search(goal):
        return (
            "Use system_control for Bluetooth actions — list_paired_devices, "
            "scan_devices, connect_device, disconnect_device, etc."
        )

    # ---- Disk/Storage routing guard ----
    if name != "system_control" and _DISK_RE.search(goal):
        return (
            "Use system_control for disk and storage actions — list_disks, "
            "disk_usage, mount_device, unmount_device, safely_eject."
        )

    # ---- Service routing guard ----
    if name != "system_control" and _SERVICE_RE.search(goal):
        return (
            "Use system_control for service management — list_services, "
            "start_service, stop_service, restart_service, enable_service."
        )

    # ---- Firewall routing guard ----
    if name != "system_control" and _FIREWALL_RE.search(goal):
        return (
            "Use system_control for firewall actions — list_zones, "
            "list_open_ports, add_port, remove_port, firewall_status."
        )

    # ---- Extension routing guard ----
    if name != "system_control" and _EXTENSION_RE.search(goal):
        return (
            "Use system_control for GNOME extension management — "
            "list_extensions, enable_extension, disable_extension, "
            "extension_info."
        )

    # ---- Printer routing guard ----
    if name != "system_control" and _PRINTER_RE.search(goal):
        return (
            "Use system_control for printer management — list_printers, "
            "printer_status, list_print_jobs, cancel_job."
        )

    # ---- Package routing guard ----
    if name != "system_control" and _PACKAGE_RE.search(goal):
        return (
            "Use system_control for package management — list_installed, "
            "check_updates, install_package, package_info, search_packages."
        )

    # ---- Browser CDP routing guard ----
    if name != "system_control" and _BROWSER_TAB_RE.search(goal):
        return (
            "Use system_control for browser tab management via CDP — "
            "list_browser_tabs, close_browser_tab, activate_browser_tab, "
            "navigate_tab."
        )

    # ---- Schedule routing guard ----
    if name != "system_control" and _SCHEDULE_RE.search(goal):
        return (
            "Use system_control for scheduled tasks — list_scheduled_tasks, "
            "create_scheduled_task, remove_scheduled_task."
        )

    # ---- File watch routing guard ----
    if name != "system_control" and _FILE_WATCH_RE.search(goal):
        return (
            "Use system_control for file watching — watch_directory, "
            "list_watchers, stop_watcher."
        )

    # ---- Clipboard history routing guard ----
    if name != "system_control" and _CLIPBOARD_HISTORY_RE.search(goal):
        return (
            "Use system_control for clipboard history — clipboard_history, "
            "clipboard_get, clipboard_copy."
        )

    # ---- Macro recording routing guard ----
    if name != "system_control" and _MACRO_RE.search(goal):
        return (
            "Use system_control for macro recording — macro_start_recording, "
            "macro_stop_recording, macro_play, macro_list."
        )

    # ---- User account routing guard ----
    if name != "system_control" and _USER_ACCOUNT_RE.search(goal):
        return "Use system_control for user account info — list_users, current_user."

    # ---- Docker routing guard ----
    if name != "system_control" and _DOCKER_RE.search(goal):
        return (
            "Use system_control for Docker management — docker_containers, "
            "docker_status, docker_start, docker_stop, docker_restart, "
            "docker_images."
        )

    # ---- LPM (Project management) routing guard ----
    if name != "lpm_control" and _LPM_RE.search(goal):
        return (
            "Use lpm_control for project management — "
            "create_project, create_task, list_tasks, move_task, show_my_tasks, "
            "sprint_health, blocked_tasks, project_status, alerts, etc. "
            "Example: lpm_control action=create_project name=MyApp"
        )

    # ---- Phase 4 — Context / predictive routing guards ----
    if name != "context_agent" and _CONTEXT_RE.search(goal):
        return (
            "Use context_agent action=context for a summary of what you are doing, "
            "your environment, and current PC status."
        )

    if name != "context_agent" and _PREDICT_RE.search(goal):
        return (
            "Use context_agent action=suggest for predictive suggestions based on "
            "your patterns, or action=patterns to see detected activity patterns."
        )

    # ---- Phase 4 — Audio routing guard ----
    if name != "context_agent" and _AUDIO_ROUTE_RE.search(goal):
        return (
            "Use context_agent for audio routing — "
            "action=list_audio_nodes to see all audio devices, "
            "action=connect_audio or disconnect_audio to manage connections, "
            "action=mute_app to mute an app, "
            "action=route_app_to_output to move audio between devices."
        )

    # ---- Phase 4 — Controller / Input device guard ----
    if name != "context_agent" and _CONTROLLER_RE.search(goal):
        return (
            "Use context_agent for game controller and input device detection — "
            "action=list_controllers to detect gamepads, "
            "action=list_input_devices to see all input devices."
        )

    # ---- Email routing guard ----
    if name != "email_control" and _EMAIL_RE.search(goal):
        return (
            "Use email_control for email — send_email, read_inbox, unread_count. "
            "First configure with: email_control action=configure ..."
        )

    # ---- Notes / notebook routing guard ----
    if name != "notes_control" and _NOTES_RE.search(goal):
        return (
            "Use notes_control for notes and notebooks — "
            "create_note, list_notes, get_note, search_notes, etc."
        )

    # ---- Presentation routing guard ----
    if name != "presentation_control" and _PRESENTATION_RE.search(goal):
        return (
            "Use presentation_control to SHOW information visually on screen — "
            "show_title, show_list, show_stats, show_table, show_progress, "
            "show_code, show_text, next_slide, prev_slide."
        )

    # ---- Habits / Goals routing guard ----
    if name != "habits_control" and _HABITS_RE.search(goal):
        return (
            "Use habits_control for habits and goals — "
            "create_habit, list_habits, log_habit, create_goal, "
            "update_goal_progress, habits_stats."
        )

    return None


def default_coding_workspace() -> str:
    return _LUCAS_REPO
