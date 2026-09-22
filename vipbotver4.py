import asyncio
import aiohttp
import traceback
import os
import threading
from telebot.async_telebot import AsyncTeleBot
from flask import Flask

# ================= CẤU HÌNH QUAN TRỌNG =================
# Mã Token Bot Telegram của bạn
BOT_TOKEN = "8666573081:AAHL6YehzVI6I3ZghnsJMxNWZeD_66-FHYc"
RC_PUBLIC_KEY = "appl_JngFETzdodyLmCREOlwTUtXdQik"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VIP_1_NAM_FILE = os.path.join(BASE_DIR, "vip1nam.txt")
VIP_VINH_VIEN_FILE = os.path.join(BASE_DIR, "vipvinhvien.txt")

bot = AsyncTeleBot(BOT_TOKEN)
app = Flask(__name__)

# ================= TRẠNG THÁI HỆ THỐNG =================
STATE = {
    "vips": [],
    "current_vip_uid": None,
    "vip_idx": 0,
    "active_file_name": None
}
# =======================================================

# ----------------- FLASK WEB SERVER -----------------
# Giúp Render nhận diện ứng dụng đang mở port web để không bị tắt
@app.route('/')
def index():
    return "Locket Bot Server is running 24/7!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, use_reloader=False)
# ----------------------------------------------------

def load_vips(file_path: str) -> list[str]:
    if not os.path.exists(file_path):
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write("# Nhập danh sách Username, UID, hoặc Link của các tài khoản VIP ở dưới\n")
                f.write("# Mỗi tài khoản nằm trên 1 dòng.\n")
        except Exception:
            pass
        return []
    
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip() and not line.strip().startswith("#")]
        return lines
    except Exception:
        return []

async def resolve_uid(session: aiohttp.ClientSession, input_val: str) -> str | None:
    input_val = input_val.strip()
    if "locket.camera/links/" in input_val:
        try:
            async with session.get(input_val, allow_redirects=True, timeout=8) as resp:
                input_val = str(resp.url)
        except Exception: pass 

    if "locket.camera/invites/" in input_val:
        try:
            invite_part = input_val.split("locket.camera/invites/")[1].split("?")[0].split("/")[0]
            if len(invite_part) >= 28: return invite_part[:28]
        except Exception: pass

    text = input_val.replace("https://", "").replace("http://", "")
    clean = text.lstrip("@").strip().split("?")[0]
    
    if len(clean) == 28 and " " not in clean and "/" not in clean: return clean
    username = clean.rstrip("/").split("/")[-1] if "locket.cam/" in clean else clean

    url = f"https://locketgold.vn/api/v1/userinfo?user={username}"
    headers = {"accept": "*/*", "referer": "https://locketgold.vn/", "user-agent": "Mozilla/5.0"}

    try:
        async with session.get(url, headers=headers, timeout=8) as resp:
            if resp.status == 200:
                data = await resp.json()
                if isinstance(data, dict):
                    return data.get("uid") or data.get("id") or data.get("user_id") or data.get("data", {}).get("uid")
                elif isinstance(data, str) and len(data.strip()) >= 20:
                    return data.strip()
    except Exception: pass
    return None

async def check_vip_status(session: aiohttp.ClientSession, uid: str) -> tuple[bool, str]:
    url = f"https://api.revenuecat.com/v1/subscribers/{uid}"
    headers = {"Authorization": f"Bearer {RC_PUBLIC_KEY}", "Content-Type": "application/json", "X-Platform": "iOS"}
    try:
        async with session.get(url, headers=headers, timeout=10) as resp:
            data = await resp.json()
            if resp.status == 200:
                entitlements = data.get("subscriber", {}).get("entitlements", {})
                if not entitlements: return False, "Không có gói Gold"
                plans = [f"{name} (HSD: {info.get('expires_date', 'Không rõ')})" for name, info in entitlements.items()]
                return True, " | ".join(plans)
            return False, data.get("message", f"HTTP {resp.status}")
    except Exception as e: return False, f"Lỗi: {str(e)}"

async def alias_users(session: aiohttp.ClientSession, original_uid: str, new_uid: str) -> tuple[bool, str]:
    url = f"https://api.revenuecat.com/v1/subscribers/{original_uid}/alias"
    headers = {"Authorization": f"Bearer {RC_PUBLIC_KEY}", "Content-Type": "application/json", "X-Platform": "iOS"}
    try:
        async with session.post(url, json={"new_app_user_id": new_uid}, headers=headers, timeout=10) as resp:
            data = await resp.json()
            if resp.status in (200, 201): return True, "Đã liên kết quyền lợi Gold thành công!"
            elif resp.status == 429: return False, "Rate Limited (Vui lòng thử lại sau)."
            else: return False, data.get("message", f"HTTP {resp.status}")
    except Exception as e: return False, str(e)

async def get_valid_vip(session: aiohttp.ClientSession, vips: list, start_idx: int) -> tuple[str | None, int]:
    idx = start_idx
    while idx < len(vips):
        clean_vip_source = vips[idx].split("|")[0].strip()
        temp_uid = await resolve_uid(session, clean_vip_source)
        if not temp_uid:
            idx += 1
            continue
        
        is_valid, msg = await check_vip_status(session, temp_uid)
        if not is_valid:
            idx += 1
            continue
        return temp_uid, idx
    return None, idx

# ----------------- GIAO TIẾP TELEGRAM -----------------
@bot.message_handler(commands=['start', 'help'])
async def send_welcome(message):
    text = (
        "👋 Xin chào Admin **Ngô Công Tuấn**!\n"
        "🤖 **TOOL KÍCH HOẠT LOCKET GOLD V4 ĐÃ SẴN SÀNG**\n\n"
        "Vui lòng chọn loại tài nguyên VIP trước khi chạy:\n"
        "👉 Bấm /vip1 - Dùng danh sách Gói 1 Năm\n"
        "👉 Bấm /vip2 - Dùng danh sách Gói Vĩnh Viễn\n\n"
        "Sau khi chọn xong, bạn chỉ cần dán Link hoặc Username của khách vào nhóm chat này để tool tự xử lý."
    )
    await bot.reply_to(message, text, parse_mode='Markdown')

@bot.message_handler(commands=['vip1', 'vip2'])
async def select_vip_list(message):
    command = message.text.strip().lower()
    file_path = VIP_1_NAM_FILE if command == '/vip1' else VIP_VINH_VIEN_FILE
    
    STATE["vips"] = load_vips(file_path)
    STATE["active_file_name"] = os.path.basename(file_path)
    
    if not STATE["vips"]:
        await bot.reply_to(message, f"❌ File `{STATE['active_file_name']}` trống. Vui lòng kiểm tra lại file txt trên GitHub.", parse_mode='Markdown')
        return

    await bot.reply_to(message, f"📂 Đã tải thành công **{len(STATE['vips'])}** tài khoản từ `{STATE['active_file_name']}`. Đang check VIP đầu tiên...", parse_mode='Markdown')
    
    async with aiohttp.ClientSession() as session:
        uid, idx = await get_valid_vip(session, STATE["vips"], 0)
        STATE["current_vip_uid"] = uid
        STATE["vip_idx"] = idx
        
        if uid:
            display_vip = STATE["vips"][idx].split("|")[0].strip()
            await bot.reply_to(message, f"✅ Đã chốt VIP sẵn sàng: `{display_vip}`.\n👉 Dán link khách để quất ngay!", parse_mode='Markdown')
        else:
            await bot.reply_to(message, "❌ Toàn bộ tài khoản trong danh sách này đều lỗi hoặc hết Gold!")

@bot.message_handler(func=lambda message: True)
async def process_customer(message):
    if not STATE["current_vip_uid"]:
        await bot.reply_to(message, "⚠️ Vui lòng gõ lệnh /vip1 hoặc /vip2 để nạp đạn trước khi bắn link khách!")
        return

    raw_text = message.text.strip()
    status_msg = await bot.reply_to(message, "🔄 Đang phân tích thông tin khách hàng...")
    
    async with aiohttp.ClientSession() as session:
        target_uid = await resolve_uid(session, raw_text)
        
        if not target_uid:
            await bot.edit_message_text("❌ Không nhận diện được tài khoản khách. Kiểm tra lại Link/Username!", chat_id=message.chat.id, message_id=status_msg.message_id)
            return
            
        await bot.edit_message_text(f"🎯 Đã bắt được UID khách: `{target_uid}`\n🚀 Đang tiến hành kích hoạt...", chat_id=message.chat.id, message_id=status_msg.message_id, parse_mode='Markdown')
        
        while STATE["current_vip_uid"]:
            display_vip = STATE["vips"][STATE["vip_idx"]].split("|")[0].strip()
            success, detail = await alias_users(session, STATE["current_vip_uid"], target_uid)

            if success:
                result_text = f"✅ **KÍCH HOẠT THÀNH CÔNG!**\n\nVIP Đã Dùng: `{display_vip}`\nKhách Hàng: `{target_uid}`\n\n👉 Copy gửi khách: _Vuốt tắt app Locket trong đa nhiệm rồi mở lại để nhận Gold._"
                await bot.send_message(message.chat.id, result_text, parse_mode='Markdown')
                break 
            else:
                if "Alias limit reached" in detail:
                    await bot.send_message(message.chat.id, f"⚠️ VIP `{display_vip}` đã hết lượt chia sẻ. Hệ thống tự động quét VIP tiếp theo...", parse_mode='Markdown')
                    
                    STATE["vip_idx"] += 1
                    new_uid, new_idx = await get_valid_vip(session, STATE["vips"], STATE["vip_idx"])
                    STATE["current_vip_uid"] = new_uid
                    STATE["vip_idx"] = new_idx
                    
                    if new_uid:
                        await bot.send_message(message.chat.id, f"🚀 Tiếp tục thử lại với VIP mới...")
                        continue 
                    else:
                        await bot.send_message(message.chat.id, f"❌ **ĐÃ CẠN KIỆT VIP TRONG DANH SÁCH `{STATE['active_file_name']}`!** Vui lòng cập nhật thêm.", parse_mode='Markdown')
                        break
                else:
                    await bot.send_message(message.chat.id, f"❌ **THẤT BẠI:** {detail}\n_(Có thể khách này đã từng được share Gold từ chỗ khác)_", parse_mode='Markdown')
                    break

async def main():
    print("Khởi động Bot Telegram...")
    await bot.polling(non_stop=True, request_timeout=90)

if __name__ == "__main__":
    # Khởi chạy Flask Web Server ở một luồng (thread) chạy ngầm
    threading.Thread(target=run_flask, daemon=True).start()
    
    # Khởi chạy Bot Telegram ở luồng chính
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Đã tắt bot.")
    except Exception:
        traceback.print_exc()