import os
import time
import threading
import subprocess
import requests
import random
import pytchat
from PIL import Image, ImageDraw, ImageFont

# --- SYSTEM CONFIG ---
START_TIME = time.time()
MAX_DURATION = (5 * 3600) + (45 * 60) 
GITHUB_REPO = os.getenv("GITHUB_REPOSITORY")
GH_PAT = os.getenv("GH_PAT")
STREAM_KEY = os.getenv("STREAM_KEY")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
CHANNEL_ID = os.getenv("CHANNEL_ID")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# --- BROADCAST SPECS ---
WIDTH, HEIGHT = 1280, 720
FPS = 30
AUDIO_FILE = "audio.mp3"

# --- NEW GAME STATE (SLOW VOTING SYSTEM) ---
game_state = {
    "score": 0,
    "high_score": 0,
    "player_lane": 2, 
    "obstacle_lane": 2,
    "obstacle_y": -200, # Starts way above screen
    "speed": 1.2,       # VERY SLOW: Takes ~20 seconds to reach bottom
    "crashed": False,
    "crash_time": 0,
    "votes": {1: 0, 2: 0, 3: 0},
    "live_video_id": None,
    "chat_status": "WAITING FOR CONNECTION...",
    "admin_msg": "",       
    "admin_msg_time": 0    
}

# --- TELEGRAM HELPER ---
def send_telegram_msg(text):
    """Sends a message to your Telegram to confirm it's working."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID: return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": text})
    except: pass
# --- 1. TELEGRAM ADMIN CONTROLLER (WITH DEBUG PRINT) ---
def telegram_admin_listener():
    print("Initializing Telegram Bot Listener...")
    send_telegram_msg("🟢 SkyVerse Engine Booted! Send /setvid <VIDEO_ID> to connect chat.")
    offset = None
    while True:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
            params = {"timeout": 30, "offset": offset}
            res = requests.get(url, params=params).json()
            
            # Print response to GitHub logs to see what's happening
            if not res.get("ok"):
                print(f"Telegram API Error Response: {res}")

            for item in res.get("result", []):
                offset = item["update_id"] + 1
                msg = item.get("message", {})
                chat_id = str(msg.get("chat", {}).get("id"))
                
                print(f"Received message from chat_id: {chat_id} (Expected: {TELEGRAM_CHAT_ID})")
                
                # Compare as strings
                if chat_id == str(TELEGRAM_CHAT_ID).strip():
                    text = msg.get("text", "").strip()
                    print(f"Valid Admin Command Received: {text}")
                    
                    if text.startswith("/setvid "):
                        vid = text.replace("/setvid ", "").strip()
                        game_state["live_video_id"] = vid
                        send_telegram_msg(f"✅ Video ID set to: {vid}. Connecting to chat...")
                    elif text.startswith("/msg "):
                        game_state["admin_msg"] = text.replace("/msg ", "")
                        game_state["admin_msg_time"] = time.time()
                        send_telegram_msg("✅ Message displayed on stream!")
                    elif text == "/reset":
                        game_state["score"] = 0
                        game_state["obstacle_y"] = -200
                        game_state["crashed"] = False
                        game_state["votes"] = {1: 0, 2: 0, 3: 0}
                        send_telegram_msg("✅ Game Reset!")
                else:
                    print(f"Ignored message from unauthorized chat_id: {chat_id}")
                    
        except Exception as e:
            print(f"CRITICAL TELEGRAM LISTENER ERROR: {e}")
        time.sleep(2)


# --- 2. AUTO FETCH VIDEO ID ---
def get_live_video_id():
    while not game_state["live_video_id"]:
        try:
            url = f"https://www.googleapis.com/youtube/v3/search?part=id&channelId={CHANNEL_ID}&eventType=live&type=video&key={YOUTUBE_API_KEY}"
            res = requests.get(url).json()
            if "items" in res and len(res["items"]) > 0:
                vid = res["items"][0]["id"]["videoId"]
                game_state["live_video_id"] = vid
                send_telegram_msg(f"✅ Auto-detected live stream: {vid}")
                break
        except: pass
        time.sleep(45)

# --- 3. YOUTUBE LIVE CHAT READER ---
def read_live_chat():
    while not game_state["live_video_id"]:
        time.sleep(2)
        
    game_state["chat_status"] = "CONNECTING..."
    try:
        chat = pytchat.create(video_id=game_state["live_video_id"])
        game_state["chat_status"] = "🟢 CHAT CONNECTED - PLAY NOW!"
        
        while chat.is_alive():
            for c in chat.get().sync_items():
                msg = c.message.strip()
                if msg in ["1", "2", "3"]:
                    game_state["votes"][int(msg)] += 1
            time.sleep(0.5)
    except Exception as e:
        game_state["chat_status"] = f"ERROR: {str(e)[:20]}"
        send_telegram_msg(f"Chat connection failed: {e}")

# --- 4. GAME ENGINE & RENDERING ---
def render_game_frame(font_main, font_small, font_title):
    frame = Image.new('RGB', (WIDTH, HEIGHT), (8, 8, 12))
    draw = ImageDraw.Draw(frame)
    t = time.time()
    
    # Background Grid
    offset = int((t * 50) % 100) # Slower grid for calm feel
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
            game_state["speed"] = 1.2
    else:
        # Move Player to lane with most votes
        highest_vote = max(game_state["votes"].values())
        if highest_vote > 0:
            # Find which lane has the highest votes
            for lane, count in game_state["votes"].items():
                if count == highest_vote:
                    game_state["player_lane"] = lane
                    break

        # Obstacle Logic (Slow Drop)
        game_state["obstacle_y"] += game_state["speed"]
        obs_x = lanes_x[game_state["obstacle_lane"]]
        
        # Draw Obstacle
        if game_state["obstacle_y"] > -50: # Only draw if slightly visible
            draw.rectangle([obs_x - 70, game_state["obstacle_y"] - 30, obs_x + 70, game_state["obstacle_y"] + 30], fill=(255, 40, 60))
        
        # Collision Detection
        player_y = HEIGHT - 150
        if abs(game_state["obstacle_y"] - player_y) < 60:
            if game_state["obstacle_lane"] == game_state["player_lane"]:
                game_state["crashed"] = True
                game_state["crash_time"] = t
            elif game_state["obstacle_y"] > player_y + 60:
                # Survived this obstacle! Reset for next one
                game_state["score"] += 1
                if game_state["score"] > game_state["high_score"]:
                    game_state["high_score"] = game_state["score"]
                game_state["obstacle_y"] = -200
                game_state["obstacle_lane"] = random.choice([1, 2, 3])
                game_state["votes"] = {1: 0, 2: 0, 3: 0} # Reset votes for new block
                game_state["speed"] += 0.1 # Very slight speed increase

        # Player Ship
        px = lanes_x[game_state["player_lane"]]
        py = player_y
        draw.polygon([(px, py - 40), (px - 40, py + 40), (px + 40, py + 40)], fill=(0, 255, 200))

        # --- UI ELEMENTS ---
        # Top Bar
        draw.rectangle([0, 0, WIDTH, 80], fill=(15, 15, 20))
        draw.text((30, 20), f"SCORE: {game_state['score']}", font=font_main, fill=(0, 255, 150))
        draw.text((WIDTH - 400, 20), f"HIGH: {game_state['high_score']}", font=font_main, fill=(255, 200, 0))
        
        # Chat Status Indicator
        status_color = (0, 255, 0) if "CONNECTED" in game_state["chat_status"] else (255, 100, 0)
        draw.text((WIDTH//2 - 150, 30), game_state["chat_status"], font=font_small, fill=status_color)

        # Admin Msg
        if game_state["admin_msg"] and (t - game_state["admin_msg_time"] < 15):
            msg_w = draw.textbbox((0,0), game_state["admin_msg"], font=font_main)[2]
            draw.rectangle([0, 100, WIDTH, 160], fill=(255, 50, 80))
            draw.text(((WIDTH - msg_w)//2, 110), game_state["admin_msg"], font=font_main, fill=(255, 255, 255))
        
        # Footer (LIVE VOTING DASHBOARD)
        draw.rectangle([0, HEIGHT - 80, WIDTH, HEIGHT], fill=(20, 20, 30))
        draw.text((50, HEIGHT - 70), "TYPE TO SAVE THE SHIP:", font=font_small, fill=(255, 255, 255))
        
        # Vote Counters
        v1, v2, v3 = game_state["votes"][1], game_state["votes"][2], game_state["votes"][3]
        draw.text((300, HEIGHT - 45), f"[1] LEFT: {v1} Votes", font=font_small, fill=(255, 255, 0) if game_state["player_lane"]==1 else (200,200,200))
        draw.text((600, HEIGHT - 45), f"[2] CENTER: {v2} Votes", font=font_small, fill=(255, 255, 0) if game_state["player_lane"]==2 else (200,200,200))
        draw.text((900, HEIGHT - 45), f"[3] RIGHT: {v3} Votes", font=font_small, fill=(255, 255, 0) if game_state["player_lane"]==3 else (200,200,200))

    return frame.tobytes()

# --- 5. FFMPEG PIPELINE ---
def trigger_next_run():
    if not GH_PAT or not GITHUB_REPO: return
    url = f"https://api.github.com/repos/{GITHUB_REPO}/dispatches"
    headers = {"Authorization": f"token {GH_PAT}", "Accept": "application/vnd.github.v3+json"}
    requests.post(url, json={"event_type": "restart_stream"}, headers=headers)
    os._exit(0)

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
    
    process = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE)
    
    while True:
        if time.time() - START_TIME > MAX_DURATION:
            trigger_next_run()
            
        frame_data = render_game_frame(font_main, font_small, font_title)
        try:
            process.stdin.write(frame_data)
        except: break
        time.sleep(1/FPS)

if __name__ == "__main__":
    threading.Thread(target=telegram_admin_listener, daemon=True).start()
    threading.Thread(target=get_live_video_id, daemon=True).start()
    threading.Thread(target=read_live_chat, daemon=True).start()
    
    while True:
        start_stream()
        time.sleep(3)
        time.sleep(0.5)

# --- 4. VOTE PROCESSOR ---
def process_votes():
    while True:
        if game_state["recent_votes"] and not game_state["crashed"]:
            vote_counts = Counter(game_state["recent_votes"])
            winning_lane = vote_counts.most_common(1)[0][0]
            game_state["player_lane"] = winning_lane
            game_state["recent_votes"] = [] 
        time.sleep(1.5) 

# --- 5. GAME ENGINE & RENDERING ---
def render_game_frame(font_main, font_small, font_title):
    frame = Image.new('RGB', (WIDTH, HEIGHT), (8, 8, 12))
    draw = ImageDraw.Draw(frame)
    t = time.time()
    
    # Background Grid
    offset = int((t * 150) % 100)
    for y in range(0, HEIGHT, 100):
        draw.line([(0, y + offset), (WIDTH, y + offset)], fill=(20, 20, 35), width=2)
    
    lanes_x = {1: 340, 2: 640, 3: 940}
    draw.line([(490, 0), (490, HEIGHT)], fill=(0, 200, 255), width=2) 
    draw.line([(790, 0), (790, HEIGHT)], fill=(0, 200, 255), width=2) 

    if game_state["crashed"]:
        if (t * 10) % 2 > 1: 
            draw.rectangle([0, 0, WIDTH, HEIGHT], fill=(150, 0, 0))
        draw.text((WIDTH//2 - 200, HEIGHT//2 - 50), "SYSTEM CRASH!", font=font_title, fill=(255, 255, 255))
        if t - game_state["crash_time"] > 3:
            game_state["crashed"] = False
            game_state["obstacles"] = []
            game_state["score"] = 0
            game_state["speed"] = 6.0
    else:
        game_state["score"] += 1
        if game_state["score"] > game_state["high_score"]:
            game_state["high_score"] = game_state["score"]
            
        # Top UI
        draw.rectangle([0, 0, WIDTH, 80], fill=(15, 15, 20))
        draw.text((30, 20), f"SCORE: {game_state['score']}", font=font_main, fill=(0, 255, 150))
        draw.text((WIDTH - 400, 20), f"HIGH: {game_state['high_score']}", font=font_main, fill=(255, 200, 0))
        
        # Admin Announcement Override (God Mode Text)
        if game_state["admin_msg"] and (t - game_state["admin_msg_time"] < 15):
            msg_w = draw.textbbox((0,0), game_state["admin_msg"], font=font_main)[2]
            draw.rectangle([0, 100, WIDTH, 160], fill=(255, 50, 80))
            draw.text(((WIDTH - msg_w)//2, 110), game_state["admin_msg"], font=font_main, fill=(255, 255, 255))
        
        # Footer Instructions
        draw.rectangle([0, HEIGHT - 50, WIDTH, HEIGHT], fill=(20, 20, 30))
        draw.text((300, HEIGHT - 35), "SPAM IN CHAT:   [1] LEFT   |   [2] CENTER   |   [3] RIGHT", font=font_small, fill=(255, 255, 255))

        # Obstacles Logic
        if random.random() < 0.02 + (game_state["speed"] / 1000): 
            game_state["obstacles"].append({"lane": random.choice([1, 2, 3]), "y": -50})
            
        for obs in game_state["obstacles"]:
            obs["y"] += game_state["speed"]
            obs_x = lanes_x[obs["lane"]]
            draw.rectangle([obs_x - 60, obs["y"] - 20, obs_x + 60, obs["y"] + 20], fill=(255, 40, 60))
            
            # Collision
            player_y = HEIGHT - 120
            if obs["lane"] == game_state["player_lane"] and abs(obs["y"] - player_y) < 50:
                game_state["crashed"] = True
                game_state["crash_time"] = t
                break
                
        game_state["obstacles"] = [obs for obs in game_state["obstacles"] if obs["y"] < HEIGHT]
        game_state["speed"] += 0.002

        # Player Ship
        px = lanes_x[game_state["player_lane"]]
        py = HEIGHT - 120
        draw.polygon([(px, py - 35), (px - 35, py + 35), (px + 35, py + 35)], fill=(0, 255, 200))

    return frame.tobytes()

# --- 6. FFMPEG PIPELINE ---
def trigger_next_run():
    if not GH_PAT or not GITHUB_REPO: return
    url = f"https://api.github.com/repos/{GITHUB_REPO}/dispatches"
    headers = {"Authorization": f"token {GH_PAT}", "Accept": "application/vnd.github.v3+json"}
    requests.post(url, json={"event_type": "restart_stream"}, headers=headers)
    os._exit(0)

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
    
    process = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE)
    
    while True:
        if time.time() - START_TIME > MAX_DURATION:
            trigger_next_run()
            
        frame_data = render_game_frame(font_main, font_small, font_title)
        try:
            process.stdin.write(frame_data)
        except: break
        time.sleep(1/FPS)

if __name__ == "__main__":
    # Launching all threads simultaneously 
    threading.Thread(target=telegram_admin_listener, daemon=True).start()
    threading.Thread(target=get_live_video_id, daemon=True).start()
    threading.Thread(target=read_live_chat, daemon=True).start()
    threading.Thread(target=process_votes, daemon=True).start()
    
    while True:
        start_stream()
        time.sleep(3)

