import os
import sys
import gc
import glob

# Đăng ký thư viện DLL NVIDIA (cuBLAS, cuDNN) cho Windows để CTranslate2 / Faster-Whisper nhận diện CUDA
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

    # Tự động quét và nạp các thư viện nvidia (cublas, cudnn)
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

import torch
from tqdm import tqdm

def format_timestamp(seconds: float) -> str:
    millis = int((seconds - int(seconds)) * 1000)
    mins, secs = divmod(int(seconds), 60)
    hours, mins = divmod(mins, 60)
    return f"{hours:02d}:{mins:02d}:{secs:02d},{millis:03d}"

def extract_and_transcribe(video_path: str):
    import ctranslate2
    from faster_whisper import WhisperModel
    print("\n[Bước 1/2] Đang nhận diện lời thoại bằng Whisper...")
    
    # GTX 1650 (4GB VRAM): Dùng ctranslate2 CUDA tăng tốc cực nhanh
    has_cuda = ctranslate2.get_cuda_device_count() > 0 or torch.cuda.is_available()
    device = "cuda" if has_cuda else "cpu"
    compute_type = "float16" if device == "cuda" else "int8"
    
    print(f"-> Chạy Whisper trên: {device.upper()} (Compute: {compute_type})")
    
    try:
        model = WhisperModel("small", device=device, compute_type=compute_type)
        segments, info = model.transcribe(video_path, beam_size=5)
    except Exception as e:
        if device == "cuda":
            print(f"-> CUDA gặp vấn đề ({e}), tự động chuyển sang chế độ CPU...")
            device = "cpu"
            compute_type = "int8"
            model = WhisperModel("small", device=device, compute_type=compute_type)
            segments, info = model.transcribe(video_path, beam_size=5)
        else:
            raise e
            
    print(f"-> Ngôn ngữ phát hiện trong video: {info.language} (Độ tin cậy: {info.language_probability:.2f})")
    
    subs = []
    for i, seg in enumerate(segments, 1):
        subs.append({
            "id": i,
            "start": seg.start,
            "end": seg.end,
            "text": seg.text.strip()
        })
    
    # Giải phóng VRAM cho Whisper trước khi nạp mô hình dịch
    del model
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        
    print(f"-> Đã nhận diện thành công {len(subs)} câu thoại.")
    return subs

def translate_subtitles(subs, target_lang="Vietnamese"):
    from transformers import AutoModelForCausalLM, AutoTokenizer
    print(f"\n[Bước 2/2] Đang nạp mô hình dịch Hy-MT2-1.8B...")
    
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
    
    print(f"-> Bắt đầu dịch {len(subs)} câu thoại sang tiếng Việt...")
    translated_subs = []
    
    for sub in tqdm(subs, desc="Tiến độ dịch"):
        source_text = sub["text"]
        if not source_text:
            translated_subs.append({**sub, "translated_text": ""})
            continue
            
        prompt = (
            f"Translate the following spoken subtitle into natural {target_lang}. "
            "Note that you should only output the translated result without any additional explanation:\n\n"
            f"{source_text}"
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
        
    return translated_subs

def save_to_srt(subs, output_srt_path: str):
    with open(output_srt_path, "w", encoding="utf-8") as f:
        for sub in subs:
            f.write(f"{sub['id']}\n")
            f.write(f"{format_timestamp(sub['start'])} --> {format_timestamp(sub['end'])}\n")
            f.write(f"{sub['translated_text']}\n\n")
    print(f"\n ĐÃ XUẤT THÀNH CÔNG FILE PHỤ ĐỀ: {output_srt_path}")

def main():
    if len(sys.argv) > 1:
        video_path = sys.argv[1].strip('\"\'')
    else:
        video_path = input("Nhập đường dẫn file video (hoặc kéo thả file video vào đây rồi ấn Enter): ").strip('\"\'')
        
    if not os.path.exists(video_path):
        print(f"Lỗi: Không tìm thấy file tại '{video_path}'")
        return

    base_name, _ = os.path.splitext(video_path)
    output_srt = f"{base_name}_vi.srt"
    
    # 1. Tách thoại
    subs = extract_and_transcribe(video_path)
    if not subs:
        print("Không tìm thấy thoại nào trong video.")
        return
        
    # 2. Dịch phụ đề
    translated_subs = translate_subtitles(subs, target_lang="Vietnamese")
    
    # 3. Xuất file SRT
    save_to_srt(translated_subs, output_srt)
    print("\n Mẹo sử dụng file SRT:")
    print("1. Đặt file .srt cùng tên và cùng thư mục với video để xem trên VLC/Media Player.")
    print("2. Hoặc kéo file .srt vào CapCut / Premiere / DaVinci Resolve để chỉnh sửa font chữ, hiệu ứng.")

if __name__ == "__main__":
    main()
