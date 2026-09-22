import asyncio
import aiohttp
import traceback
import os

# ================= CẤU HÌNH QUAN TRỌNG =================
# Public SDK Key từ app iOS
RC_PUBLIC_KEY = "appl_JngFETzdodyLmCREOlwTUtXdQik"

# Cố định đường dẫn file vip.txt luôn nằm cùng thư mục với bot2.py
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VIP_FILE = os.path.join(BASE_DIR, "vip.txt")
# =======================================================

def load_vips(file_path: str) -> list[str]:
    """Đọc danh sách VIP từ file txt. Mỗi dòng 1 tài khoản."""
    if not os.path.exists(file_path):
        # Tự tạo file mẫu nếu chưa tồn tại
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write("# Nhập danh sách Username hoặc UID gốc của các tài khoản VIP ở dưới\n")
                f.write("# Mỗi tài khoản nằm trên 1 dòng. Ví dụ:\n")
                f.write("# admin_vip1\n")
                f.write("# admin_vip2\n")
        except Exception as e:
            print(f"⚠️ Không thể tạo file {file_path}. Lỗi: {e}")
        return []
    
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            # Đọc từng dòng, bỏ qua dòng trống hoặc dòng có dấu # (comment)
            lines = [line.strip() for line in f if line.strip() and not line.strip().startswith("#")]
        return lines
    except Exception as e:
        print(f"⚠️ Không thể đọc file {file_path}. Lỗi: {e}")
        return []

# ... [GIỮ NGUYÊN TOÀN BỘ CÁC HÀM CÒN LẠI BÊN DƯỚI: resolve_uid, check_vip_status, alias_users, get_valid_vip, main] ...

async def resolve_uid(session: aiohttp.ClientSession, input_val: str) -> str | None:
    text = input_val.strip().replace("https://", "").replace("http://", "")
    clean = text.lstrip("@").strip()
    
    if len(clean) == 28 and " " not in clean and "/" not in clean:
        return clean

    if "locket.cam/" in clean:
        username = clean.rstrip("/").split("/")[-1]
    else:
        username = clean

    url = f"https://locketgold.vn/api/v1/userinfo?user={username}"
    headers = {
        "accept": "*/*",
        "referer": "https://locketgold.vn/",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    try:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=8)) as resp:
            if resp.status == 200:
                data = await resp.json()
                if isinstance(data, dict):
                    return data.get("uid") or data.get("id") or data.get("user_id") or data.get("data", {}).get("uid")
                elif isinstance(data, str) and len(data.strip()) >= 20:
                    return data.strip()
    except Exception:
        pass

    return None

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
                    return False, "Không có gói Gold"
                plans = [f"{name} (HSD: {info.get('expires_date', 'Không rõ')})" for name, info in entitlements.items()]
                return True, " | ".join(plans)
            return False, data.get("message", f"HTTP {resp.status}")
    except Exception as e:
        return False, f"Lỗi: {str(e)}"

async def alias_users(session: aiohttp.ClientSession, original_uid: str, new_uid: str) -> tuple[bool, str]:
    url = f"https://api.revenuecat.com/v1/subscribers/{original_uid}/alias"
    headers = {
        "Authorization": f"Bearer {RC_PUBLIC_KEY}",
        "Content-Type": "application/json",
        "X-Platform": "iOS"
    }
    payload = {"new_app_user_id": new_uid}

    try:
        async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            data = await resp.json()
            if resp.status in (200, 201):
                return True, "Đã liên kết quyền lợi Gold thành công!"
            elif resp.status == 429:
                return False, "Rate Limited (Vui lòng thử lại sau)."
            else:
                return False, data.get("message", f"HTTP {resp.status}")
    except Exception as e:
        return False, str(e)

async def get_valid_vip(session: aiohttp.ClientSession, vips: list, start_idx: int) -> tuple[str | None, int]:
    """Hàm chạy qua danh sách VIP để tìm ra UID hợp lệ tiếp theo"""
    idx = start_idx
    while idx < len(vips):
        vip_source = vips[idx]
        print(f"\n🔍 Đang kiểm tra VIP [{idx + 1}/{len(vips)}]: {vip_source}...")
        
        temp_uid = await resolve_uid(session, vip_source)
        if not temp_uid:
            print(f"❌ Không nhận diện được UID. Bỏ qua...")
            idx += 1
            continue
        
        is_valid, msg = await check_vip_status(session, temp_uid)
        if not is_valid:
            print(f"❌ TÀI KHOẢN LỖI: {msg}. Chuyển VIP tiếp theo...")
            idx += 1
            continue
        
        print(f"👑 TÀI KHOẢN VIP SẴN SÀNG: {msg}")
        return temp_uid, idx
    
    return None, idx

async def main():
    print("=" * 65)
    print("TOOL KÍCH HOẠT LOCKET GOLD (TỰ ĐỘNG CHUYỂN VIP TỪ DANH SÁCH)")
    print("=" * 65)

    # Đọc danh sách từ file txt
    vips = load_vips(VIP_FILE)
    if not vips:
        print(f"❌ File '{VIP_FILE}' trống hoặc chưa tồn tại.")
        print(f"👉 Tool đã tạo file '{VIP_FILE}' ở cùng thư mục. Vui lòng mở file, nhập danh sách Username/UID VIP (mỗi dòng 1 tài khoản) rồi mở lại tool.")
        return

    print(f"📂 Đã tải thành công {len(vips)} tài khoản VIP từ file.")

    async with aiohttp.ClientSession() as session:
        vip_idx = 0
        
        # Lấy tài khoản VIP hợp lệ đầu tiên trong file
        current_vip_uid, vip_idx = await get_valid_vip(session, vips, vip_idx)
        
        if not current_vip_uid:
            print("\n❌ Không có tài khoản VIP nào hợp lệ trong danh sách!")
            return

        while True:
            raw_text = input(f"\n👉 Nhập Username khách (hoặc nhập 'q' để thoát): ").strip()

            if raw_text.lower() in ("q", "exit"):
                print("Đã thoát chương trình.")
                break

            if not raw_text:
                continue

            print(f"🔄 Đang tìm thông tin cho: {raw_text}...")
            target_uid = await resolve_uid(session, raw_text)

            if not target_uid:
                print("❌ Không nhận diện được tài khoản khách. Vui lòng kiểm tra lại Username!")
                continue

            print(f"🎯 UID đích khách: {target_uid}")
            
            # Vòng lặp kích hoạt: Cố gắng share Gold bằng VIP hiện tại, nếu lỗi sẽ tự động đổi VIP
            while current_vip_uid:
                print(f"🚀 Đang tiến hành kích hoạt bằng VIP: {vips[vip_idx]}...")
                success, detail = await alias_users(session, current_vip_uid, target_uid)

                if success:
                    print(f"✅ THÀNH CÔNG: {detail}")
                    print("👉 Hướng dẫn khách: Vuốt tắt app Locket trong đa nhiệm rồi mở lại.")
                    break # Hoàn thành cho khách này, thoát vòng lặp kích hoạt
                else:
                    print(f"❌ THẤT BẠI: {detail}")
                    if "Alias limit reached" in detail:
                        print("⚠️ TÀI KHOẢN VIP ĐÃ HẾT LƯỢT CHIA SẺ.")
                        print("🔄 Hệ thống tự động chuyển sang VIP tiếp theo trong danh sách...")
                        
                        # Tăng index và lấy VIP hợp lệ tiếp theo
                        vip_idx += 1
                        current_vip_uid, vip_idx = await get_valid_vip(session, vips, vip_idx)
                        
                        if current_vip_uid:
                            print(f"\n🚀 Tự động thử lại share Gold cho khách {raw_text} bằng VIP mới...")
                            continue # Lặp lại vòng lặp kích hoạt với khách hiện tại nhưng bằng VIP mới
                        else:
                            print("\n❌ ĐÃ CẠN KIỆT TÀI KHOẢN VIP TRONG DANH SÁCH!")
                            break
                    else:
                        print("⚠️ Lỗi không xác định hoặc khách đã từng nhận Gold. Bỏ qua khách này.")
                        break
            
            # Nếu hết sạch VIP trong danh sách thì thoát hẳn tool
            if not current_vip_uid:
                print("👉 Vui lòng cập nhật thêm tài khoản mới vào file 'vip.txt' và chạy lại tool.")
                break

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception:
        traceback.print_exc()
    finally:
        input("\n[Nhấn Enter để đóng]")