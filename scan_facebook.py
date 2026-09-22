import asyncio
import aiohttp
import re
import os
import urllib.parse
import html
from datetime import datetime, timezone

# ================= CẤU HÌNH QUAN TRỌNG =================
RC_PUBLIC_KEY = "appl_JngFETzdodyLmCREOlwTUtXdQik"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, "comments.txt")
OUTPUT_FILE = os.path.join(BASE_DIR, "gold_scanned.txt")
# =======================================================

async def resolve_uid(session: aiohttp.ClientSession, input_val: str) -> tuple[str | None, str | None]:
    """Trả về Tuple: (UID, Username)"""
    input_val = input_val.strip()
    
    text = input_val.replace("https://", "").replace("http://", "")
    clean = text.lstrip("@").strip().split("?")[0]
    
    # Bóc tách Username từ link locket.cam
    if "locket.cam/" in clean:
        username = clean.rstrip("/").split("/")[-1]
    else:
        username = clean

    # Gọi API để lấy UID từ Username
    url = f"https://locketgold.vn/api/v1/userinfo?user={username}"
    headers = {
        "accept": "*/*",
        "referer": "https://locketgold.vn/",
        "user-agent": "Mozilla/5.0"
    }

    try:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=8)) as resp:
            if resp.status == 200:
                data = await resp.json()
                if isinstance(data, dict):
                    uid = data.get("uid") or data.get("id") or data.get("user_id") or data.get("data", {}).get("uid")
                    return uid, username
                elif isinstance(data, str) and len(data.strip()) >= 20:
                    return data.strip(), username
    except Exception:
        pass

    return None, username

async def check_vip_status(session: aiohttp.ClientSession, uid: str) -> tuple[bool, str]:
    url = f"https://api.revenuecat.com/v1/subscribers/{uid}"
    headers = {
        "Authorization": f"Bearer {RC_PUBLIC_KEY}",
        "Content-Type": "application/json",
        "X-Platform": "iOS"
    }
    try:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            data = await resp.json()
            if resp.status == 200:
                entitlements = data.get("subscriber", {}).get("entitlements", {})
                if not entitlements:
                    return False, "Không có Gold"
                
                plans = []
                for name, info in entitlements.items():
                    expires_date_str = info.get('expires_date')
                    
                    if not expires_date_str:
                        plans.append(f"{name} (Vĩnh viễn)")
                    else:
                        try:
                            expires_date_str_clean = expires_date_str.replace('Z', '+00:00')
                            expires_date = datetime.fromisoformat(expires_date_str_clean)
                            now = datetime.now(timezone.utc)
                            
                            days_left = (expires_date - now).days
                            
                            if days_left > 3650: 
                                plans.append(f"{name} (Vĩnh viễn)")
                            elif days_left < 0:
                                plans.append(f"{name} (Đã hết hạn)")
                            else:
                                if expires_date.year > 2050:
                                    plans.append(f"{name} (Vĩnh viễn)")
                                else:
                                    plans.append(f"{name} ({days_left} ngày)")
                        except Exception:
                            plans.append(f"{name} (HSD: {expires_date_str})")

                return True, " | ".join(plans)
            return False, "Không có Gold"
    except Exception:
        return False, "Lỗi kết nối"

def extract_locket_links(text: str) -> list[str]:
    valid_links = set()
    
    text = html.unescape(text)
    text = urllib.parse.unquote(urllib.parse.unquote(text))
    
    # [NÂNG CẤP]: Cắt bỏ locket.camera, CHỈ QUÉT CÁC LINK CÓ ĐỊNH DẠNG locket.cam/username
    pattern = r"(locket\.cam/[a-zA-Z0-9_.-]+)"
    matches = re.findall(pattern, text)
    
    for match in matches:
        valid_links.add(f"https://{match}")
        
    return list(valid_links)

async def process_link(session: aiohttp.ClientSession, link: str, seen_uids: set):
    uid, username = await resolve_uid(session, link)
    if not uid:
        print(f"[-] {link} -> ❌ Không lấy được UID (Bỏ qua)")
        return

    # Lọc trùng lặp nick
    if uid in seen_uids:
        print(f"[-] {link} -> ♻️ Đã bỏ qua (Trùng lặp nick đã quét)")
        return
    
    seen_uids.add(uid)

    is_gold, msg = await check_vip_status(session, uid)
    if is_gold:
        print(f"[+] {link} -> 👑 CÓ GOLD | User: {username} ({msg})")
        with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
            f.write(f"{link} | User: {username} | UID: {uid} | {msg}\n")
    else:
        print(f"[-] {link} -> ❌ Tài khoản thường")

async def main():
    print("=====================================================")
    print(" TOOL QUÉT LOCKET GOLD (CHỈ LẤY LINK CÓ USERNAME) ")
    print("=====================================================")
    
    if not os.path.exists(DATA_FILE):
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            f.write("")
        print(f"⚠️ Đã tạo file '{DATA_FILE}'.")
        print("👉 HƯỚNG DẪN: Chạy Script trên Facebook để lấy file comments.txt rồi chạy lại tool.")
        input("\n[Nhấn Enter để đóng]")
        return

    with open(DATA_FILE, "r", encoding="utf-8") as f:
        content = f.read()

    links = extract_locket_links(content)
    
    if not links:
        print("❌ Không tìm thấy đường link locket.cam/username nào.")
        input("\n[Nhấn Enter để đóng]")
        return

    print(f"🔍 Đã lọc thành công {len(links)} link Locket chứa Username rõ ràng. Bắt đầu quét...\n")
    
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("=== DANH SÁCH LOCKET GOLD QUÉT ĐƯỢC ===\n")

    async with aiohttp.ClientSession() as session:
        tasks = []
        semaphore = asyncio.Semaphore(10)
        seen_uids = set()

        async def sem_task(link):
            async with semaphore:
                await process_link(session, link, seen_uids)

        for link in links:
            tasks.append(sem_task(link))
            
        await asyncio.gather(*tasks)

    print("\n✅ QUÉT HOÀN TẤT!")
    print(f"📂 Các nick có Gold đã được lưu vào file: {OUTPUT_FILE}")

if __name__ == "__main__":
    asyncio.run(main())
    input("\n[Nhấn Enter để đóng]")