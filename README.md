# 🎬 Aegisub AI Studio

<div align="center">

![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python)
![Aegisub](https://img.shields.io/badge/Aegisub-Automation-ff69b4)
![Whisper](https://img.shields.io/badge/Speech%20Recognition-Faster--Whisper%20CUDA-green)
![OCR](https://img.shields.io/badge/OCR-RapidOCR%20ONNX-orange)
![AI Translation](https://img.shields.io/badge/AI%20Engine-Gemini%20%7C%20DeepSeek-purple)
![TTS](https://img.shields.io/badge/TTS-VieNeu--TTS%2048kHz-red)
![License](https://img.shields.io/badge/License-MIT-brightgreen)

**Xưởng Phụ Đề AI All-in-One Tích Hợp Trực Tiếp Vào Aegisub: Bóc Thoại ➔ Dịch Ngữ Cảnh Chuẩn Xưng Hô ➔ Thuyết Minh Giọng AI ➔ Xuất Hardsub Đỉnh Cao**

*Tác giả / Phát triển: **My Nuong** ([HCMUTE](https://hcmute.edu.vn))*

</div>

---

## 🌟 Giới Thiệu

**Aegisub AI Studio** là giải pháp tự động hóa toàn diện quy trình làm phụ đề và lồng tiếng video. Được tích hợp trực tiếp vào menu **Automation** của **Aegisub**, công cụ loại bỏ hoàn toàn các bước thủ công tốn hàng giờ đồng hồ, cho phép người sáng tạo nội dung xử lý video chuyên nghiệp chỉ với vài cú click chuột.

### Điểm Vượt Trội:
- **Đa phương thức kết hợp (Multimodal Fusion - Nghe & Nhìn)**: Kết hợp đồng thời âm thanh từ **Whisper** (khớp timeline chuẩn miligiây) và quét chữ từ **RapidOCR** (chuẩn 100% kịch bản gốc, cứu thoại khi nhạc nền quá to).
- **Dịch AI ngữ cảnh sâu (Gemini / DeepSeek)**: Hiểu trọn vẹn ngữ cảnh video, phân vai nhân vật chuẩn xưng hô (chàng - nàng, sư phụ - đồ nhi, tôi - bạn), không dịch máy móc theo từng câu rời rạc.
- **Thuyết minh AI (VieNeu-TTS 48 kHz)**: Hơn 25+ giọng đọc truyền cảm tự nhiên, hỗ trợ Voice Cloning và tự động co giãn nhịp nói theo timeline.
- **Render Hardsub & Xóa Logo 1 Click**: Tự động chèn phụ đề nét căng chuẩn 1080p, làm mờ watermark/logo nền tảng và hòa âm thông minh (Audio Ducking).

---

## 🧩 8 Tính Năng Tích Hợp Sẵn Trong Aegisub

Mở Aegisub ➔ Menu **Automation** ➔ **Aegisub AI Studio**:

1. **🚀 Kết Hợp Siêu Cấp: Âm Thanh (Whisper) + Quét Chữ (OCR) & Dịch Gemini** 👑
   - Lấy chữ từ OCR làm chuẩn kịch bản 100% (không lỗi từ đồng âm, tên riêng).
   - Lấy timeline từ Whisper để khớp đúng từng miligiây khẩu hình nhân vật.
   - Tự động cứu thoại bị nhạc nền (BGM) nuốt và giữ thoại ngoài khung hình (voice-over).
2. **🎯 Chỉ Quét Chữ Trên Video (Video OCR Chuẩn 100% Kịch Bản) & Dịch Gemini** ⚡
   - Quét phụ đề đáy video bằng **RapidOCR (ONNX)**, cực nhanh, nhẹ máy, không cần GPU mạnh.
3. **🎙️ Chỉ Bóc Giọng & Dịch (Whisper CUDA + AI Ngữ Cảnh)**
   - Phù hợp cho video chưa có chữ trên màn hình. Tự động nhận diện tiếng nói và dịch ngữ cảnh.
4. **⚡ Dịch Trực Tiếp File Phụ Đề Có Sẵn (.srt / .ass)**
   - Đã có file sub gốc, dịch toàn bộ kịch bản mượt mà chỉ trong 3-5 giây.
5. **🔄 Dịch Lại Phụ Đề Hiện Có Trên Lưới Aegisub**
   - Chuyển đổi và tinh chỉnh lời thoại đang mở bằng AI Gemini hoặc DeepSeek.
6. **🎙️ Tạo Thuyết Minh AI (VieNeu-TTS)**
   - Tạo track lồng tiếng chất lượng phòng thu 48 kHz, tự động canh nhịp thoại chuẩn xác.
7. **🎬 Xuất Video MP4 (Hardsub + Thuyết Minh + Xóa Logo)**
   - Render video hoàn chỉnh: làm mờ logo, chèn phụ đề hộp đen, hạ nhạc nền khi có giọng đọc.
8. **🎨 Định Dạng Kiểu Phụ Đề Chuẩn (Hộp Đen Che Chữ Gốc)**
   - Tự tạo style phụ đề nền đen chữ trắng viền rõ nét (Margin 55) che hoàn toàn sub gốc.

---

## 🚀 Cài Đặt Nhanh (Quick Start)

### 1. Yêu cầu hệ thống
- Hệ điều hành: **Windows 10 / 11 (64-bit)**
- **Aegisub 3.2.x+** đã cài trên máy.
- **Python 3.10 - 3.12** (Khuyên dùng Python 64-bit có hỗ trợ CUDA nếu dùng card NVIDIA).
- **FFmpeg** (đã có sẵn trong hệ thống hoặc thư viện static-ffmpeg).

### 2. Cài đặt thư viện Python
Mở Terminal / PowerShell tại thư mục dự án và chạy:
```bash
pip install -r requirements.txt
```

### 3. Cài đặt Plugin vào Aegisub
Nhấp đúp chuột vào file:
```bash
install_plugin.bat
```
Script sẽ tự động sao chép `ai_studio.lua` vào thư mục `%APPDATA%\Aegisub\automation\autoload`.

### 4. Cấu hình API Key AI (Gemini / DeepSeek)
Tạo file `ai_api_config.json` từ file mẫu `ai_api_config.example.json`:
```json
{
  "translation_engine": "gemini",
  "gemini_api_key": "YOUR_GEMINI_API_KEY",
  "deepseek_api_key": "YOUR_DEEPSEEK_API_KEY"
}
```
> 🔒 **Lưu ý bảo mật:** File `ai_api_config.json` đã được đưa vào `.gitignore` để tránh bị lộ khóa API khi push mã nguồn lên Git.

---

## 💻 Sử Dụng Bằng Lệnh (CLI)

Bạn cũng có thể chạy độc lập qua dòng lệnh mà không cần mở Aegisub UI:

- **Chế độ Kết hợp Tối thượng (Âm thanh + Quét chữ):**
```bash
python aegisub_pipeline.py hybrid --video "path/to/video.mp4" --engine gemini
```

- **Chế độ Chỉ quét chữ OCR:**
```bash
python aegisub_pipeline.py video-ocr --video "path/to/video.mp4" --engine gemini
```

- **Chế độ Bóc giọng nói Whisper:**
```bash
python aegisub_pipeline.py transcribe --video "path/to/video.mp4" --engine gemini
```

- **Chế độ Dịch lại file phụ đề:**
```bash
python aegisub_pipeline.py translate-file --sub "path/to/sub.srt" --engine gemini
```

---

## 🖥️ Web Studio Interface

Ngoài Aegisub, dự án còn đi kèm giao diện web trực quan để xem trước và xuất video:
```bash
run_studio.bat
```
Trình duyệt sẽ tự động mở tại `http://localhost:5000` với đầy đủ trình phát video xem trước vị trí phụ đề và khung làm mờ logo.

---

## 📁 Cấu Trúc Dự Án

```
Aegisub-AI-Studio/
├── aegisub_pipeline.py      # Pipeline xử lý chính (Whisper, OCR, LLM, TTS, FFmpeg)
├── ai_studio.lua            # Plugin Lua tích hợp trực tiếp vào Aegisub
├── app.py                   # Backend Flask máy chủ Web Studio
├── static/                  # Giao diện Web Studio (HTML/CSS/JS)
├── auto_sub.py              # Script bóc tách phụ đề nhanh
├── blur_logo.py             # Script làm mờ logo / watermark video
├── export_video.py          # Script render video hardsub và audio
├── install_plugin.bat       # Cài đặt 1-click plugin vào Aegisub
├── run_studio.bat           # Khởi động Web Studio
├── mo_aegisub.bat           # Mở Aegisub nhanh
├── ai_api_config.example.json # Mẫu cấu hình API Key an toàn
├── requirements.txt         # Danh sách thư viện Python phụ thuộc
├── LICENSE                  # Giấy phép mã nguồn mở MIT
└── README.md                # Tài liệu hướng dẫn sử dụng
```

---

## 📄 Bản Quyền & Giấy Phép (License)

Dự án được phát hành theo giấy phép mã nguồn mở [MIT License](LICENSE).
Bản quyền © 2026 **My Nuong**. Mọi quyền được bảo lưu.
