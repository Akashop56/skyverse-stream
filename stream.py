import os
import time
import json
import random
import threading
import subprocess
import requests
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont

# --- GITHUB AUTO-LOOP CONFIG ---
START_TIME = time.time()
MAX_DURATION = (5 * 3600) + (45 * 60) # 5 hours 45 minutes
GITHUB_REPO = os.getenv("GITHUB_REPOSITORY") # Auto-provided by GitHub Actions
GH_PAT = os.getenv("GH_PAT")

# --- STREAM CONFIG ---
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
CHANNEL_ID = os.getenv("CHANNEL_ID")
STREAM_KEY = os.getenv("STREAM_KEY")
WIDTH, HEIGHT = 1280, 720
FPS = 30
FONT_PATH = "Montserrat-Bold.ttf"
AUDIO_FILE = "audio.mp3"

state = {
    "subs": 0,
    "goal": 10000,
    "current_text": "Loading SkyVerse...",
    "current_engagement": "Subscribe!",
    "text_start_time": time.time(),
    "duration_per_slide": 6.0 # Fast 6-second rotation for maximum retention
}

def trigger_next_github_action():
    """Triggers the next 6-hour cycle via GitHub API."""
    print("5h 45m reached. Triggering next GitHub Action...")
    if not GH_PAT or not GITHUB_REPO:
        print("Missing GitHub PAT or Repo context. Cannot restart.")
        return

    url = f"https://api.github.com/repos/{GITHUB_REPO}/dispatches"
    headers = {
        "Authorization": f"token {GH_PAT}",
        "Accept": "application/vnd.github.v3+json"
    }
    data = {"event_type": "restart_stream"}
    response = requests.post(url, json=data, headers=headers)
    
    if response.status_code == 204:
        print("Successfully triggered next run. Shutting down gracefully...")
        os._exit(0)
    else:
        print(f"Failed to trigger next run: {response.status_code} - {response.text}")

def fetch_subs():
    while True:
        try:
            url = f"https://www.googleapis.com/youtube/v3/channels?part=statistics&id={CHANNEL_ID}&key={YOUTUBE_API_KEY}"
            response = requests.get(url).json()
            state["subs"] = int(response["items"][0]["statistics"]["subscriberCount"])
        except Exception as e:
            print(f"API Error: {e}")
        time.sleep(60)

def rotate_content():
    with open("content.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    
    while True:
        state["current_text"] = random.choice(data["lines"])["text"]
        state["current_engagement"] = random.choice(data["engagement"])
        state["text_start_time"] = time.time()
        time.sleep(state["duration_per_slide"])

def start_stream():
    font_main = ImageFont.truetype(FONT_PATH, 42)
    font_sub = ImageFont.truetype(FONT_PATH, 32)
    font_small = ImageFont.truetype(FONT_PATH, 20)

    ffmpeg_cmd = [
        'ffmpeg', '-y', '-f', 'rawvideo', '-vcodec', 'rawvideo', '-s', f'{WIDTH}x{HEIGHT}', 
        '-pix_fmt', 'rgb24', '-r', str(FPS), '-i', '-', '-stream_loop', '-1', '-i', AUDIO_FILE, 
        '-c:v', 'libx264', '-preset', 'ultrafast', '-tune', 'zerolatency', 
        '-b:v', '2500k', '-pix_fmt', 'yuv420p', '-g', str(FPS*2),
        '-c:a', 'aac', '-b:a', '128k', '-ar', '44100',
        '-f', 'flv', f"rtmp://a.rtmp.youtube.com/live2/{STREAM_KEY}"
    ]
    process = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE)
    
    # Dark, sleek background
    base_bg = Image.new('RGB', (WIDTH, HEIGHT), color=(10, 10, 12))

    while True:
        # Check if it's time to trigger the next GitHub Action
        if time.time() - START_TIME > MAX_DURATION:
            trigger_next_github_action()

        frame = base_bg.copy()
        draw = ImageDraw.Draw(frame)
        time_alive = time.time() - state["text_start_time"]
        
        # Fast Fade
        opacity = 255
        if time_alive < 0.5: opacity = int(255 * (time_alive * 2))
        elif time_alive > (state["duration_per_slide"] - 0.5): opacity = int(255 * ((state["duration_per_slide"] - time_alive) * 2))
        
        # Center Text with movement
        y_offset = int(15 * (time_alive / state["duration_per_slide"]))
        text_bbox = draw.textbbox((0, 0), state["current_text"], font=font_main)
        text_w = text_bbox[2] - text_bbox[0]
        draw.text(((WIDTH - text_w) // 2, (HEIGHT // 2) - 40 + y_offset), state["current_text"], font=font_main, fill=(opacity, opacity, opacity))
        
        # Viral Element: Visual Countdown Bar (Creates urgency to stay watching)
        progress_ratio = 1.0 - (time_alive / state["duration_per_slide"])
        draw.rectangle([(0, HEIGHT - 10), (int(WIDTH * progress_ratio), HEIGHT)], fill=(255, 50, 80))
        
        # Subscriber Goal UI (Upper Left)
        draw.text((30, 30), f"Road to {state['goal'] // 1000}K Subs 🔥", font=font_sub, fill=(255, 200, 50))
        draw.text((30, 70), f"Current: {state['subs']:,}", font=font_main, fill=(255, 255, 255))
        
        try:
            process.stdin.write(frame.tobytes())
        except BrokenPipeError:
            print("FFmpeg dropped. Restarting pipeline...")
            break
        
        time.sleep(1.0 / FPS)

if __name__ == "__main__":
    threading.Thread(target=fetch_subs, daemon=True).start()
    threading.Thread(target=rotate_content, daemon=True).start()
    while True:
        start_stream()
        time.sleep(3)
