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

# --- STREAM SPECS ---
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
    "current_text": "SkyVerse Engine Loading...",
    "current_eng": "Subscribe to join SkyVerse! 🔥",
    "last_update": time.time(),
    "cycle_duration": 8.0 # Thoda slow kiya taaki viewers padh sakein
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
            if state["subs"] >= state["goal"]: state["goal"] += 5000
        except: pass
        time.sleep(60)

def update_content():
    try:
        with open("content.json", "r") as f: data = json.load(f)
    except:
        data = {"lines": [{"text": "Add content.json file!"}], "engagement": ["Subscribe!"]}
        
    while True:
        line = random.choice(data["lines"])
        state["current_text"] = line["text"]
        state["current_eng"] = random.choice(data["engagement"])
        state["last_update"] = time.time()
        time.sleep(state["cycle_duration"])

def get_wrapped_text(text, font, max_width, draw):
    words = text.split()
    lines = []
    current_line = ""
    for word in words:
        test_line = current_line + word + " "
        w = draw.textbbox((0, 0), test_line, font=font)[2]
        if w < max_width:
            current_line = test_line
        else:
            lines.append(current_line)
            current_line = word + " "
    lines.append(current_line)
    return lines

def render_frame(font_main, font_sub, font_small):
    # 1. Cleaner Dark Background
    frame = Image.new('RGB', (WIDTH, HEIGHT), (10, 10, 20))
    draw = ImageDraw.Draw(frame)
    
    # Glow effect
    t = time.time()
    elapsed = t - state["last_update"]
    progress = min(elapsed / state["cycle_duration"], 1.0)
    
    # 2. Main Text (Safe Zone Wrapping)
    # Safe Margin: 100px both sides
    max_text_width = WIDTH - 200
    alpha = 255
    if elapsed < 0.8: alpha = int(255 * (elapsed / 0.8))
    elif elapsed > (state["cycle_duration"] - 0.8): alpha = int(255 * ((state["cycle_duration"] - elapsed) / 0.8))

    lines = get_wrapped_text(state["current_text"], font_main, max_text_width, draw)
    
    line_spacing = 100
    total_text_height = len(lines) * line_spacing
    current_y = (HEIGHT // 2) - (total_text_height // 2)

    for line in lines:
        w = draw.textbbox((0, 0), line.strip(), font=font_main)[2]
        draw.text(((WIDTH - w) // 2, current_y), line.strip(), font=font_main, fill=(255, 255, 255, alpha))
        current_y += line_spacing

    # 3. TOP UI: Better Subscriber Bar
    draw.rounded_rectangle([100, 150, WIDTH-100, 360], radius=25, fill=(30, 30, 50))
    draw.text((150, 190), "SkyVerse Live Status", font=font_small, fill=(0, 200, 255))
    draw.text((150, 235), f"SUBS: {state['subs']:,}", font=font_sub, fill=(255, 255, 255))
    
    # Progress Bar UI
    bar_full_w = WIDTH - 300
    prog_ratio = min(state["subs"] / state["goal"], 1.0)
    draw.rectangle([150, 320, 150+bar_full_w, 335], fill=(50, 50, 70))
    draw.rectangle([150, 320, 150+int(bar_full_w * prog_ratio), 335], fill=(0, 255, 150))
    draw.text((WIDTH-380, 240), f"Goal: {state['goal']//1000}K", font=font_small, fill=(0, 255, 150))

    # 4. BOTTOM UI: Engagement Banner
    draw.rectangle([0, HEIGHT-220, WIDTH, HEIGHT-10], fill=(20, 20, 35))
    eng_w = draw.textbbox((0, 0), state["current_eng"], font=font_small)[2]
    draw.text(((WIDTH-eng_w)//2, HEIGHT-160), state["current_eng"], font=font_small, fill=(255, 215, 0))

    # 5. SYNCED PROGRESS BAR (The Hook)
    # Yeh bar bilkul text change hone ke saath hi khatam hoga
    draw.rectangle([0, HEIGHT-20, int(WIDTH * (1 - progress)), HEIGHT], fill=(255, 60, 90))

    return frame.tobytes()

def start_stream():
    try:
        font_main = ImageFont.truetype(FONT_BOLD, 75)
        font_sub = ImageFont.truetype(FONT_BOLD, 85)
        font_small = ImageFont.truetype(FONT_BOLD, 40)
    except:
        font_main = font_sub = font_small = ImageFont.load_default()

    ffmpeg_cmd = [
        'ffmpeg', '-y', '-f', 'rawvideo', '-vcodec', 'rawvideo', '-s', f'{WIDTH}x{HEIGHT}', 
        '-pix_fmt', 'rgb24', '-r', str(FPS), '-i', '-', '-stream_loop', '-1', '-i', AUDIO_FILE, 
        '-c:v', 'libx264', '-preset', 'ultrafast', '-tune', 'zerolatency', 
        '-b:v', '3000k', '-pix_fmt', 'yuv420p', '-g', '60',
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
