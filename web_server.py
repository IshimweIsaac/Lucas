import os
import sys
import json
import asyncio
import platform
import subprocess
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends, Header
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import psutil

# Core Lucas Modules
from agent.executor import AgentExecutor
import google.generativeai as genai

app = FastAPI(title="LUCAS Remote Control Server")

# Enable CORS for local/remote devices
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from core.logger import get_logger
from memory.config_manager import get_gemini_key

logger = get_logger(__name__)

async def verify_api_key(x_api_key: str = Header(None)):
    expected = get_gemini_key()
    if not expected:
        raise HTTPException(status_code=401, detail="Server not configured with API key")
    if x_api_key != expected:
        raise HTTPException(status_code=401, detail="Invalid API Key")

# Configure Gemini for Voice Transcriptions
genai.configure(api_key=get_gemini_key())
transcribe_model = genai.GenerativeModel("gemini-3.1-flash-lite-preview")

class ChatRequest(BaseModel):
    query: str

class ControlRequest(BaseModel):
    action: str

# Helper to capture accumulated speak events
class WebSpeechCollector:
    def __init__(self):
        self.texts = []

    def __call__(self, text: str):
        self.texts.append(text)
        print(f"[Lucas Speech] {text}")

    def get_full_speech(self) -> str:
        return " ".join(self.texts).strip()

@app.post("/api/chat", dependencies=[Depends(verify_api_key)])
async def api_chat(request: ChatRequest):
    """Executes a text command received from the phone."""
    query = request.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Empty query")

    collector = WebSpeechCollector()
    executor = AgentExecutor()
    
    # Run the executor in a worker thread to prevent blocking the event loop
    loop = asyncio.get_event_loop()
    summary = await loop.run_in_executor(
        None, 
        lambda: executor.execute(goal=query, speak=collector)
    )

    full_speech = collector.get_full_speech()
    if not full_speech:
        full_speech = summary

    return {
        "success": True,
        "query": query,
        "summary": summary,
        "speech": full_speech
    }

@app.post("/api/voice", dependencies=[Depends(verify_api_key)])
async def api_voice(file: UploadFile = File(...)):
    """Transcribes WebM/WAV voice upload using Gemini and executes it."""
    try:
        audio_bytes = await file.read()
        
        # Call Gemini to transcribe the audio content natively
        response = transcribe_model.generate_content([
            "Transcribe this speech query exactly into English text. "
            "Return ONLY the transcribed text, with no markdown, punctuation explanations, or extra commentary.",
            {"mime_type": file.content_type or "audio/webm", "data": audio_bytes}
        ])
        
        transcription = response.text.strip()
        print(f"[Voice Upload] Transcribed: {transcription}")
        
        if not transcription or "error" in transcription.lower():
            raise HTTPException(status_code=400, detail="Speech could not be understood.")

        # Execute transcription
        collector = WebSpeechCollector()
        executor = AgentExecutor()
        
        loop = asyncio.get_event_loop()
        summary = await loop.run_in_executor(
            None, 
            lambda: executor.execute(goal=transcription, speak=collector)
        )

        full_speech = collector.get_full_speech()
        if not full_speech:
            full_speech = summary

        return {
            "success": True,
            "query": transcription,
            "summary": summary,
            "speech": full_speech
        }
    except Exception as e:
        logger.error("Voice API error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/screenshot", dependencies=[Depends(verify_api_key)])
async def api_screenshot():
    """Takes a live screenshot of the PC desktop and streams it back."""
    import io
    try:
        import pyautogui
        # Make screenshot size smaller for fast remote network streaming
        img = pyautogui.screenshot()
        img = img.convert("RGB")
        img.thumbnail((800, 450)) # 16:9 ratio, smaller file size
        
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=75)
        buffer.seek(0)
        return StreamingResponse(buffer, media_type="image/jpeg")
    except Exception as e:
        logger.error("Screenshot error: %s", e)
        raise HTTPException(status_code=500, detail="Could not capture desktop screenshot.")

@app.get("/api/status", dependencies=[Depends(verify_api_key)])
async def api_status():
    """Returns basic hardware and OS window stats."""
    cpu = psutil.cpu_percent()
    ram = psutil.virtual_memory().percent
    
    # Try to find the active foreground window
    active_window = "Desktop"
    try:
        if platform.system() == "Linux":
            # Active window name on X11 / GNOME
            res = subprocess.run(["xdotool", "getactivewindow", "getwindowname"], capture_output=True, text=True)
            if res.returncode == 0 and res.stdout.strip():
                active_window = res.stdout.strip()
        elif platform.system() == "Windows":
            import win32gui
            active_window = win32gui.GetWindowText(win32gui.GetForegroundWindow())
    except Exception as exc:
        logger.debug("Could not get active window: %s", exc)

    return {
        "cpu": cpu,
        "ram": ram,
        "active_window": active_window,
        "os": platform.system()
    }

@app.post("/api/control", dependencies=[Depends(verify_api_key)])
async def api_control(request: ControlRequest):
    """Performs quick immediate PC settings control actions."""
    action = request.action.lower().strip()
    try:
        import pyautogui
        if action == "vol_up":
            pyautogui.press("volumeup")
            return {"success": True, "message": "Volume increased."}
        elif action == "vol_down":
            pyautogui.press("volumedown")
            return {"success": True, "message": "Volume decreased."}
        elif action == "mute":
            pyautogui.press("volumemute")
            return {"success": True, "message": "Volume muted/unmuted."}
        elif action == "play_pause":
            pyautogui.press("playpause")
            return {"success": True, "message": "Media state toggled."}
        elif action == "lock_pc":
            _lock_computer()
            return {"success": True, "message": "PC Locked."}
        else:
            raise HTTPException(status_code=400, detail="Invalid action")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def _lock_computer():
    sys_type = platform.system()
    if sys_type == "Windows":
        import ctypes
        ctypes.windll.user32.LockWorkStation()
    elif sys_type == "Darwin":
        subprocess.run(["pmset", "displaysleepnow"])
    else:
        # Linux
        lockers = [
            ["xdg-screensaver", "lock"],
            ["gnome-screensaver-command", "-l"],
            ["dbus-send", "--type=method_call", "--dest=org.gnome.ScreenSaver", "/org/gnome/ScreenSaver", "org.gnome.ScreenSaver.Lock"],
            ["loginctl", "lock-session"]
        ]
        for cmd in lockers:
            try:
                subprocess.run(cmd, capture_output=True)
                break
            except Exception:
                continue

# Serve static files at root
app.mount("/", StaticFiles(directory="static", html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    import socket

    # Automatically find host IP to present QR connection instructions
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
    except Exception:
        local_ip = "127.0.0.1"
    finally:
        s.close()

    print("\n" + "="*60)
    print(f"🚀 LUCAS REMOTE WEB SERVER STARTED SUCCESSFULLY!")
    print(f"🔗 Access the web app locally: http://localhost:8000")
    print(f"📱 Connect from your mobile phone: http://{local_ip}:8000")
    print("="*60 + "\n")

    uvicorn.run(app, host="127.0.0.1", port=8000)
