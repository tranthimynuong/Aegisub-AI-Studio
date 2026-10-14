"""
Aegisub AI Studio - Web Studio Server
Author: My Nuong (HCMUTE)
Description: Local web UI for previewing subtitle alignment and video export.
"""

import os
import sys
import glob
import json
import threading
import subprocess
from flask import Flask, request, jsonify, send_file, send_from_directory, Response

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

    # Tự động nạp thư viện DLL NVIDIA (cublas, cudnn)
    possible_sites = [
        os.path.join(sys.prefix, "Lib", "site-packages", "nvidia", "*", "bin"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Python", "*", "Lib", "site-packages", "nvidia", "*", "bin"),
    ]
    for pattern in possible_sites:
        for d in glob.glob(pattern):
            if os.path.isdir(d):
                os.environ["PATH"] = d + ";" + os.environ.get("PATH", "")
                try:
                    os.add_dll_directory(d)
                except Exception:
                    pass

app = Flask(__name__, static_folder='static')

# Trạng thái tiến trình
CURRENT_TASK = {
    "status": "idle",       # idle | processing | error | done
    "progress": 0,          # 0 - 100
    "step": "",             # mô tả bước
    "result_file": None,
    "error_message": None
}

def get_ffmpeg():
    try:
        import static_ffmpeg
        static_ffmpeg.add_paths()
    except Exception:
        pass
    import shutil
    return shutil.which("ffmpeg")

def format_timestamp(seconds: float) -> str:
    millis = int((seconds - int(seconds)) * 1000)
    mins, secs = divmod(int(seconds), 60)
    hours, mins = divmod(mins, 60)
    return f"{hours:02d}:{mins:02d}:{secs:02d},{millis:03d}"

def format_ass_time(seconds: float) -> str:
    centis = int((seconds - int(seconds)) * 100)
    mins, secs = divmod(int(seconds), 60)
    hours, mins = divmod(mins, 60)
    return f"{hours:01d}:{mins:02d}:{secs:02d}.{centis:02d}"

def parse_srt(srt_content: str):
    subs = []
    blocks = srt_content.strip().split("\n\n")
    for block in blocks:
        lines = [line.strip() for line in block.split("\n") if line.strip()]
        if len(lines) >= 3:
            try:
                sub_id = int(lines[0])
                time_line = lines[1]
                parts = time_line.split("-->")
                start_str = parts[0].strip()
                end_str = parts[1].strip()

                def to_sec(t_str):
                    t_str = t_str.replace(",", ".")
                    h, m, s = t_str.split(":")
                    return int(h) * 3600 + int(m) * 60 + float(s)

                start_sec = to_sec(start_str)
                end_sec = to_sec(end_str)
                text = "\n".join(lines[2:])
                subs.append({
                    "id": sub_id,
                    "start": start_sec,
                    "end": end_sec,
                    "start_fmt": start_str,
                    "end_fmt": end_str,
                    "text": text,
                    "original_text": ""
                })
            except Exception:
                continue
    return subs

@app.route("/")
def index():
    return send_from_directory("static", "index.html")

@app.route("/<path:filename>")
def static_files(filename):
    return send_from_directory("static", filename)

@app.route("/api/list_videos")
def list_videos():
    folders = [r"D:\Downloads", os.getcwd()]
    videos = []
    seen = set()
    for f in folders:
        if os.path.exists(f):
            for ext in ("*.mp4", "*.mkv", "*.avi", "*.mov"):
                for p in glob.glob(os.path.join(f, ext)):
                    if not p.endswith("_Subbed.mp4") and p not in seen:
                        seen.add(p)
                        videos.append({
                            "path": p,
                            "filename": os.path.basename(p),
                            "size_mb": round(os.path.getsize(p) / (1024 * 1024), 1)
                        })
    return jsonify(videos)

@app.route("/api/video")
def get_video():
    path = request.args.get("path")
    if not path or not os.path.exists(path):
        return "Video not found", 404
    return send_file(path, conditional=True)

@app.route("/api/load_subs")
def load_subs():
    video_path = request.args.get("video_path")
    if not video_path:
        return jsonify({"error": "Missing video_path"}), 400

    base, _ = os.path.splitext(video_path)
    base_clean = base.replace("_blurred", "").replace("- blurred", "").strip()

    candidates = [
        f"{base}_vi.srt",
        f"{base}.srt",
        f"{base}_vi.ass",
        f"{base}.ass",
        f"{base_clean}_vi.srt",
        f"{base_clean}.srt",
        f"{base_clean}_vi.ass",
        f"{base_clean}.ass"
    ]
    found_sub = None
    for c in candidates:
        if os.path.exists(c):
            found_sub = c
            break

    if not found_sub:
        return jsonify({"subs": [], "found": False})

    with open(found_sub, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()

    subs = parse_srt(content)
    return jsonify({"subs": subs, "found": True, "file_path": found_sub})

@app.route("/api/save_subs", methods=["POST"])
def save_subs():
    data = request.json or {}
    video_path = data.get("video_path")
    subs = data.get("subs", [])
    font_name = data.get("font_name", "Arial")
    font_size = data.get("font_size", 48)
    margin_v = data.get("margin_v", 55)
    primary_color = data.get("primary_color", "&H00FFFFFF")  # ASS BGR
    outline_color = data.get("outline_color", "&H00000000")
    outline_width = data.get("outline_width", 3.0)

    if not video_path:
        return jsonify({"error": "Missing video_path"}), 400

    base, _ = os.path.splitext(video_path)
    srt_path = f"{base}_vi.srt"
    ass_path = f"{base}_vi.ass"

    # Lưu SRT
    with open(srt_path, "w", encoding="utf-8") as f:
        for s in subs:
            f.write(f"{s['id']}\n")
            f.write(f"{format_timestamp(s['start'])} --> {format_timestamp(s['end'])}\n")
            f.write(f"{s['text'].strip()}\n\n")

    # Lưu ASS với đầy đủ Style và Margin
    ass_header = f"""[Script Info]
Title: Video Subber Studio
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: None
PlayResX: 1280
PlayResY: 720

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_name},{font_size},{primary_color},&H000000FF,{outline_color},&H00000000,-1,0,0,0,100,100,0,0,1,{outline_width},1.5,2,10,10,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ass_lines = []
    for s in subs:
        st = format_ass_time(s['start'])
        et = format_ass_time(s['end'])
        txt = s['text'].replace("\n", "\\N")
        ass_lines.append(f"Dialogue: 0,{st},{et},Default,,0,0,0,,{txt}")

    with open(ass_path, "w", encoding="utf-8") as f:
        f.write(ass_header + "\n".join(ass_lines) + "\n")

    return jsonify({"success": True, "srt_path": srt_path, "ass_path": ass_path})

@app.route("/api/export", methods=["POST"])
def export_video():
    global CURRENT_TASK
    if CURRENT_TASK["status"] == "processing":
        return jsonify({"error": "Một tác vụ khác đang được xử lý"}), 400

    data = request.json or {}
    video_path = data.get("video_path")
    blur_logo = data.get("blur_logo", True)
    blur_x = data.get("blur_x", 15)
    blur_y = data.get("blur_y", 15)
    blur_w = data.get("blur_w", 245)
    blur_h = data.get("blur_h", 70)

    if not video_path or not os.path.exists(video_path):
        return jsonify({"error": "Video không tồn tại"}), 400

    base, ext = os.path.splitext(video_path)
    ass_path = f"{base}_vi.ass"
    srt_path = f"{base}_vi.srt"
    sub_file = ass_path if os.path.exists(ass_path) else srt_path

    if not os.path.exists(sub_file):
        return jsonify({"error": "Chưa có file phụ đề. Vui lòng bấm lưu trước."}), 400

    output_path = f"{base}_Subbed{ext}"
    ffmpeg = get_ffmpeg()

    def run_export():
        global CURRENT_TASK
        CURRENT_TASK["status"] = "processing"
        CURRENT_TASK["progress"] = 20
        CURRENT_TASK["step"] = "Đang tổng hợp video với phụ đề & bộ lọc..."

        sub_clean = os.path.abspath(sub_file).replace("\\", "/").replace(":", "\\:")
        
        filter_complex = []
        if blur_logo:
            filter_complex.append(f"crop={blur_w}:{blur_h}:{blur_x}:{blur_y},boxblur=12:5[b_left];[0:v][b_left]overlay={blur_x}:{blur_y}[v_blurred]")
            filter_complex.append(f"[v_blurred]subtitles='{sub_clean}'")
        else:
            filter_complex.append(f"subtitles='{sub_clean}'")

        vf_str = ";".join(filter_complex)

        cmd = [
            ffmpeg, "-y",
            "-i", video_path,
            "-filter_complex" if blur_logo else "-vf", vf_str,
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "18",
            "-c:a", "copy",
            output_path
        ]

        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if res.returncode == 0:
                CURRENT_TASK["status"] = "done"
                CURRENT_TASK["progress"] = 100
                CURRENT_TASK["step"] = "Xuất video thành công rực rỡ!"
                CURRENT_TASK["result_file"] = output_path
            else:
                CURRENT_TASK["status"] = "error"
                CURRENT_TASK["error_message"] = f"Lỗi ffmpeg (Mã {res.returncode})"
        except Exception as e:
            CURRENT_TASK["status"] = "error"
            CURRENT_TASK["error_message"] = str(e)

    threading.Thread(target=run_export, daemon=True).start()
    return jsonify({"success": True})

@app.route("/api/status")
def get_status():
    return jsonify(CURRENT_TASK)

@app.route("/api/open_folder", methods=["POST"])
def open_folder():
    path = request.json.get("path")
    if path and os.path.exists(path):
        subprocess.run(["explorer.exe", "/select,", os.path.abspath(path)])
        return jsonify({"success": True})
    return jsonify({"error": "Path not found"}), 404

if __name__ == "__main__":
    print("=" * 60)
    print("  🚀 VIDEO SUBBER STUDIO ĐANG KHỞI CHẠY...")
    print("  👉 Mở trình duyệt tại: http://localhost:5000")
    print("=" * 60)
    app.run(host="127.0.0.1", port=5000, debug=False)
