import os
import sys
import time
import threading
import subprocess
import requests
import random
import pytchat
from PIL import Image, ImageDraw, ImageFont

print("🚀 SYSTEM BOOTING UP...", flush=True)

# --- SYSTEM CONFIG & SECRETS STRIPPING ---
START_TIME = time.time()
MAX_DURATION = (5 * 3600) + (45 * 60) 
GITHUB_REPO = os.getenv("GITHUB_REPOSITORY")
GH_PAT = os.getenv("GH_PAT")

STREAM_KEY = str(os.getenv("STREAM_KEY", "")).strip()
YOUTUBE_API_KEY = str(os.getenv("YOUTUBE_API_KEY", "")).strip()
CHANNEL_ID = str(os.getenv("CHANNEL_ID", "")).strip()
TELEGRAM_BOT_TOKEN = str(os.getenv("TELEGRAM_BOT_TOKEN", "")).strip()

# 🔥 FIX: HARDCODED YOUR EXACT CHAT ID (Bypasses GitHub Secrets)
TELEGRAM_CHAT_ID = "8921734624"

print(f"🔍 API Keys Checked. Telegram Token starts with: {TELEGRAM_BOT_TOKEN[:5]}...", flush=True)

# --- BROADCAST SPECS ---
WIDTH, HEIGHT = 1280, 720
FPS = 30
AUDIO_FILE = "audio.mp3"

# --- GAME STATE ---
game_state = {
    "score": 0, "high_score": 0, "player_lane": 2, "obstacle_lane": 2,
    "obstacle_y": -200, "speed": 1.5, "crashed": False, "crash_time": 0,
    "votes": {1: 0, 2: 0, 3: 0}, "live_video_id": None,
    "chat_status": "WAITING FOR ADMIN (TG) TO CONNECT...",
    "admin_msg": "", "admin_msg_time": 0    
}

# --- TELEGRAM HELPER ---
def send_telegram_msg(text):
    if not TELEGRAM_BOT_TOKEN: 
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": text}, timeout=10)
    except Exception as e: 
        print(f"❌ TG Send Error: {e}", flush=True)

# --- 1. TELEGRAM ADMIN CONTROLLER ---
def telegram_admin_listener():
    print("🟢 Initializing Telegram Bot Listener Thread...", flush=True)
    send_telegram_msg("🟢 SkyVerse Engine Booted! Send /setvid <VIDEO_ID> to connect chat.")
    offset = None
    while True:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
            params = {"timeout": 30, "offset": offset}
            res = requests.get(url, params=params).json()
            
            for item in res.get("result", []):
                offset = item["update_id"] + 1
                msg = item.get("message", {})
                chat_id = str(msg.get("chat", {}).get("id")).strip()
                text = msg.get("text", "").strip()
                
                print(f"📩 TG Command from {chat_id}: {text}", flush=True)
                
                # Direct match with your Hardcoded ID
                if chat_id == TELEGRAM_CHAT_ID:
                    # 🔥 FIX: Flexible Command Matching (Ignores invisible spaces)
                    if "/setvid" in text:
                        # Extracts the last word (the Video ID) perfectly
                        vid = text.split()[-1].strip()
                        game_state["live_video_id"] = vid
                        send_telegram_msg(f"✅ Video ID set to: {vid}. Connecting to YouTube chat...")
                        print(f"🔥 Video ID manually set via TG: {vid}", flush=True)
                    elif "/msg" in text:
                        # Extract message after /msg
                        admin_text = text.split("/msg")[-1].strip()
                        game_state["admin_msg"] = admin_text
                        game_state["admin_msg_time"] = time.time()
                        send_telegram_msg("✅ Banner displayed!")
                    elif "/reset" in text:
                        game_state["score"] = 0
                        game_state["obstacle_y"] = -200
                        game_state["crashed"] = False
                        game_state["votes"] = {1: 0, 2: 0, 3: 0}
                        send_telegram_msg("✅ Game Reset!")
        except Exception as e: 
            pass
        time.sleep(2)

# --- 2. YOUTUBE LIVE CHAT READER ---
def read_live_chat():
    print("🟢 Chat Listener Thread Started. Waiting for Video ID...", flush=True)
    while not game_state["live_video_id"]:
        time.sleep(2)
        
    game_state["chat_status"] = "CONNECTING TO CHAT..."
    try:
        chat = pytchat.create(video_id=game_state["live_video_id"])
        game_state["chat_status"] = "🟢 CHAT CONNECTED - PLAY NOW!"
        print("✅ Pytchat successfully connected!", flush=True)
        
        while chat.is_alive():
            for c in chat.get().sync_items():
                msg = c.message.strip()
                if msg in ["1", "2", "3"]:
                    game_state["votes"][int(msg)] += 1
            time.sleep(0.5)
    except Exception as e:
        game_state["chat_status"] = "ERROR CONNECTING CHAT"
        send_telegram_msg(f"Chat connection failed: {e}")
        print(f"❌ Chat connection failed: {e}", flush=True)

# --- 3. GAME ENGINE & RENDERING ---
def render_game_frame(font_main, font_small, font_title):
    frame = Image.new('RGB', (WIDTH, HEIGHT), (8, 8, 12))
    draw = ImageDraw.Draw(frame)
    t = time.time()
    
    offset = int((t * 50) % 100)
    for y in range(0, HEIGHT, 100):
        draw.line([(0, y + offset), (WIDTH, y + offset)], fill=(20, 20, 35), width=2)
    
    lanes_x = {1: 340, 2: 640, 3: 940}
    draw.line([(490, 0), (490, HEIGHT)], fill=(0, 200, 255), width=2) 
    draw.line([(790, 0), (790, HEIGHT)], fill=(0, 200, 255), width=2) 

    if game_state["crashed"]:
        if (t * 10) % 2 > 1: 
            draw.rectangle([0, 0, WIDTH, HEIGHT], fill=(150, 0, 0))
        draw.text((WIDTH//2 - 200, HEIGHT//2 - 50), "SYSTEM CRASH!", font=font_title, fill=(255, 255, 255))
        if t - game_state["crash_time"] > 4:
            game_state["crashed"] = False
            game_state["obstacle_y"] = -200
            game_state["score"] = 0
            game_state["votes"] = {1: 0, 2: 0, 3: 0}
            game_state["speed"] = 1.5
    else:
        highest_vote = max(game_state["votes"].values())
        if highest_vote > 0:
            for lane, count in game_state["votes"].items():
                if count == highest_vote:
                    game_state["player_lane"] = lane
                    break

        game_state["obstacle_y"] += game_state["speed"]
        obs_x = lanes_x[game_state["obstacle_lane"]]
        
        if game_state["obstacle_y"] > -50:
            draw.rectangle([obs_x - 70, game_state["obstacle_y"] - 30, obs_x + 70, game_state["obstacle_y"] + 30], fill=(255, 40, 60))
        
        player_y = HEIGHT - 150
        if abs(game_state["obstacle_y"] - player_y) < 60:
            if game_state["obstacle_lane"] == game_state["player_lane"]:
                game_state["crashed"] = True
                game_state["crash_time"] = t
            elif game_state["obstacle_y"] > player_y + 60:
                game_state["score"] += 1
                if game_state["score"] > game_state["high_score"]:
                    game_state["high_score"] = game_state["score"]
                game_state["obstacle_y"] = -200
                game_state["obstacle_lane"] = random.choice([1, 2, 3])
                game_state["votes"] = {1: 0, 2: 0, 3: 0} 
                game_state["speed"] += 0.1 

        px = lanes_x[game_state["player_lane"]]
        py = player_y
        draw.polygon([(px, py - 40), (px - 40, py + 40), (px + 40, py + 40)], fill=(0, 255, 200))

        draw.rectangle([0, 0, WIDTH, 80], fill=(15, 15, 20))
        draw.text((30, 20), f"SCORE: {game_state['score']}", font=font_main, fill=(0, 255, 150))
        
        status_color = (0, 255, 0) if "CONNECTED" in game_state["chat_status"] else (255, 100, 0)
        draw.text((WIDTH//2 - 250, 30), game_state["chat_status"], font=font_small, fill=status_color)

        if game_state["admin_msg"] and (t - game_state["admin_msg_time"] < 15):
            draw.rectangle([0, 100, WIDTH, 160], fill=(255, 50, 80))
            draw.text((WIDTH//2 - 100, 110), game_state["admin_msg"], font=font_main, fill=(255, 255, 255))
        
        draw.rectangle([0, HEIGHT - 80, WIDTH, HEIGHT], fill=(20, 20, 30))
        draw.text((50, HEIGHT - 70), "SPAM TO DODGE:", font=font_small, fill=(255, 255, 255))
        
        v1, v2, v3 = game_state["votes"][1], game_state["votes"][2], game_state["votes"][3]
        draw.text((300, HEIGHT - 45), f"[1] LEFT: {v1}", font=font_small, fill=(255, 255, 0) if game_state["player_lane"]==1 else (200,200,200))
        draw.text((600, HEIGHT - 45), f"[2] CENTER: {v2}", font=font_small, fill=(255, 255, 0) if game_state["player_lane"]==2 else (200,200,200))
        draw.text((900, HEIGHT - 45), f"[3] RIGHT: {v3}", font=font_small, fill=(255, 255, 0) if game_state["player_lane"]==3 else (200,200,200))

    return frame.tobytes()

# --- 4. FFMPEG PIPELINE ---
def start_stream():
    try:
        font_title = ImageFont.truetype("Montserrat-Bold.ttf", 70)
        font_main = ImageFont.truetype("Montserrat-Bold.ttf", 40)
        font_small = ImageFont.truetype("Montserrat-Bold.ttf", 22)
    except:
        font_title = font_main = font_small = ImageFont.load_default()

    ffmpeg_cmd = [
        'ffmpeg', '-y', '-f', 'rawvideo', '-vcodec', 'rawvideo', '-s', f'{WIDTH}x{HEIGHT}', 
        '-pix_fmt', 'rgb24', '-r', str(FPS), '-i', '-', '-stream_loop', '-1', '-i', AUDIO_FILE, 
        '-c:v', 'libx264', '-preset', 'ultrafast', '-tune', 'zerolatency', 
        '-b:v', '2500k', '-maxrate', '2500k', '-bufsize', '5000k',
        '-pix_fmt', 'yuv420p', '-g', '60',
        '-c:a', 'aac', '-b:a', '128k', '-ar', '44100',
        '-f', 'flv', f"rtmp://a.rtmp.youtube.com/live2/{STREAM_KEY}"
    ]
    
    print("🎬 Starting FFmpeg...", flush=True)
    process = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
    
    while True:
        frame_data = render_game_frame(font_main, font_small, font_title)
        try:
            process.stdin.write(frame_data)
        except: 
            print("⚠️ FFmpeg Pipe Broken!", flush=True)
            break
        time.sleep(1/FPS)

if __name__ == "__main__":
    threading.Thread(target=telegram_admin_listener, daemon=True).start()
    threading.Thread(target=read_live_chat, daemon=True).start()
    
    while True:
        start_stream()
        time.sleep(3)
