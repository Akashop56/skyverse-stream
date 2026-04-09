import os
import time
import json
import random
import threading
import subprocess
import requests
from PIL import Image, ImageDraw, ImageFont, ImageFilter

# --- CLOUD & LOOP CONFIG ---
START_TIME = time.time()
MAX_DURATION = (5 * 3600) + (45 * 60) # 5h 45m handoff
GITHUB_REPO = os.getenv("GITHUB_REPOSITORY")
GH_PAT = os.getenv("GH_PAT")

# --- STREAM SPECS (VERTICAL IS KEY FOR VIRAL REACH) ---
WIDTH, HEIGHT = 1080, 1920 
FPS = 30
STREAM_KEY = os.getenv("STREAM_KEY")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
CHANNEL_ID = os.getenv("CHANNEL_ID")
FONT_BOLD = "Montserrat-Bold.ttf"
AUDIO_FILE = "audio.mp3"

state = {
    "subs": 0,
    "goal": 10000,
    "current_text": "Starting SkyVerse...",
    "current_eng": "Subscribe for more! 🔥",
    "last_update": time.time(),
    "cycle_duration": 7.0 # Fast rotation for retention
}

def trigger_next_run():
    if not GH_PAT or not GITHUB_REPO: return
    url = f"https://api.github.com/repos/{GITHUB_REPO}/dispatches"
    headers = {"Authorization": f"token {GH_PAT}", "Accept": "application/vnd.github.v3+json"}
    requests.post(url, json={"event_type": "restart_stream"}, headers=headers)
    os._exit(0)

def get_live_subs():
    while True:
        try:
            url = f"https://www.googleapis.com/youtube/v3/channels?part=statistics&id={CHANNEL_ID}&key={YOUTUBE_API_KEY}"
            data = requests.get(url).json()
            state["subs"] = int(data["items"][0]["statistics"]["subscriberCount"])
            # Auto-increment goal
            if state["subs"] >= state["goal"]: state["goal"] += 5000
        except: pass
        time.sleep(60)

def update_content():
    with open("content.json", "r") as f: data = json.load(f)
    while True:
        line = random.choice(data["lines"])
        state["current_text"] = line["text"]
        state["current_eng"] = random.choice(data["engagement"])
        state["last_update"] = time.time()
        time.sleep(state["cycle_duration"])

def render_frame(font_main, font_sub, font_small):
    # 1. Create Deep Gradient Background
    frame = Image.new('RGB', (WIDTH, HEIGHT), (10, 10, 15))
    draw = ImageDraw.Draw(frame)
    
    # Simple Animated Background Effect (Drifting light)
    t = time.time()
    glow_y = int(500 + 100 * (t % 10 / 10))
    draw.ellipse([(-200, glow_y), (WIDTH+200, glow_y+800)], fill=(20, 25, 50))

    # 2. Timing & Animation Logic
    elapsed = t - state["last_update"]
    progress = elapsed / state["cycle_duration"]
    
    # Professional Fade & Scale
    alpha = 255
    if elapsed < 0.8: alpha = int(255 * (elapsed / 0.8))
    elif elapsed > (state["cycle_duration"] - 0.8): alpha = int(255 * ((state["cycle_duration"] - elapsed) / 0.8))
    
    # 3. DRAW MAIN TEXT (Safe Zone: Middle)
    scale = 1.0 + (elapsed * 0.02) # Subtle zoom-in effect
    font_size = int(65 * scale)
    try: font_dyn = ImageFont.truetype(FONT_BOLD, font_size)
    except: font_dyn = font_main
    
    # Multiline text wrapping
    max_w = WIDTH - 150
    words = state["current_text"].split()
    lines = []
    current_line = ""
    for w in words:
        if draw.textbbox((0,0), current_line + w, font=font_dyn)[2] < max_w:
            current_line += w + " "
        else:
            lines.append(current_line)
            current_line = w + " "
    lines.append(current_line)

    y_start = (HEIGHT // 2) - (len(lines) * 40)
    for i, line in enumerate(lines):
        w = draw.textbbox((0,0), line, font=font_dyn)[2]
        draw.text(((WIDTH-w)//2, y_start + (i*90)), line, font=font_dyn, fill=(255, 255, 255, alpha))

    # 4. TOP UI: Sub Counter & Road to 10K
    # Glassmorphism box
    draw.rounded_rectangle([100, 150, WIDTH-100, 350], radius=20, fill=(30, 30, 45))
    draw.text((150, 190), "SkyVerse Live", font=font_small, fill=(200, 200, 255))
    draw.text((150, 230), f"{state['subs']:,}", font=font_sub, fill=(255, 255, 255))
    
    # Progress Bar
    bar_width = WIDTH - 300
    goal_prog = min(state["subs"] / state["goal"], 1.0)
    draw.rectangle([150, 310, 150+bar_width, 320], fill=(50, 50, 60))
    draw.rectangle([150, 310, 150+int(bar_width * goal_prog), 320], fill=(0, 200, 255))
    draw.text((WIDTH-350, 235), f"Road to {state['goal']//1000}K", font=font_small, fill=(0, 200, 255))

    # 5. BOTTOM UI: Engagement Banner
    draw.rectangle([0, HEIGHT-200, WIDTH, HEIGHT], fill=(20, 20, 30))
    eng_w = draw.textbbox((0,0), state["current_eng"], font=font_sub)[2]
    draw.text(((WIDTH-eng_w)//2, HEIGHT-140), state["current_eng"], font=font_sub, fill=(255, 200, 0))

    # Countdown bar (The "Don't Leave" Trigger)
    draw.rectangle([0, HEIGHT-10, int(WIDTH * (1-progress)), HEIGHT], fill=(255, 50, 50))

    return frame.tobytes()

def start_stream():
    font_main = ImageFont.truetype(FONT_BOLD, 65)
    font_sub = ImageFont.truetype(FONT_BOLD, 80)
    font_small = ImageFont.truetype(FONT_BOLD, 35)

    ffmpeg_cmd = [
        'ffmpeg', '-y', '-f', 'rawvideo', '-vcodec', 'rawvideo', '-s', f'{WIDTH}x{HEIGHT}', 
        '-pix_fmt', 'rgb24', '-r', str(FPS), '-i', '-', '-stream_loop', '-1', '-i', AUDIO_FILE, 
        '-c:v', 'libx264', '-preset', 'ultrafast', '-tune', 'zerolatency', 
        '-b:v', '4500k', '-pix_fmt', 'yuv420p', '-g', '60',
        '-c:a', 'aac', '-b:a', '128k', '-ar', '44100',
        '-f', 'flv', f"rtmp://a.rtmp.youtube.com/live2/{STREAM_KEY}"
    ]
    
    process = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE)
    
    while True:
        if time.time() - START_TIME > MAX_DURATION:
            trigger_next_run()
            
        frame_data = render_frame(font_main, font_sub, font_small)
        try:
            process.stdin.write(frame_data)
        except:
            break
        time.sleep(1/FPS)

if __name__ == "__main__":
    threading.Thread(target=get_live_subs, daemon=True).start()
    threading.Thread(target=update_content, daemon=True).start()
    start_stream()
