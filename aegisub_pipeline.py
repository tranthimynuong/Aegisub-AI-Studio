"""
Aegisub AI Studio - Core Automation Pipeline
Author: My Nuong (HCMUTE)
Description: End-to-end multi-modal pipeline for speech transcription, video OCR,
             AI-powered contextual translation (Gemini / DeepSeek), and TTS voiceover.
"""

import os
import sys
import gc
import json
import glob
import math
import re
import shutil
import argparse
import subprocess

# 1. Đảm bảo hỗ trợ UTF-8 trên Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

    # Nạp các thư viện NVIDIA CUDA (cuBLAS, cuDNN) cho ctranslate2 / faster-whisper
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

def get_ffmpeg():
    try:
        import static_ffmpeg
        static_ffmpeg.add_paths()
    except Exception:
        pass
    ff = shutil.which("ffmpeg")
    return ff

def format_timestamp_ass(seconds: float) -> str:
    # ASS format: H:MM:SS.cs (centiseconds)
    centis = int(round((seconds - int(seconds)) * 100))
    if centis >= 100:
        centis = 99
    mins, secs = divmod(int(seconds), 60)
    hours, mins = divmod(mins, 60)
    return f"{hours}:{mins:02d}:{secs:02d}.{centis:02d}"

def format_timestamp_srt(seconds: float) -> str:
    millis = int((seconds - int(seconds)) * 1000)
    mins, secs = divmod(int(seconds), 60)
    hours, mins = divmod(mins, 60)
    return f"{hours:02d}:{mins:02d}:{secs:02d},{millis:03d}"

def run_transcribe(video_path: str, model_size="small", source_lang=None):
    import torch
    import ctranslate2
    from faster_whisper import WhisperModel

    print("=" * 60)
    print("      BƯỚC 1/2: BÓC TÁCH THOẠI BẰNG WHISPER (GPU ACCELERATED)")
    print("=" * 60)
    print(f"-> Video: {video_path}")

    has_cuda = ctranslate2.get_cuda_device_count() > 0 or torch.cuda.is_available()
    device = "cuda" if has_cuda else "cpu"
    compute_type = "float16" if device == "cuda" else "int8"
    print(f"-> Thiết bị xử lý: {device.upper()} (Compute: {compute_type})")

    try:
        model = WhisperModel(model_size, device=device, compute_type=compute_type)
        segments, info = model.transcribe(
            video_path,
            language=source_lang if source_lang and source_lang != "auto" else None,
            beam_size=5
        )
    except Exception as e:
        if device == "cuda":
            print(f"-> CUDA gặp vấn đề ({e}), chuyển về chế độ CPU...")
            device = "cpu"
            compute_type = "int8"
            model = WhisperModel(model_size, device=device, compute_type=compute_type)
            segments, info = model.transcribe(video_path, beam_size=5)
        else:
            raise e

    print(f"-> Ngôn ngữ phát hiện: {info.language} (Độ tin cậy: {info.language_probability:.2f})")
    
    subs = []
    for i, seg in enumerate(segments, 1):
        subs.append({
            "id": i,
            "start": round(seg.start, 3),
            "end": round(seg.end, 3),
            "text": seg.text.strip()
        })

    del model
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    print(f"-> Đã bóc tách thành công {len(subs)} câu thoại.")
    return subs, info.language

def run_video_ocr(video_path: str, sample_fps: float = 1.8, crop_y_start: float = None, crop_y_end: float = None):
    import cv2
    from difflib import SequenceMatcher
    from rapidocr_onnxruntime import RapidOCR
    from tqdm import tqdm

    print("\n" + "=" * 60)
    print("      🔍 BƯỚC 1/2: QUÉT CHỮ HARDSUB TRÊN VIDEO (VIDEO OCR CHUẨN KỊCH BẢN)")
    print("=" * 60)
    print(f"-> Video: {video_path}")
    print("-> Đang khởi tạo mô hình RapidOCR (ONNX Cực Nhanh)...")

    ocr = RapidOCR()
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"Lỗi: Không thể mở video tại '{video_path}'")
        return []

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    duration = total_frames / fps

    print(f"-> Độ phân giải : {w}x{h} ({'Khung dọc 9:16' if h > w else 'Khung ngang 16:9'})")
    print(f"-> Thời lượng   : {int(duration // 60)} phút {int(duration % 60)} giây ({total_frames} frames)")

    # Tự động định vị vùng chứa phụ đề đáy màn hình
    if crop_y_start is None:
        crop_y_start = 0.70 if h > w else 0.78
    if crop_y_end is None:
        crop_y_end = 0.93 if h > w else 0.95

    crop_top = int(h * crop_y_start)
    crop_bottom = int(h * crop_y_end)

    step = max(1, int(round(fps / sample_fps)))
    sample_interval = step / fps

    raw_timeline = []
    frame_count = 0
    prev_crop_gray = None
    last_text = ""

    pbar = tqdm(total=total_frames, desc="Tiến độ quét OCR video")

    while True:
        ret = cap.grab()
        if not ret:
            break

        if frame_count % step == 0:
            ret, frame = cap.retrieve()
            if not ret:
                break
            cur_sec = frame_count / fps
            crop = frame[crop_top:crop_bottom, :]
            gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)

            # Khử trùng lặp: nếu vùng chữ không thay đổi, dùng lại kết quả OCR trước
            if prev_crop_gray is not None:
                diff = cv2.absdiff(gray, prev_crop_gray)
                if cv2.mean(diff)[0] < 3.0:
                    raw_timeline.append((cur_sec, last_text))
                    frame_count += 1
                    pbar.update(1)
                    continue

            prev_crop_gray = gray
            res, _ = ocr(crop)
            text = ""
            if res:
                valid_texts = [
                    r[1].strip() for r in res 
                    if (len(r[1].strip()) >= 2 or any('\u4e00' <= char <= '\u9fff' for char in r[1]))
                    and r[1].strip() not in ["...", "---", "___", "."]
                ]
                if valid_texts:
                    text = " ".join(valid_texts)
            last_text = text
            raw_timeline.append((cur_sec, text))

        frame_count += 1
        pbar.update(1)

    pbar.close()
    cap.release()

    # Hợp nhất các khung hình có chữ giống nhau
    merged = []
    current_sub = None

    for sec, text in raw_timeline:
        if text:
            if current_sub is None:
                current_sub = {'start': sec, 'end': sec + sample_interval, 'text': text}
            else:
                sim = SequenceMatcher(None, current_sub['text'], text).ratio()
                if sim > 0.60:
                    current_sub['end'] = sec + sample_interval
                    if len(text) > len(current_sub['text']):
                        current_sub['text'] = text
                else:
                    if current_sub['end'] - current_sub['start'] >= 0.4:
                        merged.append(current_sub)
                    current_sub = {'start': sec, 'end': sec + sample_interval, 'text': text}
        else:
            if current_sub is not None:
                if current_sub['end'] - current_sub['start'] >= 0.4:
                    merged.append(current_sub)
                current_sub = None

    if current_sub is not None and (current_sub['end'] - current_sub['start'] >= 0.4):
        merged.append(current_sub)

    subs = []
    for idx, s in enumerate(merged, 1):
        subs.append({
            "id": idx,
            "start": round(s["start"], 3),
            "end": round(s["end"], 3),
            "text": s["text"]
        })

    print(f"-> Đã bóc tách thành công {len(subs)} câu thoại chuẩn xác 100% từ hình ảnh video.")
    return subs

def fuse_audio_and_ocr(ocr_subs, audio_subs):
    """
    Hợp nhất Đa phương thức (Multimodal Fusion - Âm thanh Whisper + Quét hình ảnh RapidOCR):
    - ocr_subs: danh sách câu quét từ video [{'start', 'end', 'text'}]
    - audio_subs: danh sách câu nghe từ âm thanh [{'start', 'end', 'text'}]
    
    Thuật toán:
    1. Chuẩn hóa chữ: Chữ Hán từ OCR là kịch bản chuẩn 100% (tránh hoàn toàn từ đồng âm, ảo giác của Whisper).
    2. Khớp nhịp nói: Lấy nhịp ngắt/mở miệng thực tế của diễn viên từ Whisper audio.
    3. Cứu thoại BGM: Những câu thoại OCR phát hiện nhưng Whisper bị nuốt tiếng (nhạc nền to) sẽ được tự động bù vào.
    4. Cứu thoại ngoài khung hình: Những câu thoại có tiếng nói nhưng không có chữ hiển thị trên màn hình sẽ được giữ lại từ Whisper.
    """
    used_ocr_indices = set()
    fused_subs = []

    for a in audio_subs:
        a_start = a["start"]
        a_end = a["end"]
        a_text = a["text"].strip()
        if not a_text:
            continue

        # Tìm các đoạn OCR giao thoa thời gian với đoạn âm thanh
        matched_ocr = []
        for idx, o in enumerate(ocr_subs):
            o_start = o["start"]
            o_end = o["end"]
            overlap = min(a_end, o_end) - max(a_start, o_start)
            if overlap > 0.1 or (abs(a_start - o_start) <= 0.6 and abs(a_end - o_end) <= 0.8):
                matched_ocr.append((idx, o))

        if matched_ocr:
            for idx, _ in matched_ocr:
                used_ocr_indices.add(idx)

            matched_ocr.sort(key=lambda x: x[1]["start"])
            ocr_text = " ".join([item[1]["text"] for item in matched_ocr]).strip()

            # Lấy ranh giới thời gian chuẩn nhất (kết hợp nhịp âm thanh và thời gian chữ hiện)
            f_start = min(a_start, matched_ocr[0][1]["start"])
            f_end = max(a_end, matched_ocr[-1][1]["end"])

            fused_subs.append({
                "start": round(f_start, 3),
                "end": round(f_end, 3),
                "text": ocr_text,
                "note": "hybrid"
            })
        else:
            # Không có chữ OCR tương ứng (lời thoại ngoài khung hình / thuyết minh ngầm)
            fused_subs.append({
                "start": round(a_start, 3),
                "end": round(a_end, 3),
                "text": a_text,
                "note": "audio_only"
            })

    # Bổ sung các câu OCR mà Whisper bị nuốt mất do nhạc nền (BGM) quá to
    recovered_count = 0
    for idx, o in enumerate(ocr_subs):
        if idx not in used_ocr_indices:
            fused_subs.append({
                "start": round(o["start"], 3),
                "end": round(o["end"], 3),
                "text": o["text"].strip(),
                "note": "ocr_recovered"
            })
            recovered_count += 1

    # Sắp xếp theo mốc thời gian bắt đầu
    fused_subs.sort(key=lambda x: x["start"])

    # Gán ID tuần tự
    final_subs = []
    for i, s in enumerate(fused_subs, 1):
        s["id"] = i
        final_subs.append(s)

    print(f"\n-> 🔗 Kết quả Hợp Nhất Đa Phương Thức (Multimodal Fusion):")
    print(f"   - Tổng số câu thoại           : {len(final_subs)}")
    print(f"   - Số câu ghép chuẩn (Audio+OCR): {len(final_subs) - recovered_count}")
    print(f"   - Số câu cứu thêm từ OCR      : {recovered_count} (khắc phục hoàn toàn BGM lấn át)")

    return final_subs

API_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ai_api_config.json")

def load_api_config():
    if os.path.exists(API_CONFIG_PATH):
        try:
            with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "translation_engine": "gemini",
        "gemini_api_key": "",
        "deepseek_api_key": ""
    }

def save_api_config(cfg: dict):
    try:
        with open(API_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def extract_json_from_llm(raw_text: str):
    import re
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        data = json.loads(cleaned)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for v in data.values():
                if isinstance(v, list):
                    return v
    except Exception:
        m = re.search(r"\[\s*\{.*\}\s*\]", cleaned, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                pass
    return None

def run_translate_gemini(subs, api_key: str, target_lang="Vietnamese"):
    import requests
    import time
    print("\n" + "=" * 60)
    print("      🌟 DỊCH NGỮ CẢNH TOÀN VIDEO BẰNG GOOGLE GEMINI AI")
    print("=" * 60)
    print(f"-> Tổng số câu thoại : {len(subs)}")
    print("-> Đang phân tích bối cảnh, thể loại và chuẩn hóa xưng hô...")

    chunk_size = 75  # 75 câu/đoạn: Tối ưu cho ngữ cảnh và không vượt trần token
    translated_map = {}
    # Ưu tiên các model Flash-Lite có hạn mức Free cực cao (1.500 lượt/ngày) và tốc độ siêu nhanh
    active_models = [
        "gemini-flash-lite-latest",
        "gemini-3.5-flash-lite",
        "gemini-3.1-flash-lite",
        "gemini-3.5-flash",
        "gemini-3.8-flash"
    ]

    chunks = []
    for i in range(0, len(subs), chunk_size):
        chunk = subs[i:i + chunk_size]
        chunks.append((i, chunk))

    def translate_chunk(chunk_info):
        start_idx, chunk = chunk_info
        items_to_send = [{"id": s["id"], "text": s["text"]} for s in chunk]

        prompt = (
            f"Bạn là một biên dịch viên phụ đề phim chuyên nghiệp xuất sắc (từ tiếng Trung/Anh sang tiếng {target_lang}).\n"
            "Dưới đây là một phần lời thoại trong video theo trình tự thời gian:\n\n"
            f"{json.dumps(items_to_send, ensure_ascii=False, indent=2)}\n\n"
            "HÃY THỰC HIỆN CÁC YÊU CẦU SAU:\n"
            "1. PHÂN TÍCH NGỮ CẢNH: Nắm bắt thể loại phim (cổ trang, đô thị tổng tài, học đường, gia đình, hài hước...), vai vế và mối quan hệ giữa các nhân vật.\n"
            "2. XƯNG HÔ CHUẨN VĂN HÓA VIỆT: Tự động phân vai xưng hô (Anh - Em, Tôi - Cô, Cậu - Tớ, Huynh - Muội, Chàng - Thiếp, Mày - Tao...) tự nhiên, mượt mà và NHẤT QUÁN xuyên suốt. Tuyệt đối không dịch máy móc kiểu 'Tôi - Bạn'.\n"
            "3. ĐẦY ĐỦ Ý NGHĨA 100%: Dịch sát nghĩa, đầy đủ câu từ, giữ trọn vẹn mọi tình tiết và sắc thái của kịch bản gốc. Tuyệt đối KHÔNG tự ý tóm tắt, cắt bớt hay lược bỏ bất kỳ câu chữ nào.\n"
            "4. ĐỊNH DẠNG ĐẦU RA: Bắt buộc trả về đúng cấu trúc JSON array dạng:\n"
            "[\n"
            '  {"id": 1, "translated_text": "..."},\n'
            '  {"id": 2, "translated_text": "..."}\n'
            "]\n"
            "Chỉ trả về JSON thuần túy, không có giải thích hay lời mở đầu/kết thúc."
        )

        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.3,
                "responseMimeType": "application/json"
            }
        }

        max_retries = 3
        for attempt in range(max_retries):
            for model_name in active_models:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
                try:
                    resp = requests.post(url, json=payload, timeout=35)
                    if resp.status_code == 200:
                        res_json = resp.json()
                        raw_content = res_json["candidates"][0]["content"]["parts"][0]["text"]
                        parsed = extract_json_from_llm(raw_content)
                        if parsed and isinstance(parsed, list):
                            chunk_res = {}
                            for item in parsed:
                                if "id" in item and "translated_text" in item:
                                    chunk_res[item["id"]] = item["translated_text"]
                            print(f"-> Đã dịch xong đoạn {start_idx+1} đến {min(start_idx+len(chunk), len(subs))} câu thoại ({model_name})...")
                            return chunk_res
                    elif resp.status_code == 429:
                        # Model chạm giới hạn (hoặc hạn mức ngày), lập tức chuyển sang model khác trong danh sách
                        continue
                    elif resp.status_code in [404, 503]:
                        # Model không hỗ trợ hoặc tạm quá tải, chuyển model tiếp theo
                        continue
                    else:
                        continue
                except Exception:
                    continue

            # Nếu cả danh sách model đều bận tạm thời, chờ 5s rồi thử lại vòng lặp
            time.sleep(5)

        print(f"   ⚠️ Không thể dịch đoạn từ câu {start_idx+1} qua Gemini AI.")
        return {}

    for c in chunks:
        chunk_map = translate_chunk(c)
        translated_map.update(chunk_map)
        time.sleep(1.0)

    res_subs = []
    missing_count = 0
    for s in subs:
        t_text = translated_map.get(s["id"])
        if t_text is not None and t_text.strip() != "":
            res_subs.append({**s, "translated_text": t_text.strip()})
        else:
            missing_count += 1
            res_subs.append({**s, "translated_text": s["text"]})

    if missing_count > len(subs) * 0.5:
        return None

    print("🎉 Dịch ngữ cảnh toàn video với Google Gemini AI thành công 100%!")
    return res_subs

def run_translate_deepseek(subs, api_key: str, target_lang="Vietnamese"):
    import requests
    from concurrent.futures import ThreadPoolExecutor, as_completed
    print("\n" + "=" * 60)
    print("      🌟 DỊCH NGỮ CẢNH TOÀN VIDEO BẰNG DEEPSEEK V3 AI")
    print("=" * 60)
    print(f"-> Tổng số câu thoại : {len(subs)}")
    print("-> Đang phân tích bối cảnh, thể loại và chuẩn hóa xưng hô...")

    chunk_size = 90
    translated_map = {}
    url = "https://api.deepseek.com/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    chunks = []
    for i in range(0, len(subs), chunk_size):
        chunk = subs[i:i + chunk_size]
        chunks.append((i, chunk))

    def translate_chunk_ds(chunk_info):
        start_idx, chunk = chunk_info
        items_to_send = [{"id": s["id"], "text": s["text"]} for s in chunk]

        prompt = (
            f"Bạn là một biên dịch viên phụ đề phim chuyên nghiệp (từ tiếng Trung/Anh sang tiếng {target_lang}).\n"
            "Dưới đây là một phần lời thoại trong video theo trình tự thời gian:\n\n"
            f"{json.dumps(items_to_send, ensure_ascii=False, indent=2)}\n\n"
            "HÃY THỰC HIỆN CÁC YÊU CẦU SAU:\n"
            "1. Nắm bắt thể loại phim và mối quan hệ giữa các nhân vật.\n"
            "2. Tự động đồng bộ đại từ xưng hô phù hợp (Anh - Em, Tôi - Cô, Huynh - Muội, Cậu - Tớ, Mày - Tao...) nhất quán xuyên suốt.\n"
            "3. Trả về đúng JSON array dạng:\n"
            "[\n"
            '  {"id": 1, "translated_text": "..."},\n'
            '  {"id": 2, "translated_text": "..."}\n'
            "]\n"
            "Chỉ trả về JSON thuần túy."
        )

        payload = {
            "model": "deepseek-chat",
            "messages": [
                {"role": "system", "content": "You are a professional subtitle translator. Always output valid JSON array."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.3
        }

        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=40)
            if resp.status_code == 200:
                raw_content = resp.json()["choices"][0]["message"]["content"]
                parsed = extract_json_from_llm(raw_content)
                if parsed and isinstance(parsed, list):
                    chunk_res = {}
                    for item in parsed:
                        if "id" in item and "translated_text" in item:
                            chunk_res[item["id"]] = item["translated_text"]
                    print(f"-> Đã dịch xong đoạn {start_idx+1} đến {min(start_idx+chunk_size, len(subs))} câu thoại...")
                    return chunk_res
            else:
                print(f"   ⚠️ DeepSeek trả về mã {resp.status_code}: {resp.text[:200]}")
        except Exception as e:
            print(f"   ⚠️ Lỗi kết nối DeepSeek: {e}")
        return {}

    workers = min(3, len(chunks))
    if workers > 1:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(translate_chunk_ds, c) for c in chunks]
            for f in as_completed(futures):
                translated_map.update(f.result())
    else:
        for c in chunks:
            translated_map.update(translate_chunk_ds(c))

    res_subs = []
    missing_count = 0
    for s in subs:
        t_text = translated_map.get(s["id"])
        if t_text is not None and t_text.strip() != "":
            res_subs.append({**s, "translated_text": t_text.strip()})
        else:
            missing_count += 1
            res_subs.append({**s, "translated_text": s["text"]})

    if missing_count > len(subs) * 0.5:
        return None

    print("🎉 Dịch ngữ cảnh toàn video với DeepSeek AI thành công 100%!")
    return res_subs

def run_translate_hy_mt2(subs, target_lang="Vietnamese"):
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from tqdm import tqdm

    print("\n" + "=" * 60)
    print("      BƯỚC 2/2: DỊCH PHỤ ĐỀ BẰNG TENCENT HY-MT2-1.8B (OFFLINE)")
    print("=" * 60)
    print("-> Đang nạp mô hình dịch vào GPU...")

    model_id = "tencent/Hy-MT2-1.8B"
    device = "cuda" if torch.cuda.is_available() else "cpu"

    tokenizer = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(
        model_id,
        dtype=torch.float16 if device == "cuda" else torch.float32,
        device_map="auto",
        trust_remote_code=True
    )
    model.eval()

    print(f"-> Đang tiến hành dịch {len(subs)} câu sang tiếng Việt...")
    translated_subs = []

    for sub in tqdm(subs, desc="Tiến độ dịch"):
        raw_text = sub["text"]
        if not raw_text:
            translated_subs.append({**sub, "translated_text": ""})
            continue

        prompt = (
            f"Translate the following spoken subtitle into natural {target_lang}. "
            "Note that you should only output the translated result without any additional explanation:\n\n"
            f"{raw_text}"
        )

        messages = [{"role": "user", "content": prompt}]
        inputs = tokenizer.apply_chat_template(
            messages,
            add_generation_prompt=True,
            return_tensors="pt"
        ).to(model.device)

        with torch.no_grad():
            outputs = model.generate(
                **inputs,
                max_new_tokens=256,
                temperature=0.7,
                top_p=0.6,
                top_k=20,
                repetition_penalty=1.05
            )

        translated = tokenizer.decode(outputs[0][inputs["input_ids"].shape[-1]:], skip_special_tokens=True).strip()
        translated_subs.append({**sub, "translated_text": translated})

    del model
    del tokenizer
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    return translated_subs

def run_translate(subs, target_lang="Vietnamese", engine="gemini", api_key=None):
    cfg = load_api_config()

    if engine in ["gemini", "deepseek", "hy_mt2"]:
        cfg["translation_engine"] = engine
    if api_key and api_key.strip():
        if engine == "deepseek":
            cfg["deepseek_api_key"] = api_key.strip()
        else:
            cfg["gemini_api_key"] = api_key.strip()
        save_api_config(cfg)

    g_key = api_key if (engine == "gemini" and api_key) else (cfg.get("gemini_api_key") or os.environ.get("GEMINI_API_KEY"))
    d_key = api_key if (engine == "deepseek" and api_key) else (cfg.get("deepseek_api_key") or os.environ.get("DEEPSEEK_API_KEY"))

    if engine == "gemini":
        if g_key and g_key.strip():
            result = run_translate_gemini(subs, g_key.strip(), target_lang)
            if result:
                return result
            print("\n⚠️ Chuyển sang phương án dự phòng (Fallback sang Tencent Hy-MT2)...")
        else:
            print("\n⚠️ Chưa có Gemini API Key. Đang tự động chuyển sang mô hình Offline Hy-MT2...")
            return run_translate_hy_mt2(subs, target_lang)

    elif engine == "deepseek":
        if d_key and d_key.strip():
            result = run_translate_deepseek(subs, d_key.strip(), target_lang)
            if result:
                return result
            print("\n⚠️ Chuyển sang phương án dự phòng (Fallback sang Tencent Hy-MT2)...")
        else:
            print("\n⚠️ Chưa có DeepSeek API Key. Đang tự động chuyển sang mô hình Offline Hy-MT2...")
            return run_translate_hy_mt2(subs, target_lang)

    return run_translate_hy_mt2(subs, target_lang)

def write_ass_file(subs, output_path: str):
    header = """[Script Info]
; Script generated by Aegisub AI Studio
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709
PlayResX: 1920
PlayResY: 1080

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Segoe UI,24,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,3,2,0,2,20,20,55,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(header)
        for sub in subs:
            start_str = format_timestamp_ass(sub["start"])
            end_str = format_timestamp_ass(sub["end"])
            text = sub.get("translated_text", sub.get("text", "")).replace("\n", "\\N")
            f.write(f"Dialogue: 0,{start_str},{end_str},Default,,0,0,0,,{text}\n")

def write_json_file(subs, output_path: str):
    data = []
    for sub in subs:
        data.append({
            "id": sub["id"],
            "start": sub["start"],
            "end": sub["end"],
            "start_ms": int(sub["start"] * 1000),
            "end_ms": int(sub["end"] * 1000),
            "text": sub.get("translated_text", sub.get("text", "")),
            "raw_text": sub.get("text", "")
        })
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def set_console_title(title: str):
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.kernel32.SetConsoleTitleW(title)
        except Exception:
            pass

def format_sec(sec: float) -> str:
    m, s = divmod(int(sec), 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"

def get_video_duration(video_path):
    ff = get_ffmpeg()
    cmd = [ff, "-i", video_path]
    res = subprocess.run(cmd, stderr=subprocess.PIPE, stdout=subprocess.DEVNULL, text=True, errors='replace')
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", res.stderr or "")
    if m:
        h, mins, s = m.groups()
        return int(h) * 3600 + int(mins) * 60 + float(s)
    return None

def check_video_has_audio(video_path: str) -> bool:
    try:
        import av
        with av.open(video_path) as container:
            return len(container.streams.audio) > 0
    except Exception:
        return True

def run_ffmpeg_with_progress(cmd, video_path):
    total_sec = get_video_duration(video_path)
    full_cmd = list(cmd)
    full_cmd.extend(["-progress", "pipe:1", "-nostats"])

    proc = subprocess.Popen(
        full_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        errors='replace',
        bufsize=1
    )

    cur_sec = 0.0
    speed_str = "1.0x"

    print("-> Đang tiến hành xuất video...")
    for line in proc.stdout:
        line = line.strip()
        if not line:
            continue
        if line.startswith("out_time_us="):
            try:
                us = int(line.split("=")[1])
                cur_sec = us / 1_000_000.0
            except Exception:
                pass
        elif line.startswith("speed="):
            speed_str = line.split("=")[1].strip()
        elif line == "progress=continue" or line == "progress=end":
            if total_sec and total_sec > 0:
                pct = min(100.0, (cur_sec / total_sec) * 100.0)
                try:
                    speed_val = float(speed_str.rstrip("x"))
                    eta_sec = (total_sec - cur_sec) / speed_val if speed_val > 0 else 0
                except Exception:
                    eta_sec = 0

                bar_len = 25
                filled = int(bar_len * pct / 100.0)
                bar = "█" * filled + "░" * (bar_len - filled)
                eta_text = f"Còn lại: {format_sec(eta_sec)}" if eta_sec > 0 else "Sắp xong"

                status_str = f"\r🚀 Tiến độ: [{bar}] {pct:5.1f}% | {format_sec(cur_sec)}/{format_sec(total_sec)} | Tốc độ: {speed_str} | {eta_text}"
                print(status_str, end="", flush=True)
                set_console_title(f"[{int(pct)}%] Đang xuất video - {format_sec(cur_sec)}/{format_sec(total_sec)} ({speed_str})")

    proc.stdout.close()
    returncode = proc.wait()
    return returncode, ""

def write_lines_file(subs, output_path: str):
    with open(output_path, "w", encoding="utf-8") as f:
        for sub in subs:
            start_ms = int(round(sub["start"] * 1000))
            end_ms = int(round(sub["end"] * 1000))
            raw_text = (sub.get("text") or "").replace("\n", "\\N").replace("|", " ")
            text = (sub.get("translated_text") or sub.get("text") or "").replace("\n", "\\N").replace("|", " ")
            f.write(f"{start_ms}|{end_ms}|{raw_text}|{text}\n")

def handle_transcribe(args):
    video = os.path.abspath(args.video)
    if not os.path.exists(video):
        print(f"Lỗi: Không tìm thấy video tại '{video}'")
        sys.exit(1)

    base, _ = os.path.splitext(video)
    output_ass = args.output_ass or f"{base}_vi.ass"
    output_json = args.output_json or f"{base}_ai_sub.json"
    output_lines = args.output_lines or f"{base}_ai_lines.txt"

    raw_subs, lang = run_transcribe(video, model_size=args.model_size, source_lang=args.source_lang)
    if not raw_subs:
        print("Không tìm thấy câu thoại nào.")
        sys.exit(1)

    engine = getattr(args, "engine", "gemini") or "gemini"
    api_key = getattr(args, "api_key", None)
    translated_subs = run_translate(raw_subs, target_lang="Vietnamese", engine=engine, api_key=api_key)

    write_ass_file(translated_subs, output_ass)
    write_json_file(translated_subs, output_json)
    write_lines_file(translated_subs, output_lines)

    print("\n" + "=" * 60)
    print("🎉 HOÀN THÀNH TÁCH THOẠI & DỊCH THUẬT!")
    print(f"👉 File ASS   : {output_ass}")
    print(f"👉 File JSON  : {output_json}")
    print(f"👉 File Lines : {output_lines}")
    print("=" * 60)

def handle_video_ocr(args):
    video = os.path.abspath(args.video)
    if not os.path.exists(video):
        print(f"Lỗi: Không tìm thấy video tại '{video}'")
        sys.exit(1)

    base, _ = os.path.splitext(video)
    output_ass = args.output_ass or f"{base}_ocr_vi.ass"
    output_json = args.output_json or f"{base}_ocr_sub.json"
    output_lines = args.output_lines or f"{base}_ocr_lines.txt"

    sample_fps = getattr(args, "sample_fps", 1.8) or 1.8
    raw_subs = run_video_ocr(video, sample_fps=sample_fps)
    if not raw_subs:
        print("Không tìm thấy câu phụ đề chữ Hán nào trên màn hình video.")
        sys.exit(1)

    engine = getattr(args, "engine", "gemini") or "gemini"
    api_key = getattr(args, "api_key", None)
    translated_subs = run_translate(raw_subs, target_lang="Vietnamese", engine=engine, api_key=api_key)

    write_ass_file(translated_subs, output_ass)
    write_json_file(translated_subs, output_json)
    write_lines_file(translated_subs, output_lines)

    print("\n" + "=" * 60)
    print("🎉 HOÀN THÀNH QUÉT CHỮ VIDEO OCR & DỊCH THUẬT!")
    print(f"👉 File ASS   : {output_ass}")
    print(f"👉 File JSON  : {output_json}")
    print("=" * 60)

def handle_hybrid(args):
    video = os.path.abspath(args.video)
    if not os.path.exists(video):
        print(f"Lỗi: Không tìm thấy video tại '{video}'")
        sys.exit(1)

    base, _ = os.path.splitext(video)
    output_ass = args.output_ass or f"{base}_hybrid_vi.ass"
    output_json = args.output_json or f"{base}_hybrid_sub.json"
    output_lines = args.output_lines or f"{base}_hybrid_lines.txt"

    print("\n" + "=" * 60)
    print(" 🚀 CHẾ ĐỘ TỐI THƯỢNG: KẾT HỢP ÂM THANH (WHISPER) + QUÉT CHỮ (VIDEO OCR)")
    print("=" * 60)
    print(f"-> Video mục tiêu: {video}")

    # 1. Quét hình ảnh bằng RapidOCR
    sample_fps = getattr(args, "sample_fps", 1.8) or 1.8
    ocr_subs = run_video_ocr(video, sample_fps=sample_fps)

    # 2. Bóc tách âm thanh bằng Whisper CUDA
    model_size = getattr(args, "model_size", "small") or "small"
    source_lang = getattr(args, "source_lang", "auto") or "auto"
    audio_subs, lang = run_transcribe(video, model_size=model_size, source_lang=source_lang)

    # 3. Hợp nhất Đa phương thức
    print("\n-> Đang tiến hành Hợp nhất Đa phương thức (Multimodal Fusion Alignment)...")
    if ocr_subs and audio_subs:
        raw_subs = fuse_audio_and_ocr(ocr_subs, audio_subs)
    elif ocr_subs:
        print("-> Chỉ có kết quả từ OCR, sử dụng toàn bộ OCR.")
        raw_subs = ocr_subs
    elif audio_subs:
        print("-> Chỉ có kết quả từ Whisper, sử dụng toàn bộ Whisper.")
        raw_subs = audio_subs
    else:
        print("Không tìm thấy câu thoại nào từ cả âm thanh lẫn video.")
        sys.exit(1)

    # 4. Dịch ngữ cảnh AI
    engine = getattr(args, "engine", "gemini") or "gemini"
    api_key = getattr(args, "api_key", None)
    translated_subs = run_translate(raw_subs, target_lang="Vietnamese", engine=engine, api_key=api_key)

    write_ass_file(translated_subs, output_ass)
    write_json_file(translated_subs, output_json)
    write_lines_file(translated_subs, output_lines)

    print("\n" + "=" * 60)
    print("🎉 HOÀN THÀNH KẾT HỢP ĐA PHƯƠNG THỨC & DỊCH THUẬT AI!")
    print(f"👉 File ASS   : {output_ass}")
    print(f"👉 File JSON  : {output_json}")
    print(f"👉 File Lines : {output_lines}")
    print("=" * 60)

def handle_retranslate(args):
    sub = os.path.abspath(args.sub)
    if not os.path.exists(sub):
        print(f"Lỗi: Không tìm thấy file phụ đề tại '{sub}'")
        sys.exit(1)

    dialogues = parse_ass_dialogues(sub)
    if not dialogues:
        print("Lỗi: Không tìm thấy câu thoại hợp lệ nào trong file phụ đề.")
        sys.exit(1)

    subs_to_translate = []
    for idx, d in enumerate(dialogues, 1):
        subs_to_translate.append({
            "id": idx,
            "start": d["start"],
            "end": d["end"],
            "text": d["text"]
        })

    engine = getattr(args, "engine", "gemini") or "gemini"
    api_key = getattr(args, "api_key", None)
    translated_subs = run_translate(subs_to_translate, target_lang="Vietnamese", engine=engine, api_key=api_key)

    output_lines = getattr(args, "output_lines", None)
    if output_lines:
        write_lines_file(translated_subs, output_lines)

    output_ass = getattr(args, "output_ass", None) or sub
    write_ass_file(translated_subs, output_ass)

    print("\n" + "=" * 60)
    print("🎉 HOÀN THÀNH DỊCH LẠI PHỤ ĐỀ VỚI NGỮ CẢNH!")
    print(f"👉 File ASS   : {output_ass}")
    if output_lines:
        print(f"👉 File Lines : {output_lines}")
    print("=" * 60)

def parse_ass_timestamp(t_str: str) -> float:
    parts = t_str.strip().split(":")
    if len(parts) == 3:
        try:
            h = float(parts[0])
            m = float(parts[1])
            s = float(parts[2])
            return h * 3600.0 + m * 60.0 + s
        except Exception:
            return 0.0
    return 0.0

def clean_ass_text(text: str) -> str:
    cleaned = re.sub(r"\{.*?\}", "", text)
    cleaned = cleaned.replace(r"\N", " ").replace(r"\n", " ").replace(r"\h", " ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned

def parse_ass_dialogues(ass_path: str):
    dialogues = []
    if not os.path.exists(ass_path):
        return dialogues
    with open(ass_path, "r", encoding="utf-8-sig", errors="replace") as f:
        in_events = False
        format_keys = []
        for line in f:
            line_str = line.strip()
            if line_str.startswith("[") and line_str.endswith("]"):
                in_events = (line_str.lower() == "[events]")
                continue
            if in_events and line_str.lower().startswith("format:"):
                format_keys = [k.strip().lower() for k in line_str[len("Format:"):].split(",")]
            elif in_events and line_str.lower().startswith("dialogue:"):
                raw_data = line_str[len("Dialogue:"):].strip()
                if format_keys:
                    parts = raw_data.split(",", len(format_keys) - 1)
                    record = {k: v.strip() for k, v in zip(format_keys, parts)}
                    start = parse_ass_timestamp(record.get("start", "0:00:00.00"))
                    end = parse_ass_timestamp(record.get("end", "0:00:00.00"))
                    text = clean_ass_text(record.get("text", ""))
                    if text and end > start:
                        dialogues.append({"start": start, "end": end, "text": text})
                else:
                    parts = raw_data.split(",", 9)
                    if len(parts) == 10:
                        start = parse_ass_timestamp(parts[1])
                        end = parse_ass_timestamp(parts[2])
                        text = clean_ass_text(parts[9])
                        if text and end > start:
                            dialogues.append({"start": start, "end": end, "text": text})
    return dialogues

def parse_srt_timestamp(ts: str) -> float:
    ts = ts.strip().replace(",", ".")
    parts = ts.split(":")
    if len(parts) == 3:
        try:
            return float(parts[0]) * 3600.0 + float(parts[1]) * 60.0 + float(parts[2])
        except Exception:
            return 0.0
    return 0.0

def parse_srt_file(file_path: str):
    subs = []
    with open(file_path, "r", encoding="utf-8-sig", errors="replace") as f:
        content = f.read()

    content = content.replace("\r\n", "\n").replace("\r", "\n")
    blocks = re.split(r"\n\s*\n", content.strip())

    idx = 1
    for block in blocks:
        lines = [line.strip() for line in block.split("\n") if line.strip()]
        if not lines:
            continue
        time_line_idx = -1
        for i, line in enumerate(lines):
            if "-->" in line:
                time_line_idx = i
                break
        if time_line_idx == -1:
            continue

        time_part = lines[time_line_idx]
        text_lines = lines[time_line_idx + 1:]
        if not text_lines:
            continue

        m = re.search(r"(\d+:\d+:\d+[.,]\d+)\s*-->\s*(\d+:\d+:\d+[.,]\d+)", time_part)
        if m:
            start = parse_srt_timestamp(m.group(1))
            end = parse_srt_timestamp(m.group(2))
            raw_text = " ".join(text_lines)
            clean_text = re.sub(r"<[^>]+>", "", raw_text).strip()
            clean_text = re.sub(r"\{.*?\}", "", clean_text).strip()
            if clean_text and end > start:
                subs.append({
                    "id": idx,
                    "start": start,
                    "end": end,
                    "text": clean_text
                })
                idx += 1
    return subs

def parse_any_subtitle_file(file_path: str):
    _, ext = os.path.splitext(file_path.lower())
    if ext == ".ass":
        dialogues = parse_ass_dialogues(file_path)
        return [{"id": idx, "start": d["start"], "end": d["end"], "text": d["text"]} for idx, d in enumerate(dialogues, 1)]
    else:
        return parse_srt_file(file_path)

def handle_translate_file(args):
    sub_file = os.path.abspath(args.sub_file)
    if not os.path.exists(sub_file):
        print(f"Lỗi: Không tìm thấy file phụ đề tại '{sub_file}'")
        sys.exit(1)

    print("=" * 60)
    print("      ⚡ DỊCH TRỰC TIẾP FILE PHỤ ĐỀ CÓ SẴN (BỎ QUA BÓC TÁCH)")
    print("=" * 60)
    print(f"-> File phụ đề gốc: {sub_file}")

    subs = parse_any_subtitle_file(sub_file)
    if not subs:
        print("Lỗi: Không tìm thấy câu thoại hợp lệ nào trong file phụ đề.")
        sys.exit(1)

    print(f"-> Đã nạp thành công {len(subs)} câu thoại có sẵn mốc thời gian.")

    folder = os.path.dirname(sub_file)
    base = os.path.splitext(os.path.basename(sub_file))[0]
    output_ass = getattr(args, "output_ass", None) or os.path.join(folder, f"{base}_vi.ass")
    output_lines = getattr(args, "output_lines", None) or os.path.join(folder, f"{base}_ai_lines.txt")
    output_json = getattr(args, "output_json", None) or os.path.join(folder, f"{base}_ai_sub.json")

    engine = getattr(args, "engine", "gemini") or "gemini"
    api_key = getattr(args, "api_key", None)
    translated_subs = run_translate(subs, target_lang="Vietnamese", engine=engine, api_key=api_key)

    write_ass_file(translated_subs, output_ass)
    write_json_file(translated_subs, output_json)
    write_lines_file(translated_subs, output_lines)

    print("\n" + "=" * 60)
    print("🎉 DỊCH FILE PHỤ ĐỀ HOÀN TẤT THÀNH CÔNG!")
    print(f"👉 File ASS chuẩn : {output_ass}")
    print(f"👉 File JSON      : {output_json}")
    print(f"👉 File Lines     : {output_lines}")
    print("=" * 60)

def handle_tts(args):
    import numpy as np
    import soundfile as sf
    import librosa
    from vieneu import Vieneu

    sub = os.path.abspath(args.sub)
    if not os.path.exists(sub):
        print(f"Lỗi: Không tìm thấy file phụ đề tại '{sub}'")
        sys.exit(1)

    dialogues = parse_ass_dialogues(sub)
    if not dialogues:
        print("Lỗi: Không tìm thấy câu thoại hợp lệ nào trong file phụ đề.")
        sys.exit(1)

    video = os.path.abspath(args.video) if getattr(args, "video", None) else None
    if getattr(args, "output_audio", None):
        out_audio = os.path.abspath(args.output_audio)
    else:
        if video:
            folder = os.path.dirname(video)
            base = os.path.splitext(os.path.basename(video))[0]
            clean_base = base.replace("_blurred", "").replace("_Subbed", "")
            out_audio = os.path.join(folder, f"{clean_base}_dubbing.wav")
        else:
            folder = os.path.dirname(sub)
            base = os.path.splitext(os.path.basename(sub))[0]
            clean_base = base.replace("_blurred", "").replace("_Subbed", "")
            out_audio = os.path.join(folder, f"{clean_base}_dubbing.wav")

    voice = getattr(args, "voice", "Thiện Minh") or "Thiện Minh"
    ref_audio = getattr(args, "ref_audio", None)
    if ref_audio:
        ref_audio = os.path.abspath(ref_audio)
        if not os.path.exists(ref_audio):
            print(f"Cảnh báo: File âm thanh mẫu '{ref_audio}' không tồn tại. Sẽ dùng giọng mặc định '{voice}'.")
            ref_audio = None

    speed_adjust = getattr(args, "speed_adjust", True)
    if speed_adjust is None:
        speed_adjust = True

    print("=" * 60)
    print("      🎙️ TẠO GIỌNG ĐỌC THUYẾT MINH AI (VIENEU-TTS)")
    print("=" * 60)
    print(f"-> Phụ đề         : {sub}")
    if ref_audio:
        print(f"-> Chế độ giọng   : 🎯 SAO CHÉP GIỌNG (Voice Cloning: {ref_audio})")
    else:
        print(f"-> Giọng đọc mẫu  : {voice}")
    print(f"-> Số câu thoại   : {len(dialogues)}")
    print(f"-> Tự co giãn nhịp: {'BẬT (Khớp thời lượng phụ đề)' if speed_adjust else 'TẮT'}")
    print(f"-> Xuất audio ra  : {out_audio}")
    print("-" * 60)

    set_console_title("🎙️ Đang nạp mô hình VieNeu-TTS...")
    print("-> Đang khởi tạo mô hình VieNeu-TTS (v3 Turbo, 48kHz)...")
    tts = Vieneu(mode="v3turbo")
    sample_rate = 48000

    # Xác định độ dài tổng của track audio
    total_sec = 0.0
    if video and os.path.exists(video):
        total_sec = get_video_duration(video)
    if not total_sec or total_sec <= 0:
        total_sec = max(d["end"] for d in dialogues) + 2.0

    total_samples = int(math.ceil(total_sec * sample_rate))
    full_track = np.zeros(total_samples, dtype=np.float32)

    total_count = len(dialogues)
    for idx, d in enumerate(dialogues, 1):
        start_sec = d["start"]
        end_sec = d["end"]
        text = d["text"]
        slot_dur = max(0.4, end_sec - start_sec)

        pct = (idx / total_count) * 100.0
        preview = text[:35] + ("..." if len(text) > 35 else "")
        status_line = f"[{idx}/{total_count}] ({pct:4.1f}%) {format_sec(start_sec)}: \"{preview}\""
        print(f"-> {status_line}")
        set_console_title(f"🎙️ [{int(pct)}%] VieNeu-TTS: {idx}/{total_count} câu thoại")

        try:
            if ref_audio:
                clip_audio = tts.infer(text=text, ref_audio=ref_audio)
            else:
                clip_audio = tts.infer(text=text, voice=voice)

            if clip_audio is None or len(clip_audio) == 0:
                continue

            clip_audio = clip_audio.astype(np.float32)
            clip_dur = len(clip_audio) / float(sample_rate)

            # Co giãn tốc độ nếu câu nói quá dài so với slot phụ đề (tối đa 1.35x để giữ giọng tự nhiên)
            if speed_adjust and clip_dur > slot_dur:
                factor = min(1.35, clip_dur / slot_dur)
                if factor > 1.05:
                    try:
                        clip_audio = librosa.effects.time_stretch(clip_audio, rate=factor)
                    except Exception:
                        pass

            start_idx = int(round(start_sec * sample_rate))
            end_idx = start_idx + len(clip_audio)

            if end_idx > len(full_track):
                full_track = np.pad(full_track, (0, end_idx - len(full_track)))

            full_track[start_idx:end_idx] += clip_audio

        except Exception as e:
            print(f"   ⚠️ Lỗi câu {idx}: {e}")

    # Chống vỡ tiếng (Clipping prevention)
    max_peak = np.max(np.abs(full_track)) if len(full_track) > 0 else 0
    if max_peak > 0.95:
        full_track = (full_track / max_peak) * 0.95

    print("\n-> Đang lưu file âm thanh WAV 48kHz...")
    sf.write(out_audio, full_track, sample_rate, subtype="PCM_16")

    set_console_title("🎉 [100%] Hoàn thành lồng tiếng VieNeu-TTS!")
    print("\n" + "=" * 60)
    print("🎉 TẠO THUYẾT MINH AI THÀNH CÔNG 100%!")
    print(f"👉 File thuyết minh: {out_audio}")
    print("=" * 60)

def handle_export(args):
    video = os.path.abspath(args.video)
    sub = os.path.abspath(args.sub)
    if not os.path.exists(video):
        print(f"Lỗi: Không tìm thấy video tại '{video}'")
        sys.exit(1)
    if not os.path.exists(sub):
        print(f"Lỗi: Không tìm thấy file phụ đề tại '{sub}'")
        sys.exit(1)

    ffmpeg = get_ffmpeg()
    if not ffmpeg:
        print("Lỗi: Không tìm thấy ffmpeg.")
        sys.exit(1)

    if args.output:
        out_path = os.path.abspath(args.output)
    else:
        folder = os.path.dirname(video)
        base = os.path.basename(video)
        name, ext = os.path.splitext(base)
        clean_name = name.replace("_blurred", "")
        out_path = os.path.join(folder, f"{clean_name}_Subbed{ext}")

    # Chuẩn hóa path cho filter FFmpeg trên Windows
    sub_filter_path = sub.replace("\\", "/").replace(":", "\\:")
    quality = getattr(args, "quality", "1080p") or "1080p"

    dub_audio = getattr(args, "dub_audio", None)
    dub_mode = getattr(args, "dub_mode", "ducking") or "ducking"
    if dub_audio:
        dub_audio = os.path.abspath(dub_audio)
        if not os.path.exists(dub_audio):
            print(f"Cảnh báo: File thuyết minh '{dub_audio}' không tồn tại. Bỏ qua lồng tiếng.")
            dub_audio = None

    print("=" * 60)
    print("         BẮT ĐẦU XUẤT VIDEO (HARDSUB + LÀM MỜ LOGO)")
    print("=" * 60)
    print(f"-> Video gốc   : {video}")
    print(f"-> Phụ đề      : {sub}")
    print(f"-> Xóa logo    : {'CÓ (boxblur)' if args.blur_logo else 'KHÔNG'}")
    print(f"-> Chất lượng  : {quality.upper()} ({'Nâng cấp 1080p Full HD siêu nét' if quality == '1080p' else 'Gốc HQ'})")
    if dub_audio:
        print(f"-> Thuyết minh : {dub_audio} (Chế độ: {dub_mode})")
    print(f"-> Xuất ra     : {out_path}")
    print("-" * 60)

    # Cấu hình Encoder tối ưu
    if quality == "fast":
        enc_args = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p"]
    elif quality == "original_hq":
        enc_args = ["-c:v", "libx264", "-profile:v", "high", "-level", "4.2", "-preset", "medium", "-crf", "15", "-pix_fmt", "yuv420p"]
    else:  # "1080p" - Mặc định sắc nét nhất
        enc_args = ["-c:v", "libx264", "-profile:v", "high", "-level", "4.2", "-preset", "medium", "-crf", "15", "-pix_fmt", "yuv420p"]

    # Xây dựng bộ lọc video
    if quality == "1080p":
        if args.blur_logo:
            v_filter = f"[0:v]split[main][crop];[crop]crop=245:70:15:15,boxblur=15:5[blur];[main][blur]overlay=15:15,scale=1920:1080:flags=lanczos,subtitles='{sub_filter_path}'[vout]"
        else:
            v_filter = f"[0:v]scale=1920:1080:flags=lanczos,subtitles='{sub_filter_path}'[vout]"
    else:
        if args.blur_logo:
            v_filter = f"[0:v]split[main][crop];[crop]crop=245:70:15:15,boxblur=15:5[blur];[main][blur]overlay=15:15,subtitles='{sub_filter_path}'[vout]"
        else:
            v_filter = f"[0:v]subtitles='{sub_filter_path}'[vout]"

    inputs = [ffmpeg, "-y", "-i", video]
    has_orig_audio = check_video_has_audio(video)

    if dub_audio and dub_mode != "none":
        inputs.extend(["-i", dub_audio])
        if dub_mode == "ducking" and has_orig_audio:
            # Ducking: Hạ âm gốc xuống 20%, giọng AI 100%
            a_filter = "[0:a]volume=0.20[a_orig];[1:a]volume=1.0[a_dub];[a_orig][a_dub]amix=inputs=2:duration=first:dropout_transition=2[aout]"
            full_filter = f"{v_filter};{a_filter}"
            cmd = [
                *inputs,
                "-filter_complex", full_filter,
                "-map", "[vout]",
                "-map", "[aout]",
                *enc_args,
                "-c:a", "aac", "-b:a", "192k",
                out_path
            ]
        else:
            # Thay thế hoàn toàn bằng giọng AI
            cmd = [
                *inputs,
                "-filter_complex", v_filter,
                "-map", "[vout]",
                "-map", "1:a",
                *enc_args,
                "-c:a", "aac", "-b:a", "192k",
                out_path
            ]
    else:
        # Không lồng tiếng, giữ audio gốc
        cmd = [
            *inputs,
            "-filter_complex", v_filter,
            "-map", "[vout]",
            "-map", "0:a?",
            *enc_args,
            "-c:a", "copy",
            out_path
        ]

    returncode, stderr_err = run_ffmpeg_with_progress(cmd, video)

    if returncode == 0:
        set_console_title("🎉 [100%] Xuất Video Hoàn Thành!")
        print("\n\n" + "=" * 60)
        print("🎉 XUẤT VIDEO THÀNH CÔNG 100%!")
        print(f"👉 File thành phẩm: {out_path}")
        print("=" * 60)

        # Mở Windows Explorer trỏ trực tiếp đến file video vừa xuất
        if args.open_folder:
            try:
                subprocess.Popen(f'explorer /select,"{out_path}"')
            except Exception:
                pass
    else:
        print(f"\n❌ Lỗi khi xuất video (Exit code {returncode})")
        if stderr_err:
            print(stderr_err[-500:])
        sys.exit(returncode)

def handle_run_config(config_path):
    with open(config_path, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    task = cfg.get("task")
    if task == "transcribe":
        class Args:
            pass
        args = Args()
        args.video = cfg["video"]
        args.output_ass = cfg.get("output_ass")
        args.output_json = cfg.get("output_json")
        args.output_lines = cfg.get("output_lines")
        args.model_size = cfg.get("model_size", "small")
        args.source_lang = cfg.get("source_lang", "auto")
        args.engine = cfg.get("engine", "gemini")
        args.api_key = cfg.get("api_key")
        handle_transcribe(args)
    elif task == "retranslate":
        class Args:
            pass
        args = Args()
        args.sub = cfg["sub"]
        args.engine = cfg.get("engine", "gemini")
        args.api_key = cfg.get("api_key")
        args.output_lines = cfg.get("output_lines")
        args.output_ass = cfg.get("output_ass")
        handle_retranslate(args)
    elif task == "translate_file":
        class Args:
            pass
        args = Args()
        args.sub_file = cfg["sub_file"]
        args.engine = cfg.get("engine", "gemini")
        args.api_key = cfg.get("api_key")
        args.output_ass = cfg.get("output_ass")
        args.output_lines = cfg.get("output_lines")
        args.output_json = cfg.get("output_json")
        handle_translate_file(args)
    elif task == "tts":
        class Args:
            pass
        args = Args()
        args.sub = cfg["sub"]
        args.video = cfg.get("video")
        args.output_audio = cfg.get("output_audio")
        args.voice = cfg.get("voice", "Thiện Minh")
        args.ref_audio = cfg.get("ref_audio")
        args.speed_adjust = cfg.get("speed_adjust", True)
        handle_tts(args)
    elif task == "export":
        class Args:
            pass
        args = Args()
        args.video = cfg["video"]
        args.sub = cfg["sub"]
        args.output = cfg.get("output")
        args.quality = cfg.get("quality", "1080p")
        args.blur_logo = cfg.get("blur_logo", True)
        args.open_folder = cfg.get("open_folder", True)
        args.dub_audio = cfg.get("dub_audio")
        args.dub_mode = cfg.get("dub_mode", "ducking")
        handle_export(args)
    elif task == "video_ocr":
        class Args:
            pass
        args = Args()
        args.video = cfg["video"]
        args.engine = cfg.get("engine", "gemini")
        args.api_key = cfg.get("api_key")
        args.sample_fps = cfg.get("sample_fps", 1.8)
        args.output_ass = cfg.get("output_ass")
        args.output_lines = cfg.get("output_lines")
        args.output_json = cfg.get("output_json")
        handle_video_ocr(args)
    elif task == "hybrid":
        class Args:
            pass
        args = Args()
        args.video = cfg["video"]
        args.engine = cfg.get("engine", "gemini")
        args.api_key = cfg.get("api_key")
        args.model_size = cfg.get("model_size", "small")
        args.source_lang = cfg.get("source_lang", "auto")
        args.sample_fps = cfg.get("sample_fps", 1.8)
        args.output_ass = cfg.get("output_ass")
        args.output_lines = cfg.get("output_lines")
        args.output_json = cfg.get("output_json")
        handle_hybrid(args)
    else:
        print(f"Unknown task: {task}")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="Aegisub AI Subtitle Studio Pipeline")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Subcommand: run-config (An toàn tuyệt đối cho đường dẫn Unicode tiếng Trung/Việt)
    cfg_p = subparsers.add_parser("run-config")
    cfg_p.add_argument("--config", required=True, help="Đường dẫn file cấu hình JSON UTF-8")

    # Subcommand: hybrid (Kết hợp Đa phương thức: Âm thanh Whisper + Quét chữ RapidOCR)
    hy_p = subparsers.add_parser("hybrid")
    hy_p.add_argument("--video", required=True, help="Đường dẫn file video cần bóc tách đa phương thức")
    hy_p.add_argument("--model-size", default="small", help="Whisper model size (small, base, tiny, medium)")
    hy_p.add_argument("--source-lang", default="auto", help="Ngôn ngữ gốc (auto, zh, en, ...)")
    hy_p.add_argument("--engine", default="gemini", choices=["gemini", "deepseek", "hy_mt2"], help="Engine dịch thuật")
    hy_p.add_argument("--api-key", help="API Key cho Gemini hoặc DeepSeek")
    hy_p.add_argument("--sample-fps", type=float, default=1.8, help="Tốc độ quét OCR khung hình/giây")
    hy_p.add_argument("--output-ass", help="Đường dẫn file ASS xuất ra")
    hy_p.add_argument("--output-lines", help="Đường dẫn file Lines trung gian")
    hy_p.add_argument("--output-json", help="Đường dẫn file JSON trung gian")

    # Subcommand: video-ocr (Quét chữ hardsub trực tiếp trên màn hình video)
    ocr_p = subparsers.add_parser("video-ocr")
    ocr_p.add_argument("--video", required=True, help="Đường dẫn file video cần quét chữ OCR")
    ocr_p.add_argument("--engine", default="gemini", choices=["gemini", "deepseek", "hy_mt2"], help="Engine dịch thuật")
    ocr_p.add_argument("--api-key", help="API Key cho Gemini hoặc DeepSeek")
    ocr_p.add_argument("--sample-fps", type=float, default=1.8, help="Tốc độ quét khung hình/giây")
    ocr_p.add_argument("--output-ass", help="Đường dẫn file ASS xuất ra")
    ocr_p.add_argument("--output-lines", help="Đường dẫn file Lines trung gian")
    ocr_p.add_argument("--output-json", help="Đường dẫn file JSON trung gian")

    # Subcommand: transcribe
    trans_p = subparsers.add_parser("transcribe")
    trans_p.add_argument("--video", required=True, help="Đường dẫn file video")
    trans_p.add_argument("--output-ass", help="Đường dẫn file ASS xuất ra")
    trans_p.add_argument("--output-json", help="Đường dẫn file JSON trung gian")
    trans_p.add_argument("--output-lines", help="Đường dẫn file Lines trung gian (cho Aegisub)")
    trans_p.add_argument("--model-size", default="small", help="Whisper model size")
    trans_p.add_argument("--source-lang", default="auto", help="Ngôn ngữ gốc (auto, zh, en, ...)")
    trans_p.add_argument("--engine", default="gemini", choices=["gemini", "deepseek", "hy_mt2"], help="Engine dịch thuật")
    trans_p.add_argument("--api-key", help="API Key cho Gemini hoặc DeepSeek")

    # Subcommand: translate-file (Dịch trực tiếp file phụ đề SRT / ASS / VTT có sẵn mà không cần bóc tách)
    tf_p = subparsers.add_parser("translate-file")
    tf_p.add_argument("--sub-file", required=True, help="Đường dẫn file phụ đề có sẵn (.srt / .ass / .vtt)")
    tf_p.add_argument("--engine", default="gemini", choices=["gemini", "deepseek", "hy_mt2"], help="Engine dịch thuật")
    tf_p.add_argument("--api-key", help="API Key cho Gemini hoặc DeepSeek")
    tf_p.add_argument("--output-ass", help="Đường dẫn file ASS xuất ra")
    tf_p.add_argument("--output-lines", help="Đường dẫn file Lines trung gian")
    tf_p.add_argument("--output-json", help="Đường dẫn file JSON trung gian")

    # Subcommand: retranslate
    retrans_p = subparsers.add_parser("retranslate")
    retrans_p.add_argument("--sub", required=True, help="Đường dẫn file phụ đề (.ass)")
    retrans_p.add_argument("--engine", default="gemini", choices=["gemini", "deepseek", "hy_mt2"], help="Engine dịch thuật")
    retrans_p.add_argument("--api-key", help="API Key cho Gemini hoặc DeepSeek")
    retrans_p.add_argument("--output-lines", help="Đường dẫn file Lines trung gian")
    retrans_p.add_argument("--output-ass", help="Đường dẫn file ASS xuất ra")

    # Subcommand: tts
    tts_p = subparsers.add_parser("tts")
    tts_p.add_argument("--sub", required=True, help="Đường dẫn file phụ đề (.ass)")
    tts_p.add_argument("--video", help="Đường dẫn file video (để lấy thời lượng chuẩn)")
    tts_p.add_argument("--output-audio", help="Đường dẫn file audio xuất ra (.wav)")
    tts_p.add_argument("--voice", default="Thiện Minh", help="Tên giọng đọc mẫu")
    tts_p.add_argument("--ref-audio", help="Đường dẫn file âm thanh mẫu để clone giọng")
    tts_p.add_argument("--no-speed-adjust", dest="speed_adjust", action="store_false", help="Tắt tự động co giãn nhịp nói")
    tts_p.set_defaults(speed_adjust=True)

    # Subcommand: export
    exp_p = subparsers.add_parser("export")
    exp_p.add_argument("--video", required=True, help="Đường dẫn file video")
    exp_p.add_argument("--sub", required=True, help="Đường dẫn file phụ đề (.ass)")
    exp_p.add_argument("--output", help="Đường dẫn video xuất")
    exp_p.add_argument("--quality", default="1080p", choices=["1080p", "original_hq", "fast"], help="Chất lượng xuất")
    exp_p.add_argument("--blur-logo", action="store_true", help="Bật làm mờ logo góc trái")
    exp_p.add_argument("--open-folder", action="store_true", help="Mở thư mục chứa video sau khi xuất")
    exp_p.add_argument("--dub-audio", help="Đường dẫn file âm thanh thuyết minh (.wav)")
    exp_p.add_argument("--dub-mode", default="ducking", choices=["ducking", "replace", "none"], help="Chế độ lồng tiếng")

    args = parser.parse_args()

    if args.command == "run-config":
        handle_run_config(args.config)
    elif args.command == "video-ocr":
        handle_video_ocr(args)
    elif args.command == "transcribe":
        handle_transcribe(args)
    elif args.command == "translate-file":
        handle_translate_file(args)
    elif args.command == "retranslate":
        handle_retranslate(args)
    elif args.command == "tts":
        handle_tts(args)
    elif args.command == "export":
        handle_export(args)

if __name__ == "__main__":
    main()
