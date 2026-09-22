import asyncio
import aiohttp
import traceback
import os

# ================= CẤU HÌNH QUAN TRỌNG =================
RC_PUBLIC_KEY = "appl_JngFETzdodyLmCREOlwTUtXdQik"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VIP_1_NAM_FILE = os.path.join(BASE_DIR, "vip1nam.txt")
VIP_VINH_VIEN_FILE = os.path.join(BASE_DIR, "vipvinhvien.txt")
# =======================================================

def load_vips(file_path: str) -> list[str]:
    if not os.path.exists(file_path):
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write("# Nhập danh sách Username, UID, hoặc Link của các tài khoản VIP ở dưới\n")
                f.write("# Mỗi tài khoản nằm trên 1 dòng.\n")
        except Exception as e:
            print(f"⚠️ Không thể tạo file {file_path}. Lỗi: {e}")
        return []
    
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip() and not line.strip().startswith("#")]
        return lines
    except Exception as e:
        print(f"⚠️ Không thể đọc file {file_path}. Lỗi: {e}")
        return []

async def resolve_uid(session: aiohttp.ClientSession, input_val: str) -> str | None:
    input_val = input_val.strip()

    if "locket.camera/links/" in input_val:
        try:
            async with session.get(input_val, allow_redirects=True, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                input_val = str(resp.url)
        except Exception:
            pass 

    if "locket.camera/invites/" in input_val:
        try:
            invite_part = input_val.split("locket.camera/invites/")[1].split("?")[0].split("/")[0]
            if len(invite_part) >= 28:
                return invite_part[:28]
        except Exception:
            pass

    text = input_val.replace("https://", "").replace("http://", "")
    clean = text.lstrip("@").strip().split("?")[0]
    
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
        "user-agent": "Mozilla/5.0"
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
    idx = start_idx
    while idx < len(vips):
        raw_vip_source = vips[idx]
        
        # NÂNG CẤP: Tự động lọc bỏ các thông tin dư thừa từ tool quét
        # Lấy phần tử đầu tiên trước dấu "|" (thường là link hoặc UID)
        clean_vip_source = raw_vip_source.split("|")[0].strip()
        
        print(f"\n🔍 Đang kiểm tra VIP [{idx + 1}/{len(vips)}]: {clean_vip_source}...")
        
        temp_uid = await resolve_uid(session, clean_vip_source)
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
    print("=================================================================")
    print("TOOL KÍCH HOẠT LOCKET GOLD (TỰ ĐỘNG CHUYỂN VIP TỪ DANH SÁCH)")
    print("=================================================================\n")

    print("Chọn loại gói Gold bạn muốn share:")
    print("1. Gói 1 Năm (dùng file vip1nam.txt)")
    print("2. Gói Vĩnh Viễn (dùng file vipvinhvien.txt)")
    
    selected_file = None
    while True:
        choice = input("👉 Nhập lựa chọn (1 hoặc 2): ").strip()
        if choice == "1":
            selected_file = VIP_1_NAM_FILE
            break
        elif choice == "2":
            selected_file = VIP_VINH_VIEN_FILE
            break
        else:
            print("❌ Lựa chọn không hợp lệ, vui lòng nhập '1' hoặc '2'.")

    vips = load_vips(selected_file)
    file_name = os.path.basename(selected_file)
    
    if not vips:
        print(f"❌ File '{file_name}' trống hoặc chưa tồn tại.")
        print(f"👉 Tool đã tạo file '{file_name}' ở cùng thư mục. Vui lòng cập nhật danh sách và mở lại tool.")
        return

    print(f"📂 Đã tải thành công {len(vips)} tài khoản VIP từ file {file_name}.")

    async with aiohttp.ClientSession() as session:
        vip_idx = 0
        current_vip_uid, vip_idx = await get_valid_vip(session, vips, vip_idx)
        
        if not current_vip_uid:
            print("\n❌ Không có tài khoản VIP nào hợp lệ trong danh sách!")
            return

        while True:
            raw_text = input(f"\n👉 Nhập Username hoặc dán Link Locket khách (nhập 'q' để thoát): ").strip()

            if raw_text.lower() in ("q", "exit"):
                print("Đã thoát chương trình.")
                break

            if not raw_text:
                continue

            print(f"🔄 Đang tìm và giải mã thông tin...")
            target_uid = await resolve_uid(session, raw_text)

            if not target_uid:
                print("❌ Không nhận diện được tài khoản khách. Vui lòng kiểm tra lại Username/Link!")
                continue

            print(f"🎯 UID đích khách: {target_uid}")
            
            while current_vip_uid:
                # Chỉ in ra thông tin UID/Link cho gọn gàng
                display_vip = vips[vip_idx].split("|")[0].strip()
                print(f"🚀 Đang tiến hành kích hoạt bằng VIP: {display_vip}...")
                success, detail = await alias_users(session, current_vip_uid, target_uid)

                if success:
                    print(f"✅ THÀNH CÔNG: {detail}")
                    print("👉 Hướng dẫn khách: Vuốt tắt app Locket trong đa nhiệm rồi mở lại.")
                    break 
                else:
                    print(f"❌ THẤT BẠI: {detail}")
                    if "Alias limit reached" in detail:
                        print("⚠️ TÀI KHOẢN VIP ĐÃ HẾT LƯỢT CHIA SẺ.")
                        print("🔄 Hệ thống tự động chuyển sang VIP tiếp theo trong danh sách...")
                        
                        vip_idx += 1
                        current_vip_uid, vip_idx = await get_valid_vip(session, vips, vip_idx)
                        
                        if current_vip_uid:
                            print(f"\n🚀 Tự động thử lại share Gold bằng VIP mới...")
                            continue 
                        else:
                            print("\n❌ ĐÃ CẠN KIỆT TÀI KHOẢN VIP TRONG DANH SÁCH!")
                            break
                    else:
                        print("⚠️ Lỗi không xác định hoặc khách đã từng nhận Gold. Bỏ qua khách này.")
                        break
            
            if not current_vip_uid:
                print(f"👉 Vui lòng cập nhật thêm tài khoản mới vào file '{file_name}' và chạy lại tool.")
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