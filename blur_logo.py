import os
import sys
import subprocess

def get_ffmpeg():
    try:
        import static_ffmpeg
        static_ffmpeg.add_paths()
    except Exception:
        pass
    import shutil
    return shutil.which("ffmpeg")

def blur_video(input_path, output_path=None, blur_left=True, blur_right=False):
    if not os.path.exists(input_path):
        print(f"Lỗi: Không tìm thấy file '{input_path}'")
        return

    if not output_path:
        base, ext = os.path.splitext(input_path)
        output_path = f"{base}_blurred{ext}"

    ffmpeg = get_ffmpeg()
    if not ffmpeg:
        print("Lỗi: Không tìm thấy ffmpeg trên hệ thống.")
        return

    # Filter xóa mờ tự nhiên (Frosted glass blur)
    # Góc trái (bilibili): x=15, y=15, w=245, h=70
    # Góc phải (Moon Fox): x=1050, y=15, w=215, h=70
    filters = []
    if blur_left and blur_right:
        fc = (
            "[0:v]crop=245:70:15:15,boxblur=12:5[b_left];"
            "[0:v]crop=215:70:1050:15,boxblur=12:5[b_right];"
            "[0:v][b_left]overlay=15:15[tmp];"
            "[tmp][b_right]overlay=1050:15"
        )
    elif blur_right:
        fc = "[0:v]crop=215:70:1050:15,boxblur=12:5[b_right];[0:v][b_right]overlay=1050:15"
    else:
        fc = "[0:v]crop=245:70:15:15,boxblur=12:5[b_left];[0:v][b_left]overlay=15:15"

    cmd = [
        ffmpeg, "-y",
        "-i", input_path,
        "-filter_complex", fc,
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "18",
        "-c:a", "copy",
        output_path
    ]

    print(f"\n-> Đang làm mờ logo tự nhiên bằng FFmpeg...")
    print(f"-> File gốc: {input_path}")
    print(f"-> Xuất ra: {output_path}")

    res = subprocess.run(cmd)
    if res.returncode == 0:
        print(f"\n🎉 HOÀN TẤT! Video đã làm mờ logo được lưu tại: {output_path}")
    else:
        print(f"\nLỗi khi xuất video (Mã lỗi {res.returncode})")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        video_file = sys.argv[1].strip('\"\'')
    else:
        video_file = r"D:\Downloads\【自制动画】聊斋系列之《商三官》 - Original.mp4"
    blur_video(video_file)
