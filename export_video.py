import os
import sys
import glob
import subprocess

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

def get_ffmpeg():
    try:
        import static_ffmpeg
        static_ffmpeg.add_paths()
    except Exception:
        pass
    import shutil
    return shutil.which("ffmpeg")

def find_latest_video():
    folders = [r"D:\Downloads", os.getcwd()]
    for f in folders:
        if os.path.exists(f):
            # Tìm file blurred trước, nếu không có thì tìm mp4 thường
            blurred = glob.glob(os.path.join(f, "*blurred*.mp4"))
            if blurred:
                return blurred[0]
            mp4s = glob.glob(os.path.join(f, "*.mp4"))
            valid = [v for v in mp4s if not v.endswith("_Subbed.mp4")]
            if valid:
                return valid[0]
    return None

def find_matching_sub(video_path):
    base, _ = os.path.splitext(video_path)
    base_clean = base.replace("_blurred", "").replace("- blurred", "").strip()

    candidates = [
        f"{base}.ass",
        f"{base}_vi.ass",
        f"{base_clean}_vi.ass",
        f"{base_clean}.ass",
        f"{base}.srt",
        f"{base}_vi.srt",
        f"{base_clean}_vi.srt",
        f"{base_clean}.srt"
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
            
    # Quét bất kỳ file .ass nào trong cùng thư mục
    folder = os.path.dirname(video_path)
    ass_files = glob.glob(os.path.join(folder, "*.ass"))
    if ass_files:
        return ass_files[0]
    srt_files = glob.glob(os.path.join(folder, "*_vi.srt"))
    if srt_files:
        return srt_files[0]
    return None

def export_subbed_video(video_path=None, sub_path=None, output_path=None):
    if not video_path:
        video_path = find_latest_video()

    if not video_path or not os.path.exists(video_path):
        print("Lỗi: Không tìm thấy file video nào trong thư mục D:\\Downloads!")
        return

    if not sub_path:
        sub_path = find_matching_sub(video_path)

    if not sub_path or not os.path.exists(sub_path):
        print(f"Lỗi: Không tìm thấy file phụ đề (.ass hoặc .srt) tương ứng cho video '{video_path}'")
        return

    if not output_path:
        folder = os.path.dirname(video_path)
        base_name = os.path.basename(video_path)
        name_no_ext, ext = os.path.splitext(base_name)
        clean_name = name_no_ext.replace("_blurred", "")
        output_path = os.path.join(folder, f"{clean_name}_Subbed{ext}")

    ffmpeg = get_ffmpeg()
    if not ffmpeg:
        print("Lỗi: Không tìm thấy ffmpeg trên máy.")
        return

    # Chuẩn hóa đường dẫn cho filter của ffmpeg trên Windows
    sub_clean_path = os.path.abspath(sub_path).replace("\\", "/").replace(":", "\\:")

    print("=" * 60)
    print("           BẮT ĐẦU XUẤT VIDEO GHÉP PHỤ ĐỀ (HARDSUB)          ")
    print("=" * 60)
    print(f"-> Video nguồn : {video_path}")
    print(f"-> Phụ đề nạp  : {sub_path} ({'Bản ASS có hộp đen & Style' if sub_path.endswith('.ass') else 'Bản SRT'})")
    print(f"-> Xuất ra     : {output_path}")
    print("-" * 60)
    print("-> Đang tiến hành ghép phụ đề vào từng khung hình...")
    print("-> Vui lòng đợi trong giây lát...\n")

    cmd = [
        ffmpeg, "-y",
        "-i", video_path,
        "-vf", f"scale=1920:1080:flags=lanczos,subtitles='{sub_clean_path}'",
        "-c:v", "libx264",
        "-profile:v", "high",
        "-level", "4.2",
        "-preset", "medium",
        "-crf", "15",
        "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        output_path
    ]

    res = subprocess.run(cmd)

    if res.returncode == 0:
        print("\n" + "=" * 60)
        print("🎉 XUẤT VIDEO THÀNH CÔNG 100%!")
        print(f"👉 File thành phẩm của bạn nằm tại: {output_path}")
        print("=" * 60)
    else:
        print(f"\n❌ Có lỗi xảy ra khi xuất video (Mã lỗi {res.returncode})")

if __name__ == "__main__":
    v_arg = sys.argv[1].strip('\"\'') if len(sys.argv) > 1 else None
    s_arg = sys.argv[2].strip('\"\'') if len(sys.argv) > 2 else None
    export_subbed_video(v_arg, s_arg)
