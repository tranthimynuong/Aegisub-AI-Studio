--[[
  =============================================================================
  Aegisub AI Studio - Plugin Tự Động Hóa Phụ Đề Cho Aegisub (Phiên Bản CapCut Pro)
  Tác giả: My Nuong
  Tính năng:
    1. Bóc tách giọng nói (Whisper CUDA) & Quét chữ video (RapidOCR)
    2. Dịch ngữ cảnh chuẩn xưng hô (Gemini / DeepSeek)
    3. Thuyết minh lồng tiếng AI (VieNeu-TTS)
    4. Xuất video MP4 (Hardsub nét căng + Làm mờ logo + Audio Ducking)
    5. Định dạng kiểu phụ đề chuẩn (Hộp đen che phụ đề cứng, Margin 55)
  =============================================================================
]]--

local tr = aegisub.gettext

script_name = "Aegisub AI Studio"
script_description = "Bộ công cụ AI Bóc thoại, Dịch thuật & Xuất Hardsub tự động trực tiếp trong Aegisub"
script_author = "My Nuong"
script_version = "2.0"

-- Kiểm tra file có tồn tại không
local function file_exists(path)
    if not path or path == "" then return false end
    local f = io.open(path, "r")
    if f then
        f:close()
        return true
    end
    return false
end

-- Tự động tìm thư mục dự án Aegisub-AI-Studio
local function find_script_dir()
    local candidates = {
        "D:\\Projects\\Aegisub-AI-Studio",
        "D:\\Projects\\Aegisub-AI-Studio\\video_subber",
        "C:\\Projects\\Aegisub-AI-Studio",
        os.getenv("AEGISUB_AI_STUDIO_DIR") or ""
    }
    for _, dir in ipairs(candidates) do
        if dir ~= "" and file_exists(dir .. "\\aegisub_pipeline.py") then
            return dir
        end
    end
    return "D:\\Projects\\Aegisub-AI-Studio"
end

-- Tự động tìm Python thực thi
local function find_python_exe(script_dir)
    local candidates = {
        "C:\\Users\\trant\\AppData\\Local\\Python\\pythoncore-3.12-64\\python.exe",
        script_dir .. "\\.venv\\Scripts\\python.exe",
        "python"
    }
    for _, py in ipairs(candidates) do
        if py == "python" or file_exists(py) then
            return py
        end
    end
    return "python"
end

local SCRIPT_DIR = find_script_dir()
local PYTHON_EXE = find_python_exe(SCRIPT_DIR)
local PIPELINE_PY = SCRIPT_DIR .. "\\aegisub_pipeline.py"

-- Thoát ký tự chuỗi JSON an toàn
local function escape_json_str(s)
    s = s:gsub('\\', '\\\\')
    s = s:gsub('"', '\\"')
    s = s:gsub('\n', '\\n')
    s = s:gsub('\r', '\\r')
    s = s:gsub('\t', '\\t')
    return s
end

-- Ghi file JSON cấu hình UTF-8
local function write_json_config(path, tbl)
    local f = io.open(path, "w")
    if not f then return false end
    f:write("{\n")
    local items = {}
    for k, v in pairs(tbl) do
        local val_str
        if type(v) == "string" then
            val_str = '"' .. escape_json_str(v) .. '"'
        elseif type(v) == "boolean" then
            val_str = v and "true" or "false"
        elseif type(v) == "number" then
            val_str = tostring(v)
        else
            val_str = "null"
        end
        table.insert(items, string.format('  "%s": %s', escape_json_str(k), val_str))
    end
    f:write(table.concat(items, ",\n"))
    f:write("\n}\n")
    f:close()
    return true
end

-- Cấu hình API Dịch thuật (Gemini / DeepSeek)
local API_CONFIG_JSON = SCRIPT_DIR .. "\\ai_api_config.json"

local function load_api_config()
    local cfg = {
        translation_engine = "gemini",
        gemini_api_key = "",
        deepseek_api_key = ""
    }
    local f = io.open(API_CONFIG_JSON, "r")
    if f then
        local content = f:read("*a")
        f:close()
        local g_key = content:match('"gemini_api_key"%s*:%s*"([^"]*)"')
        local d_key = content:match('"deepseek_api_key"%s*:%s*"([^"]*)"')
        local eng = content:match('"translation_engine"%s*:%s*"([^"]*)"')
        if g_key then cfg.gemini_api_key = g_key end
        if d_key then cfg.deepseek_api_key = d_key end
        if eng then cfg.translation_engine = eng end
    end
    return cfg
end

local function save_api_config(cfg)
    write_json_config(API_CONFIG_JSON, cfg)
end

-- Chuyển đổi mili-giây sang định dạng thời gian ASS: H:MM:SS.cs
local function ms_to_ass_time(ms)
    local total_cs = math.floor((ms or 0) / 10 + 0.5)
    local cs = total_cs % 100
    local total_s = math.floor(total_cs / 100)
    local s = total_s % 60
    local total_m = math.floor(total_s / 60)
    local m = total_m % 60
    local h = math.floor(total_m / 60)
    return string.format("%d:%02d:%02d.%02d", h, m, s, cs)
end

-- Tìm đường dẫn video hiện tại hoặc mặc định thư mục Downloads
local function get_current_or_default_video()
    local props = aegisub.project_properties()
    if props and props.video_file and props.video_file ~= "" and not props.video_file:match("^%?") then
        return props.video_file
    end
    return "D:\\Downloads"
end

-- Tìm đường dẫn phụ đề liên quan hoặc mặc định
local function get_current_or_default_sub()
    local props = aegisub.project_properties()
    if props and props.video_file and props.video_file ~= "" and not props.video_file:match("^%?") then
        local base = props.video_file:gsub("%.[^.]+$", "")
        if file_exists(base .. ".srt") then return base .. ".srt" end
        if file_exists(base .. ".ass") then return base .. ".ass" end
        if file_exists(base .. ".vtt") then return base .. ".vtt" end
        return base .. ".srt"
    end
    local fn = aegisub.file_name()
    if fn and fn ~= "" and (fn:match("%.srt$") or fn:match("%.ass$") or fn:match("%.vtt$")) then
        return fn
    end
    return "D:\\Downloads\\subtitle.srt"
end

-- Đảm bảo phong cách "Default" có hộp đen (Opaque Box) và Margin phù hợp
local function ensure_opaque_box_style(subs)
    local style_found = false
    for i = 1, #subs do
        local line = subs[i]
        if line.class == "style" and line.name == "Default" then
            line.fontname = "Segoe UI"
            line.fontsize = 24
            line.color1 = "&H00FFFFFF&" -- Chữ trắng
            line.color2 = "&H000000FF&"
            line.color3 = "&H00000000&" -- Viền đen
            line.color4 = "&H00000000&" -- Hộp đen
            line.bold = true
            line.borderstyle = 3       -- Hộp đen kín (Opaque Box)
            line.outline = 2.0
            line.shadow = 0
            line.align = 2            -- Đáy giữa
            line.margin_l = 20
            line.margin_r = 20
            line.margin_t = 55        -- Cách đáy 55px (che đè phụ đề tiếng Trung gốc)
            line.margin_b = 55
            subs[i] = line
            style_found = true
            break
        end
    end

    if not style_found then
        local new_style = {
            class = "style",
            name = "Default",
            fontname = "Segoe UI",
            fontsize = 24,
            color1 = "&H00FFFFFF&",
            color2 = "&H000000FF&",
            color3 = "&H00000000&",
            color4 = "&H00000000&",
            bold = true,
            italic = false,
            underline = false,
            strikeout = false,
            scale_x = 100,
            scale_y = 100,
            spacing = 0,
            angle = 0,
            borderstyle = 3,
            outline = 2.0,
            shadow = 0,
            align = 2,
            margin_l = 20,
            margin_r = 20,
            margin_t = 55,
            margin_b = 55,
            encoding = 1
        }
        local insert_pos = 1
        for i = 1, #subs do
            if subs[i].class == "dialogue" then
                insert_pos = i
                break
            end
            insert_pos = i + 1
        end
        subs.insert(insert_pos, new_style)
    end
end

-- Xuất phụ đề Aegisub ra file ASS tạm thời
local function export_subs_to_ass_file(subs, file_path)
    local f = io.open(file_path, "w")
    if not f then return false end

    f:write("[Script Info]\n")
    f:write("; Exported by Aegisub AI Studio\n")
    f:write("ScriptType: v4.00+\n")
    f:write("WrapStyle: 0\n")
    f:write("ScaledBorderAndShadow: yes\n")
    f:write("PlayResX: 1920\n")
    f:write("PlayResY: 1080\n\n")

    f:write("[V4+ Styles]\n")
    f:write("Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n")

    local has_default = false
    for i = 1, #subs do
        local line = subs[i]
        if line.class == "style" then
            if line.name == "Default" then has_default = true end
            f:write(string.format("Style: %s,%s,%g,%s,%s,%s,%s,%d,%d,%d,%d,%g,%g,%g,%g,%d,%g,%g,%d,%d,%d,%d,%d\n",
                line.name, line.fontname or "Segoe UI", line.fontsize or 24,
                line.color1 or "&H00FFFFFF&", line.color2 or "&H000000FF&",
                line.color3 or "&H00000000&", line.color4 or "&H00000000&",
                (line.bold and -1 or 0), (line.italic and -1 or 0),
                (line.underline and -1 or 0), (line.strikeout and -1 or 0),
                line.scale_x or 100, line.scale_y or 100,
                line.spacing or 0, line.angle or 0,
                line.borderstyle or 3, line.outline or 2.0, line.shadow or 0,
                line.align or 2, line.margin_l or 20, line.margin_r or 20,
                line.margin_t or 55, line.encoding or 1))
        end
    end
    if not has_default then
        f:write("Style: Default,Segoe UI,24,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,3,2,0,2,20,20,55,1\n")
    end

    f:write("\n[Events]\n")
    f:write("Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
    for i = 1, #subs do
        local line = subs[i]
        if line.class == "dialogue" and not line.comment then
            local s_time = ms_to_ass_time(line.start_time)
            local e_time = ms_to_ass_time(line.end_time)
            f:write(string.format("Dialogue: %d,%s,%s,%s,%s,%d,%d,%d,%s,%s\n",
                line.layer or 0, s_time, e_time, line.style or "Default",
                line.actor or "", line.margin_l or 0, line.margin_r or 0,
                line.margin_t or 0, line.effect or "", line.text or ""))
        end
    end

    f:close()
    return true
end

-- =============================================================================
-- 1. KẾT HỢP SIÊU CẤP: ÂM THANH (WHISPER) + QUÉT CHỮ (VIDEO OCR) & DỊCH AI
-- =============================================================================
local function macro_ai_hybrid(subs, sel)
    local default_video = get_current_or_default_video()
    local api_cfg = load_api_config()

    local engine_items = {
        "⭐ Google Gemini AI (Khuyên dùng - Ngữ cảnh toàn video, xưng hô chuẩn)",
        "⭐ DeepSeek V3 AI (Ngữ cảnh toàn video - Siêu mượt)",
        "💻 Offline Local (Tencent Hy-MT2 - Không cần mạng)"
    }
    local cur_eng_val = engine_items[1]
    if api_cfg.translation_engine == "deepseek" then
        cur_eng_val = engine_items[2]
    elseif api_cfg.translation_engine == "hy_mt2" then
        cur_eng_val = engine_items[3]
    end

    local cur_api_key = api_cfg.gemini_api_key
    if cur_eng_val:match("DeepSeek") then
        cur_api_key = api_cfg.deepseek_api_key
    end

    local dialog_config = {
        {class = "label", label = "Đường dẫn file Video cần bóc tách Đa phương thức:", x = 0, y = 0, width = 3, height = 1},
        {class = "edit", name = "video_path", text = default_video, x = 0, y = 1, width = 3, height = 1},

        {class = "label", label = "Công cụ Dịch thuật:", x = 0, y = 2, width = 1, height = 1},
        {class = "dropdown", name = "engine", items = engine_items, value = cur_eng_val, x = 1, y = 2, width = 2, height = 1},

        {class = "label", label = "API Key (Gemini / DeepSeek):", x = 0, y = 3, width = 1, height = 1},
        {class = "edit", name = "api_key", text = cur_api_key, x = 1, y = 3, width = 2, height = 1},

        {class = "label", label = "Mô hình Whisper (Âm thanh):", x = 0, y = 4, width = 1, height = 1},
        {class = "dropdown", name = "model_size", items = {"small (Khuyên dùng - GPU)", "base (Nhanh)", "tiny (Siêu nhanh)", "medium (Chính xác cao)"}, value = "small (Khuyên dùng - GPU)", x = 1, y = 4, width = 2, height = 1},

        {class = "label", label = "Tốc độ quét OCR (Hình ảnh):", x = 0, y = 5, width = 1, height = 1},
        {class = "dropdown", name = "speed_mode", items = {"Nhanh (1.8 fps - Khuyên dùng)", "Siêu nhanh (1.2 fps)", "Chi tiết từng giây (2.5 fps)"}, value = "Nhanh (1.8 fps - Khuyên dùng)", x = 1, y = 5, width = 2, height = 1},

        {class = "label", label = "🚀 TỐI THƯỢNG: Chữ chuẩn 100% kịch bản từ OCR + Timeline khớp miligiây từ âm thanh Whisper!", x = 0, y = 6, width = 3, height = 1},

        {class = "checkbox", name = "auto_style", label = "Tự động áp dụng Hộp Đen (Opaque Box) để che phụ đề gốc", value = true, x = 0, y = 7, width = 3, height = 1},
        {class = "checkbox", name = "clear_existing", label = "Xóa toàn bộ phụ đề cũ trong Aegisub trước khi nạp mới", value = true, x = 0, y = 8, width = 3, height = 1},
        {class = "checkbox", name = "keep_original", label = "Giữ câu tiếng gốc (Comment & Cột Actor) để soi đối chiếu song ngữ", value = true, x = 0, y = 9, width = 3, height = 1}
    }

    local btn, res = aegisub.dialog.display(dialog_config, {"🚀 Bắt đầu Kết Hợp Đa Phương Thức", "Hủy"})
    if btn ~= "🚀 Bắt đầu Kết Hợp Đa Phương Thức" then return end

    local video = res.video_path
    if not video or video == "" or not file_exists(video) then
        aegisub.dialog.display({{class = "label", label = "Không tìm thấy file video tại đường dẫn đã nhập!\nVui lòng kiểm tra lại đường dẫn video.", x = 0, y = 0, width = 2, height = 1}})
        return
    end

    local model_code = "small"
    if res.model_size:match("base") then
        model_code = "base"
    elseif res.model_size:match("tiny") then
        model_code = "tiny"
    elseif res.model_size:match("medium") then
        model_code = "medium"
    end

    local sample_fps = 1.8
    if res.speed_mode:match("Siêu nhanh") then
        sample_fps = 1.2
    elseif res.speed_mode:match("Chi tiết") then
        sample_fps = 2.5
    end

    local engine_code = "gemini"
    if res.engine:match("DeepSeek") then
        engine_code = "deepseek"
        if res.api_key and res.api_key ~= "" then
            api_cfg.deepseek_api_key = res.api_key
        end
    elseif res.engine:match("Offline") then
        engine_code = "hy_mt2"
    else
        engine_code = "gemini"
        if res.api_key and res.api_key ~= "" then
            api_cfg.gemini_api_key = res.api_key
        end
    end
    api_cfg.translation_engine = engine_code
    save_api_config(api_cfg)

    local temp_lines = SCRIPT_DIR .. "\\temp_ai_lines.txt"
    local config_json = SCRIPT_DIR .. "\\task_hybrid.json"
    os.remove(temp_lines)

    write_json_config(config_json, {
        task = "hybrid",
        video = video,
        engine = engine_code,
        api_key = res.api_key or "",
        model_size = model_code,
        source_lang = "auto",
        sample_fps = sample_fps,
        output_lines = temp_lines
    })

    local cmd = string.format('start "AI SUBTITLE STUDIO - KẾT HỢP ĐA PHƯƠNG THỨC (ÂM THANH + QUÉT CHỮ)" /wait cmd /c ""%s" "%s" run-config --config "%s" || pause"',
        PYTHON_EXE, PIPELINE_PY, config_json)

    os.execute(cmd)

    local f = io.open(temp_lines, "r")
    if not f then
        aegisub.dialog.display({{class = "label", label = "Quá trình xử lý đa phương thức đã bị hủy hoặc gặp lỗi.\nVui lòng kiểm tra lại cửa sổ tiến độ.", x = 0, y = 0, width = 2, height = 1}})
        return
    end

    local lines_data = {}
    for line in f:lines() do
        local s_ms, e_ms, raw_t, txt = line:match("^(%d+)|(%d+)|(.-)|(.*)$")
        if s_ms and e_ms and txt then
            table.insert(lines_data, {
                start_ms = tonumber(s_ms),
                end_ms = tonumber(e_ms),
                raw_text = raw_t,
                text = txt
            })
        end
    end
    f:close()

    if #lines_data == 0 then
        aegisub.dialog.display({{class = "label", label = "Không phát hiện thấy câu thoại nào từ cả âm thanh và video.", x = 0, y = 0, width = 2, height = 1}})
        return
    end

    if res.clear_existing then
        local i = 1
        while i <= #subs do
            if subs[i].class == "dialogue" then
                subs.delete(i)
            else
                i = i + 1
            end
        end
    end

    if res.auto_style then
        ensure_opaque_box_style(subs)
    end

    for _, item in ipairs(lines_data) do
        if res.keep_original and item.raw_text and item.raw_text ~= "" then
            local comment_dlg = {
                class = "dialogue",
                comment = true,
                layer = 0,
                start_time = item.start_ms,
                end_time = item.end_ms,
                style = "Default",
                actor = "GỐC",
                margin_l = 0, margin_r = 0, margin_t = 0,
                effect = "",
                text = "【GỐC】 " .. item.raw_text
            }
            subs.append(comment_dlg)
        end

        local dlg = {
            class = "dialogue",
            comment = false,
            layer = 0,
            start_time = item.start_ms,
            end_time = item.end_ms,
            style = "Default",
            actor = item.raw_text or "",
            margin_l = 0, margin_r = 0, margin_t = 0,
            effect = "",
            text = item.text
        }
        subs.append(dlg)
    end

    aegisub.set_undo_point("AI Kết Hợp Đa Phương Thức (Âm thanh + Quét chữ)")

    aegisub.dialog.display({
        {class = "label", label = string.format("🎉 THÀNH CÔNG RỰC RỠ!\nĐã kết hợp Âm thanh (Whisper) & Quét chữ (Video OCR) để tạo ra %d dòng phụ đề hoàn hảo!\n\nChữ chuẩn 100%% kịch bản, timeline khớp khít từng giây với giọng nói.", #lines_data), x = 0, y = 0, width = 3, height = 3}
    })
end

-- =============================================================================
-- 2. QUÉT CHỮ TRÊN MÀN HÌNH VIDEO (VIDEO OCR CHUẨN 100% KỊCH BẢN) & DỊCH AI
-- =============================================================================
local function macro_ai_video_ocr(subs, sel)
    local default_video = get_current_or_default_video()
    local api_cfg = load_api_config()

    local engine_items = {
        "⭐ Google Gemini AI (Khuyên dùng - Ngữ cảnh toàn video, xưng hô chuẩn)",
        "⭐ DeepSeek V3 AI (Ngữ cảnh toàn video - Siêu mượt)",
        "💻 Offline Local (Tencent Hy-MT2 - Không cần mạng)"
    }
    local cur_eng_val = engine_items[1]
    if api_cfg.translation_engine == "deepseek" then
        cur_eng_val = engine_items[2]
    elseif api_cfg.translation_engine == "hy_mt2" then
        cur_eng_val = engine_items[3]
    end

    local cur_api_key = api_cfg.gemini_api_key
    if cur_eng_val:match("DeepSeek") then
        cur_api_key = api_cfg.deepseek_api_key
    end

    local dialog_config = {
        {class = "label", label = "Đường dẫn file Video cần quét chữ Hardsub:", x = 0, y = 0, width = 3, height = 1},
        {class = "edit", name = "video_path", text = default_video, x = 0, y = 1, width = 3, height = 1},

        {class = "label", label = "Công cụ Dịch thuật:", x = 0, y = 2, width = 1, height = 1},
        {class = "dropdown", name = "engine", items = engine_items, value = cur_eng_val, x = 1, y = 2, width = 2, height = 1},

        {class = "label", label = "API Key (Gemini / DeepSeek):", x = 0, y = 3, width = 1, height = 1},
        {class = "edit", name = "api_key", text = cur_api_key, x = 1, y = 3, width = 2, height = 1},

        {class = "label", label = "Tốc độ quét OCR:", x = 0, y = 4, width = 1, height = 1},
        {class = "dropdown", name = "speed_mode", items = {"Nhanh (1.8 fps - Khuyên dùng)", "Siêu nhanh (1.2 fps)", "Chi tiết từng giây (2.5 fps)"}, value = "Nhanh (1.8 fps - Khuyên dùng)", x = 1, y = 4, width = 2, height = 1},

        {class = "label", label = "💡 Video OCR quét thẳng chữ Hán in trên hình ảnh video, chuẩn kịch bản 100%, không bị sót thoại!", x = 0, y = 5, width = 3, height = 1},

        {class = "checkbox", name = "auto_style", label = "Tự động áp dụng Hộp Đen (Opaque Box) để che phụ đề gốc", value = true, x = 0, y = 6, width = 3, height = 1},
        {class = "checkbox", name = "clear_existing", label = "Xóa toàn bộ phụ đề cũ trong Aegisub trước khi nạp mới", value = true, x = 0, y = 7, width = 3, height = 1},
        {class = "checkbox", name = "keep_original", label = "Giữ câu tiếng gốc (Comment & Cột Actor) để soi đối chiếu song ngữ", value = true, x = 0, y = 8, width = 3, height = 1}
    }

    local btn, res = aegisub.dialog.display(dialog_config, {"🔍 Bắt đầu Quét Chữ & Dịch", "Hủy"})
    if btn ~= "🔍 Bắt đầu Quét Chữ & Dịch" then return end

    local video = res.video_path
    if not video or video == "" or not file_exists(video) then
        aegisub.dialog.display({{class = "label", label = "Không tìm thấy file video tại đường dẫn đã nhập!\nVui lòng kiểm tra lại đường dẫn video.", x = 0, y = 0, width = 2, height = 1}})
        return
    end

    local sample_fps = 1.8
    if res.speed_mode:match("Siêu nhanh") then
        sample_fps = 1.2
    elseif res.speed_mode:match("Chi tiết") then
        sample_fps = 2.5
    end

    local engine_code = "gemini"
    if res.engine:match("DeepSeek") then
        engine_code = "deepseek"
        if res.api_key and res.api_key ~= "" then
            api_cfg.deepseek_api_key = res.api_key
        end
    elseif res.engine:match("Offline") then
        engine_code = "hy_mt2"
    else
        engine_code = "gemini"
        if res.api_key and res.api_key ~= "" then
            api_cfg.gemini_api_key = res.api_key
        end
    end
    api_cfg.translation_engine = engine_code
    save_api_config(api_cfg)

    local temp_lines = SCRIPT_DIR .. "\\temp_ai_lines.txt"
    local config_json = SCRIPT_DIR .. "\\task_video_ocr.json"
    os.remove(temp_lines)

    write_json_config(config_json, {
        task = "video_ocr",
        video = video,
        engine = engine_code,
        api_key = res.api_key or "",
        sample_fps = sample_fps,
        output_lines = temp_lines
    })

    local cmd = string.format('start "AI SUBTITLE STUDIO - QUÉT CHỮ HARDSUB VIDEO OCR & DỊCH" /wait cmd /c ""%s" "%s" run-config --config "%s" || pause"',
        PYTHON_EXE, PIPELINE_PY, config_json)

    os.execute(cmd)

    local f = io.open(temp_lines, "r")
    if not f then
        aegisub.dialog.display({{class = "label", label = "Quá trình quét OCR đã bị hủy hoặc gặp lỗi.\nVui lòng kiểm tra lại cửa sổ tiến độ.", x = 0, y = 0, width = 2, height = 1}})
        return
    end

    local lines_data = {}
    for line in f:lines() do
        local s_ms, e_ms, raw_t, txt = line:match("^(%d+)|(%d+)|(.-)|(.*)$")
        if s_ms and e_ms and txt then
            table.insert(lines_data, {
                start_ms = tonumber(s_ms),
                end_ms = tonumber(e_ms),
                raw_text = raw_t,
                text = txt
            })
        end
    end
    f:close()

    if #lines_data == 0 then
        aegisub.dialog.display({{class = "label", label = "Không phát hiện thấy câu chữ phụ đề nào trên video.", x = 0, y = 0, width = 2, height = 1}})
        return
    end

    if res.clear_existing then
        local i = 1
        while i <= #subs do
            if subs[i].class == "dialogue" then
                subs.delete(i)
            else
                i = i + 1
            end
        end
    end

    if res.auto_style then
        ensure_opaque_box_style(subs)
    end

    for _, item in ipairs(lines_data) do
        if res.keep_original and item.raw_text and item.raw_text ~= "" then
            local comment_dlg = {
                class = "dialogue",
                comment = true,
                layer = 0,
                start_time = item.start_ms,
                end_time = item.end_ms,
                style = "Default",
                actor = "GỐC",
                margin_l = 0, margin_r = 0, margin_t = 0,
                effect = "",
                text = "【GỐC】 " .. item.raw_text
            }
            subs.append(comment_dlg)
        end

        local dlg = {
            class = "dialogue",
            comment = false,
            layer = 0,
            start_time = item.start_ms,
            end_time = item.end_ms,
            style = "Default",
            actor = item.raw_text or "",
            margin_l = 0, margin_r = 0, margin_t = 0,
            effect = "",
            text = item.text
        }
        subs.append(dlg)
    end

    aegisub.set_undo_point("AI Quét Chữ Video OCR & Dịch Thuật")

    aegisub.dialog.display({
        {class = "label", label = string.format("🎉 THÀNH CÔNG! Đã bóc tách và dịch xong %d dòng phụ đề chuẩn 100%% từ hình ảnh video!\n\nToàn bộ chữ tiếng Trung gốc đã được lưu vào cột Actor để bạn dễ đối chiếu.", #lines_data), x = 0, y = 0, width = 3, height = 2}
    })
end

-- =============================================================================
-- 2. BÓC THOẠI & DỊCH THUẬT (WHISPER + AI NGỮ CẢNH)
-- =============================================================================
local function macro_ai_transcribe(subs, sel)
    local default_video = get_current_or_default_video()
    local api_cfg = load_api_config()

    local engine_items = {
        "⭐ Google Gemini AI (Khuyên dùng - Ngữ cảnh toàn video, xưng hô chuẩn)",
        "⭐ DeepSeek V3 AI (Ngữ cảnh toàn video - Siêu mượt)",
        "💻 Offline Local (Tencent Hy-MT2 - Không cần mạng)"
    }
    local cur_eng_val = engine_items[1]
    if api_cfg.translation_engine == "deepseek" then
        cur_eng_val = engine_items[2]
    elseif api_cfg.translation_engine == "hy_mt2" then
        cur_eng_val = engine_items[3]
    end

    local cur_api_key = api_cfg.gemini_api_key
    if cur_eng_val:match("DeepSeek") then
        cur_api_key = api_cfg.deepseek_api_key
    end

    local dialog_config = {
        {class = "label", label = "Đường dẫn file Video cần bóc thoại:", x = 0, y = 0, width = 3, height = 1},
        {class = "edit", name = "video_path", text = default_video, x = 0, y = 1, width = 3, height = 1},

        {class = "label", label = "Công cụ Dịch thuật:", x = 0, y = 2, width = 1, height = 1},
        {class = "dropdown", name = "engine", items = engine_items, value = cur_eng_val, x = 1, y = 2, width = 2, height = 1},

        {class = "label", label = "API Key (Gemini / DeepSeek):", x = 0, y = 3, width = 1, height = 1},
        {class = "edit", name = "api_key", text = cur_api_key, x = 1, y = 3, width = 2, height = 1},

        {class = "label", label = "Mô hình Whisper:", x = 0, y = 4, width = 1, height = 1},
        {class = "dropdown", name = "model_size", items = {"small (Khuyên dùng - Nhanh & Chuẩn)", "base (Siêu tốc)", "medium (Chính xác cao)"}, value = "small (Khuyên dùng - Nhanh & Chuẩn)", x = 1, y = 4, width = 2, height = 1},

        {class = "label", label = "Ngôn ngữ trong video:", x = 0, y = 5, width = 1, height = 1},
        {class = "dropdown", name = "source_lang", items = {"Tự động phát hiện (Auto)", "Tiếng Trung (zh)", "Tiếng Anh (en)"}, value = "Tự động phát hiện (Auto)", x = 1, y = 5, width = 2, height = 1},

        {class = "checkbox", name = "auto_style", label = "Tự động áp dụng Hộp Đen (Opaque Box) để che phụ đề gốc", value = true, x = 0, y = 6, width = 3, height = 1},
        {class = "checkbox", name = "clear_existing", label = "Xóa toàn bộ phụ đề cũ trong Aegisub trước khi nạp mới", value = true, x = 0, y = 7, width = 3, height = 1},
        {class = "checkbox", name = "keep_original", label = "Giữ câu tiếng gốc (Comment & Cột Actor) để soi đối chiếu song ngữ", value = true, x = 0, y = 8, width = 3, height = 1}
    }

    local btn, res = aegisub.dialog.display(dialog_config, {" Bắt đầu AI Dịch", "Hủy"})
    if btn ~= " Bắt đầu AI Dịch" then return end

    local video = res.video_path
    if not video or video == "" or video == "D:\\Downloads" then
        aegisub.dialog.display({{class = "label", label = "Vui lòng nhập đường dẫn file video hợp lệ!", x = 0, y = 0, width = 2, height = 1}})
        return
    end

    local model_code = "small"
    if res.model_size:match("^base") then model_code = "base"
    elseif res.model_size:match("^medium") then model_code = "medium" end

    local lang_code = "auto"
    if res.source_lang:match("zh") then lang_code = "zh"
    elseif res.source_lang:match("en") then lang_code = "en" end

    local engine_code = "gemini"
    if res.engine:match("DeepSeek") then
        engine_code = "deepseek"
        if res.api_key and res.api_key ~= "" then
            api_cfg.deepseek_api_key = res.api_key
        end
    elseif res.engine:match("Offline") then
        engine_code = "hy_mt2"
    else
        engine_code = "gemini"
        if res.api_key and res.api_key ~= "" then
            api_cfg.gemini_api_key = res.api_key
        end
    end
    api_cfg.translation_engine = engine_code
    save_api_config(api_cfg)

    -- File trao đổi dữ liệu
    local temp_lines = SCRIPT_DIR .. "\\temp_ai_lines.txt"
    local config_json = SCRIPT_DIR .. "\\task_transcribe.json"
    os.remove(temp_lines)

    -- Ghi config JSON UTF-8
    write_json_config(config_json, {
        task = "transcribe",
        video = video,
        model_size = model_code,
        source_lang = lang_code,
        engine = engine_code,
        api_key = res.api_key or "",
        output_lines = temp_lines
    })

    -- Khởi chạy Python qua cấu hình JSON an toàn tuyệt đối
    local cmd = string.format('start "AI SUBTITLE STUDIO - WHISPER & AI DỊCH" /wait cmd /c ""%s" "%s" run-config --config "%s" || pause"',
        PYTHON_EXE, PIPELINE_PY, config_json)

    os.execute(cmd)

    -- Đọc kết quả dòng phụ đề
    local f = io.open(temp_lines, "r")
    if not f then
        aegisub.dialog.display({{class = "label", label = "Quá trình dịch đã bị hủy hoặc gặp lỗi.\nVui lòng kiểm tra lại cửa sổ tiến độ.", x = 0, y = 0, width = 2, height = 1}})
        return
    end

    local lines_data = {}
    for line in f:lines() do
        local s_ms, e_ms, raw_t, txt = line:match("^(%d+)|(%d+)|(.-)|(.*)$")
        if s_ms and e_ms and txt then
            table.insert(lines_data, {
                start_ms = tonumber(s_ms),
                end_ms = tonumber(e_ms),
                raw_text = raw_t,
                text = txt
            })
        else
            local s_ms2, e_ms2, txt2 = line:match("^(%d+)|(%d+)|(.*)$")
            if s_ms2 and e_ms2 and txt2 then
                table.insert(lines_data, {
                    start_ms = tonumber(s_ms2),
                    end_ms = tonumber(e_ms2),
                    raw_text = "",
                    text = txt2
                })
            end
        end
    end
    f:close()

    if #lines_data == 0 then
        aegisub.dialog.display({{class = "label", label = "Không phát hiện thấy câu thoại nào trong video.", x = 0, y = 0, width = 2, height = 1}})
        return
    end

    -- Xóa dòng cũ nếu người dùng yêu cầu
    if res.clear_existing then
        local i = 1
        while i <= #subs do
            if subs[i].class == "dialogue" then
                subs.delete(i)
            else
                i = i + 1
            end
        end
    end

    -- Áp dụng kiểu Hộp Đen
    if res.auto_style then
        ensure_opaque_box_style(subs)
    end

    -- Nạp các dòng phụ đề mới vào bảng Aegisub (hỗ trợ dòng đối chiếu tiếng gốc)
    for _, item in ipairs(lines_data) do
        -- 1. Dòng chú thích tiếng gốc (Comment = true -> không render lên video thành phẩm)
        if res.keep_original and item.raw_text and item.raw_text ~= "" then
            local comment_dlg = {
                class = "dialogue",
                comment = true,
                layer = 0,
                start_time = item.start_ms,
                end_time = item.end_ms,
                style = "Default",
                actor = "GỐC",
                margin_l = 0,
                margin_r = 0,
                margin_t = 0,
                effect = "",
                text = "【GỐC】 " .. item.raw_text
            }
            subs.append(comment_dlg)
        end

        -- 2. Dòng dịch tiếng Việt (hiển thị câu gốc ở cột Actor để soi trực tiếp)
        local dlg = {
            class = "dialogue",
            comment = false,
            layer = 0,
            start_time = item.start_ms,
            end_time = item.end_ms,
            style = "Default",
            actor = item.raw_text or "",
            margin_l = 0,
            margin_r = 0,
            margin_t = 0,
            effect = "",
            text = item.text
        }
        subs.append(dlg)
    end

    aegisub.set_undo_point("AI Bóc Thoại & Dịch Tự Động")

    aegisub.dialog.display({
        {class = "label", label = string.format("🎉 THÀNH CÔNG! Đã nạp %d dòng phụ đề tiếng Việt vào Aegisub!\n\nBạn có thể nhấn Phím Cách (Space) để nghe và chỉnh sửa từng câu ngay trên timeline.", #lines_data), x = 0, y = 0, width = 3, height = 2}
    })
end

-- =============================================================================
-- 2. DỊCH TRỰC TIẾP FILE PHỤ ĐỀ CÓ SẴN (.SRT / .ASS / .VTT) - BỎ QUA BÓC TÁCH
-- =============================================================================
local function macro_ai_translate_file(subs, sel)
    local default_sub = get_current_or_default_sub()
    local api_cfg = load_api_config()

    local engine_items = {
        "⭐ Google Gemini AI (Khuyên dùng - Ngữ cảnh toàn video, xưng hô chuẩn)",
        "⭐ DeepSeek V3 AI (Ngữ cảnh toàn video - Siêu mượt)",
        "💻 Offline Local (Tencent Hy-MT2 - Không cần mạng)"
    }
    local cur_eng_val = engine_items[1]
    if api_cfg.translation_engine == "deepseek" then
        cur_eng_val = engine_items[2]
    elseif api_cfg.translation_engine == "hy_mt2" then
        cur_eng_val = engine_items[3]
    end

    local cur_api_key = api_cfg.gemini_api_key
    if cur_eng_val:match("DeepSeek") then
        cur_api_key = api_cfg.deepseek_api_key
    end

    local dialog_config = {
        {class = "label", label = "Đường dẫn file Phụ đề có sẵn (.srt / .ass / .vtt):", x = 0, y = 0, width = 3, height = 1},
        {class = "edit", name = "sub_file", text = default_sub, x = 0, y = 1, width = 3, height = 1},

        {class = "label", label = "Công cụ Dịch thuật:", x = 0, y = 2, width = 1, height = 1},
        {class = "dropdown", name = "engine", items = engine_items, value = cur_eng_val, x = 1, y = 2, width = 2, height = 1},

        {class = "label", label = "API Key (Gemini / DeepSeek):", x = 0, y = 3, width = 1, height = 1},
        {class = "edit", name = "api_key", text = cur_api_key, x = 1, y = 3, width = 2, height = 1},

        {class = "checkbox", name = "auto_style", label = "Tự động áp dụng Hộp Đen (Opaque Box) để che phụ đề gốc", value = true, x = 0, y = 4, width = 3, height = 1},
        {class = "checkbox", name = "clear_existing", label = "Xóa toàn bộ phụ đề cũ trong Aegisub trước khi nạp mới", value = true, x = 0, y = 5, width = 3, height = 1},
        {class = "checkbox", name = "keep_original", label = "Giữ câu tiếng gốc (Comment & Cột Actor) để soi đối chiếu song ngữ", value = true, x = 0, y = 6, width = 3, height = 1}
    }

    local btn, res = aegisub.dialog.display(dialog_config, {"⚡ Bắt đầu Dịch File", "Hủy"})
    if btn ~= "⚡ Bắt đầu Dịch File" then return end

    local sub_file = res.sub_file
    if not sub_file or sub_file == "" or not file_exists(sub_file) then
        local d_count = 0
        for i = 1, #subs do
            if subs[i].class == "dialogue" then
                d_count = d_count + 1
            end
        end
        if d_count > 0 then
            -- Tự động xuất phụ đề đang mở trên màn hình Aegisub thành file tạm để dịch ngay!
            local temp_current = SCRIPT_DIR .. "\\temp_render.ass"
            if export_subs_to_ass_file(subs, temp_current) then
                sub_file = temp_current
            else
                aegisub.dialog.display({{class = "label", label = "Lỗi: Không thể xuất phụ đề tạm thời từ Aegisub.", x = 0, y = 0, width = 2, height = 1}})
                return
            end
        else
            aegisub.dialog.display({{
                class = "label",
                label = "Không tìm thấy file phụ đề tại đường dẫn đã nhập!\n\nVui lòng dán đường dẫn file .srt / .ass cần dịch vào ô.",
                x = 0, y = 0, width = 3, height = 2
            }})
            return
        end
    end

    local engine_code = "gemini"
    if res.engine:match("DeepSeek") then
        engine_code = "deepseek"
        if res.api_key and res.api_key ~= "" then
            api_cfg.deepseek_api_key = res.api_key
        end
    elseif res.engine:match("Offline") then
        engine_code = "hy_mt2"
    else
        engine_code = "gemini"
        if res.api_key and res.api_key ~= "" then
            api_cfg.gemini_api_key = res.api_key
        end
    end
    api_cfg.translation_engine = engine_code
    save_api_config(api_cfg)

    local temp_lines = SCRIPT_DIR .. "\\temp_ai_lines.txt"
    local config_json = SCRIPT_DIR .. "\\task_translate_file.json"
    os.remove(temp_lines)

    write_json_config(config_json, {
        task = "translate_file",
        sub_file = sub_file,
        engine = engine_code,
        api_key = res.api_key or "",
        output_lines = temp_lines
    })

    local cmd = string.format('start "AI SUBTITLE STUDIO - DỊCH TRỰC TIẾP FILE PHỤ ĐỀ" /wait cmd /c ""%s" "%s" run-config --config "%s" || pause"',
        PYTHON_EXE, PIPELINE_PY, config_json)

    os.execute(cmd)

    local f = io.open(temp_lines, "r")
    if not f then
        aegisub.dialog.display({{class = "label", label = "Quá trình dịch đã bị hủy hoặc gặp lỗi.\nVui lòng kiểm tra lại cửa sổ tiến độ.", x = 0, y = 0, width = 2, height = 1}})
        return
    end

    local lines_data = {}
    for line in f:lines() do
        local s_ms, e_ms, raw_t, txt = line:match("^(%d+)|(%d+)|(.-)|(.*)$")
        if s_ms and e_ms and txt then
            table.insert(lines_data, {
                start_ms = tonumber(s_ms),
                end_ms = tonumber(e_ms),
                raw_text = raw_t,
                text = txt
            })
        else
            local s_ms2, e_ms2, txt2 = line:match("^(%d+)|(%d+)|(.*)$")
            if s_ms2 and e_ms2 and txt2 then
                table.insert(lines_data, {
                    start_ms = tonumber(s_ms2),
                    end_ms = tonumber(e_ms2),
                    raw_text = "",
                    text = txt2
                })
            end
        end
    end
    f:close()

    if #lines_data == 0 then
        aegisub.dialog.display({{class = "label", label = "Không phát hiện thấy câu thoại nào trong file phụ đề.", x = 0, y = 0, width = 2, height = 1}})
        return
    end

    if res.clear_existing then
        local i = 1
        while i <= #subs do
            if subs[i].class == "dialogue" then
                subs.delete(i)
            else
                i = i + 1
            end
        end
    end

    if res.auto_style then
        ensure_opaque_box_style(subs)
    end

    for _, item in ipairs(lines_data) do
        if res.keep_original and item.raw_text and item.raw_text ~= "" then
            local comment_dlg = {
                class = "dialogue",
                comment = true,
                layer = 0,
                start_time = item.start_ms,
                end_time = item.end_ms,
                style = "Default",
                actor = "GỐC",
                margin_l = 0,
                margin_r = 0,
                margin_t = 0,
                effect = "",
                text = item.raw_text
            }
            subs.append(comment_dlg)
        end

        local dlg = {
            class = "dialogue",
            comment = false,
            layer = 0,
            start_time = item.start_ms,
            end_time = item.end_ms,
            style = "Default",
            actor = item.raw_text or "",
            margin_l = 0,
            margin_r = 0,
            margin_t = 0,
            effect = "",
            text = item.text
        }
        subs.append(dlg)
    end

    aegisub.set_undo_point("Dịch trực tiếp file phụ đề SRT/ASS")

    aegisub.dialog.display({
        {class = "label", label = string.format("🎉 THÀNH CÔNG! Đã dịch và nạp %d dòng phụ đề tiếng Việt từ file có sẵn!\n\n⚡ Đã bỏ qua 100%% bước bóc tách Whisper, tiết kiệm tối đa thời gian & VRAM!", #lines_data), x = 0, y = 0, width = 3, height = 2}
    })
end


-- =============================================================================
-- 2. DỊCH LẠI BẰNG AI NGỮ CẢNH (GEMINI / DEEPSEEK)
-- =============================================================================
local function macro_ai_retranslate(subs, sel)
    local dialogue_count = 0
    for i = 1, #subs do
        if subs[i].class == "dialogue" then
            dialogue_count = dialogue_count + 1
        end
    end

    if dialogue_count == 0 then
        aegisub.dialog.display({{class = "label", label = "Aegisub chưa có dòng phụ đề nào để dịch lại!", x = 0, y = 0, width = 2, height = 1}})
        return
    end

    local api_cfg = load_api_config()

    local engine_items = {
        "⭐ Google Gemini AI (Khuyên dùng - Ngữ cảnh toàn video, xưng hô chuẩn)",
        "⭐ DeepSeek V3 AI (Ngữ cảnh toàn video - Siêu mượt)",
        "💻 Offline Local (Tencent Hy-MT2 - Không cần mạng)"
    }
    local cur_eng_val = engine_items[1]
    if api_cfg.translation_engine == "deepseek" then
        cur_eng_val = engine_items[2]
    elseif api_cfg.translation_engine == "hy_mt2" then
        cur_eng_val = engine_items[3]
    end

    local cur_api_key = api_cfg.gemini_api_key
    if cur_eng_val:match("DeepSeek") then
        cur_api_key = api_cfg.deepseek_api_key
    end

    local dialog_config = {
        {class = "label", label = "Chọn công cụ AI Dịch lại:", x = 0, y = 0, width = 1, height = 1},
        {class = "dropdown", name = "engine", items = engine_items, value = cur_eng_val, x = 1, y = 0, width = 2, height = 1},

        {class = "label", label = "API Key (Gemini / DeepSeek):", x = 0, y = 1, width = 1, height = 1},
        {class = "edit", name = "api_key", text = cur_api_key, x = 1, y = 1, width = 2, height = 1},

        {class = "label", label = "💡 AI sẽ đọc hiểu toàn bộ câu chuyện và tự khớp xưng hô (Anh-Em, Huynh-Muội, Tôi-Cô...)", x = 0, y = 2, width = 3, height = 1}
    }

    local btn, res = aegisub.dialog.display(dialog_config, {" Dịch Lại Ngay", "Hủy"})
    if btn ~= " Dịch Lại Ngay" then return end

    local engine_code = "gemini"
    if res.engine:match("DeepSeek") then
        engine_code = "deepseek"
        if res.api_key and res.api_key ~= "" then
            api_cfg.deepseek_api_key = res.api_key
        end
    elseif res.engine:match("Offline") then
        engine_code = "hy_mt2"
    else
        engine_code = "gemini"
        if res.api_key and res.api_key ~= "" then
            api_cfg.gemini_api_key = res.api_key
        end
    end
    api_cfg.translation_engine = engine_code
    save_api_config(api_cfg)

    local temp_ass = SCRIPT_DIR .. "\\temp_render.ass"
    if not export_subs_to_ass_file(subs, temp_ass) then
        aegisub.dialog.display({{class = "label", label = "Lỗi: Không thể ghi file phụ đề tạm thời.", x = 0, y = 0, width = 2, height = 1}})
        return
    end

    local temp_lines = SCRIPT_DIR .. "\\temp_ai_lines.txt"
    os.remove(temp_lines)

    local config_json = SCRIPT_DIR .. "\\task_retranslate.json"
    write_json_config(config_json, {
        task = "retranslate",
        sub = temp_ass,
        engine = engine_code,
        api_key = res.api_key or "",
        output_lines = temp_lines
    })

    local cmd = string.format('start "AI SUBTITLE STUDIO - DỊCH LẠI NGỮ CẢNH" /wait cmd /c ""%s" "%s" run-config --config "%s" || pause"',
        PYTHON_EXE, PIPELINE_PY, config_json)

    os.execute(cmd)

    local f = io.open(temp_lines, "r")
    if not f then
        aegisub.dialog.display({{class = "label", label = "Quá trình dịch đã bị hủy hoặc gặp lỗi.\nVui lòng kiểm tra lại cửa sổ tiến độ.", x = 0, y = 0, width = 2, height = 1}})
        return
    end

    local lines_data = {}
    for line in f:lines() do
        local s_ms, e_ms, raw_t, txt = line:match("^(%d+)|(%d+)|(.-)|(.*)$")
        if s_ms and e_ms and txt then
            table.insert(lines_data, {
                start_ms = tonumber(s_ms),
                end_ms = tonumber(e_ms),
                raw_text = raw_t,
                text = txt
            })
        end
    end
    f:close()

    if #lines_data == 0 then
        aegisub.dialog.display({{class = "label", label = "Không có dòng phụ đề mới nào được nạp.", x = 0, y = 0, width = 2, height = 1}})
        return
    end

    -- Cập nhật bản dịch mới vào các dòng dialogue hiện có
    local d_idx = 1
    for i = 1, #subs do
        local line = subs[i]
        if line.class == "dialogue" and d_idx <= #lines_data then
            line.text = lines_data[d_idx].text
            subs[i] = line
            d_idx = d_idx + 1
        end
    end

    aegisub.set_undo_point("Dịch lại bằng AI Ngữ Cảnh")

    aegisub.dialog.display({
        {class = "label", label = string.format("🎉 Đã dịch lại thành công %d dòng phụ đề với AI Ngữ Cảnh!\nXưng hô và văn phong đã được chuẩn hóa đồng bộ toàn video.", #lines_data), x = 0, y = 0, width = 3, height = 2}
    })
end

-- =============================================================================
-- 3. TẠO THUYẾT MINH TIẾNG VIỆT (VIENEU-TTS)
-- =============================================================================
local function macro_ai_tts(subs, sel)
    local dialogue_count = 0
    for i = 1, #subs do
        if subs[i].class == "dialogue" then
            dialogue_count = dialogue_count + 1
        end
    end

    if dialogue_count == 0 then
        aegisub.dialog.display({{class = "label", label = "Aegisub chưa có dòng phụ đề nào để tạo thuyết minh!", x = 0, y = 0, width = 2, height = 1}})
        return
    end

    local default_video = get_current_or_default_video()

    local voice_options = {
        "⭐ Thiện Minh (Nam Bắc · Review phim / Kể chuyện)",
        "⭐ Trúc Ly (Nữ Bắc · Tự nhiên / Truyền cảm)",
        "⭐ Adam bựa (Nam Bắc · Hài hước / Tự nhiên)",
        "⭐ Thùy Dung (Nữ Nam · Tin tức / Truyền cảm)",
        "⭐ Mai Anh (Nữ Bắc · Tin tức)",
        "⭐ Hải Đăng (Nam Bắc · Tự nhiên)",
        "⭐ Quang Sơn (Nam Trung · Tự nhiên)",
        "⭐ Thái Sơn (Nam Nam · Kể chuyện)",
        "⭐ Quỳnh Anh (Nữ Bắc · Đọc truyện)",
        "⭐ Mỹ Duyên (Nữ Nam · Đọc truyện)",
        "⭐ Ngọc Huyền (Nữ Bắc · Tự nhiên)",
        "⭐ Ngọc Trân (Nữ Trung · Tự nhiên)",
        "🎯 [Sao Chép Giọng - Voice Cloning] (File audio mẫu 3-10s)"
    }

    local dialog_config = {
        {class = "label", label = "Chọn Giọng đọc AI (VieNeu-TTS):", x = 0, y = 0, width = 1, height = 1},
        {class = "dropdown", name = "voice", items = voice_options, value = voice_options[1], x = 1, y = 0, width = 2, height = 1},

        {class = "label", label = "File âm thanh mẫu để Clone giọng (tùy chọn):", x = 0, y = 1, width = 3, height = 1},
        {class = "edit", name = "ref_audio", text = "", x = 0, y = 2, width = 3, height = 1},

        {class = "label", label = "File Video nguồn (để lấy thời lượng chuẩn):", x = 0, y = 3, width = 3, height = 1},
        {class = "edit", name = "video_path", text = default_video, x = 0, y = 4, width = 3, height = 1},

        {class = "checkbox", name = "speed_adjust", label = "Tự động co giãn nhịp nói (Auto-fit) để khớp độ dài từng câu phụ đề", value = true, x = 0, y = 5, width = 3, height = 1}
    }

    local btn, res = aegisub.dialog.display(dialog_config, {"🎙️ Bắt đầu tạo Thuyết Minh", "Hủy"})
    if btn ~= "🎙️ Bắt đầu tạo Thuyết Minh" then return end

    local is_clone = res.voice:match("Sao Chép Giọng")
    local ref_audio_val = res.ref_audio or ""
    if is_clone and ref_audio_val == "" then
        aegisub.dialog.display({{class = "label", label = "Bạn đã chọn 'Sao Chép Giọng' nhưng chưa nhập đường dẫn file âm thanh mẫu (.mp3 / .wav)!", x = 0, y = 0, width = 3, height = 1}})
        return
    end

    -- Trích xuất tên giọng
    local voice_name = "Thiện Minh"
    if not is_clone then
        voice_name = res.voice:match("^⭐%s*(.-)%s*%(") or res.voice
        voice_name = voice_name:match("^%s*(.-)%s*$")
    end

    local temp_ass = SCRIPT_DIR .. "\\temp_render.ass"
    if not export_subs_to_ass_file(subs, temp_ass) then
        aegisub.dialog.display({{class = "label", label = "Lỗi: Không thể ghi file phụ đề tạm thời.", x = 0, y = 0, width = 2, height = 1}})
        return
    end

    local config_json = SCRIPT_DIR .. "\\task_tts.json"
    write_json_config(config_json, {
        task = "tts",
        sub = temp_ass,
        video = res.video_path,
        voice = voice_name,
        ref_audio = is_clone and ref_audio_val or "",
        speed_adjust = res.speed_adjust
    })

    local cmd = string.format('start "AI SUBTITLE STUDIO - TẠO THUYẾT MINH VIENEU-TTS" /wait cmd /c ""%s" "%s" run-config --config "%s" || pause"',
        PYTHON_EXE, PIPELINE_PY, config_json)

    os.execute(cmd)

    aegisub.dialog.display({
        {class = "label", label = "🎉 Quá trình tạo giọng thuyết minh AI hoàn tất!\nFile audio đã được tạo (WAV 48kHz chuẩn phòng thu).\n\n👉 Bạn hãy vào menu 'AI Studio / 3. Xuất Video MP4' để tự động ghép giọng thuyết minh này vào video (hòa âm Ducking chuẩn review phim)!", x = 0, y = 0, width = 3, height = 3}
    })
end

-- =============================================================================
-- 3. XUẤT VIDEO MP4 (HARDSUB + THUYẾT MINH + XÓA LOGO)
-- =============================================================================
local function macro_ai_export(subs, sel)
    local dialogue_count = 0
    for i = 1, #subs do
        if subs[i].class == "dialogue" then
            dialogue_count = dialogue_count + 1
        end
    end

    if dialogue_count == 0 then
        aegisub.dialog.display({{class = "label", label = "Aegisub chưa có dòng phụ đề nào để xuất!", x = 0, y = 0, width = 2, height = 1}})
        return
    end

    local default_video = get_current_or_default_video()
    local default_dub = ""
    if default_video and default_video ~= "" and default_video ~= "D:\\Downloads" then
        local folder = default_video:match("^(.*)[/\\]")
        local fname = default_video:match("[/\\]([^/\\]+)$")
        if folder and fname then
            local bname = fname:match("^(.*)%.[^%.]+$") or fname
            local clean = bname:gsub("_blurred", ""):gsub("_Subbed", "")
            local candidate = folder .. "\\" .. clean .. "_dubbing.wav"
            if file_exists(candidate) then
                default_dub = candidate
            end
        end
    end

    local dub_items = {
        "⭐ Thuyết minh chuẩn (Hạ tiếng gốc 20% + Giọng AI 100% - Chuẩn Review)",
        " Thay thế hoàn toàn tiếng gốc bằng giọng AI",
        " Không lồng tiếng (Chỉ giữ âm thanh gốc của video)"
    }
    local dub_default = (default_dub ~= "") and dub_items[1] or dub_items[3]

    local dialog_config = {
        {class = "label", label = "Đường dẫn Video nguồn:", x = 0, y = 0, width = 3, height = 1},
        {class = "edit", name = "video_path", text = default_video, x = 0, y = 1, width = 3, height = 1},

        {class = "label", label = "Chất lượng xuất video:", x = 0, y = 2, width = 1, height = 1},
        {class = "dropdown", name = "quality", items = {"⭐ Siêu Nét 1080p Full HD (Khuyên dùng - Nâng cấp độ nét, chữ sắc lẹm)", "💎 Giữ nguyên độ phân giải gốc (Chất lượng cao)", "⚡ Xuất nhanh (Preset Fast)"}, value = "⭐ Siêu Nét 1080p Full HD (Khuyên dùng - Nâng cấp độ nét, chữ sắc lẹm)", x = 1, y = 2, width = 2, height = 1},

        {class = "label", label = "Chế độ âm thanh thuyết minh AI:", x = 0, y = 3, width = 1, height = 1},
        {class = "dropdown", name = "dub_mode", items = dub_items, value = dub_default, x = 1, y = 3, width = 2, height = 1},

        {class = "label", label = "File âm thanh thuyết minh (.wav):", x = 0, y = 4, width = 3, height = 1},
        {class = "edit", name = "dub_audio", text = default_dub, x = 0, y = 5, width = 3, height = 1},

        {class = "checkbox", name = "blur_logo", label = "Làm mờ Logo Bilibili / Watermark (góc trái trên)", value = true, x = 0, y = 6, width = 3, height = 1},
        {class = "checkbox", name = "open_folder", label = "Tự động mở thư mục chứa video sau khi xuất xong", value = true, x = 0, y = 7, width = 3, height = 1},
    }

    local btn, res = aegisub.dialog.display(dialog_config, {" Bắt đầu xuất MP4", "Hủy"})
    if btn ~= " Bắt đầu xuất MP4" then return end

    local video = res.video_path
    if not video or video == "" or video == "D:\\Downloads" then
        aegisub.dialog.display({{class = "label", label = "Vui lòng nhập đường dẫn file video hợp lệ!", x = 0, y = 0, width = 2, height = 1}})
        return
    end

    local quality_code = "1080p"
    if res.quality:match("Giữ nguyên") then
        quality_code = "original_hq"
    elseif res.quality:match("Xuất nhanh") then
        quality_code = "fast"
    end

    local dub_mode_code = "none"
    if res.dub_mode:match("Thuyết minh chuẩn") then
        dub_mode_code = "ducking"
    elseif res.dub_mode:match("Thay thế") then
        dub_mode_code = "replace"
    end

    -- Ghi phụ đề hiện tại ra file ASS tạm thời
    local temp_ass = SCRIPT_DIR .. "\\temp_render.ass"
    if not export_subs_to_ass_file(subs, temp_ass) then
        aegisub.dialog.display({{class = "label", label = "Lỗi: Không thể ghi file phụ đề tạm thời.", x = 0, y = 0, width = 2, height = 1}})
        return
    end

    local config_json = SCRIPT_DIR .. "\\task_export.json"
    write_json_config(config_json, {
        task = "export",
        video = video,
        sub = temp_ass,
        quality = quality_code,
        blur_logo = res.blur_logo,
        open_folder = res.open_folder,
        dub_audio = (dub_mode_code ~= "none") and res.dub_audio or "",
        dub_mode = dub_mode_code
    })

    local cmd = string.format('start "AI SUBTITLE STUDIO - XUẤT VIDEO MP4" /wait cmd /c ""%s" "%s" run-config --config "%s" || pause"',
        PYTHON_EXE, PIPELINE_PY, config_json)

    os.execute(cmd)

    aegisub.dialog.display({
        {class = "label", label = " Quá trình xuất video đã hoàn thành!\nFile video mới đã được ghép phụ đề sắc nét, lồng tiếng và làm mờ logo.", x = 0, y = 0, width = 3, height = 2}
    })
end

-- =============================================================================
-- 5. ĐỊNH DẠNG KIỂU PHỤ ĐỀ CHUẨN (HỘP ĐEN)
-- =============================================================================
local function macro_ai_apply_style(subs, sel)
    ensure_opaque_box_style(subs)

    for i = 1, #subs do
        local line = subs[i]
        if line.class == "dialogue" then
            line.style = "Default"
            subs[i] = line
        end
    end

    aegisub.set_undo_point("Áp dụng phong cách Hộp Đen chuẩn")

    aegisub.dialog.display({
        {class = "label", label = " Đã áp dụng Hộp Đen (Segoe UI 24pt) và Margin 55 cho toàn bộ phụ đề!\nPhụ đề tiếng Trung gốc đã được che kín đẹp mắt và sắc nét.", x = 0, y = 0, width = 3, height = 2}
    })
end

-- =============================================================================
-- ĐĂNG KÝ CÁC TÍNH NĂNG VÀO MENU AUTOMATION CỦA AEGISUB
-- =============================================================================
aegisub.register_macro("AI Studio/1. 🚀 Kết Hợp Siêu Cấp: Âm Thanh (Whisper) + Quét Chữ (OCR) & Dịch Gemini", "Tối thượng: Chữ chuẩn 100% kịch bản từ OCR + Timeline khớp miligiây từ âm thanh Whisper", macro_ai_hybrid)
aegisub.register_macro("AI Studio/2. 🎯 Chỉ Quét Chữ Trên Video (Video OCR Chuẩn 100% Kịch Bản) & Dịch Gemini", "Quét trực tiếp chữ Hán cứng trên video, chuẩn kịch bản 100% không bị sót thoại bởi nhạc nền", macro_ai_video_ocr)
aegisub.register_macro("AI Studio/3. 🎙️ Chỉ Bóc Giọng Nói (Whisper CUDA) & Dịch AI", "Nhận diện lời thoại qua âm thanh cho video không có chữ trên màn hình", macro_ai_transcribe)
aegisub.register_macro("AI Studio/4. ⚡ Dịch Trực Tiếp File Phụ Đề Có Sẵn (.srt / .ass - Bỏ Qua Bóc Tách)", "Dịch file SRT/ASS có sẵn sang tiếng Việt, tiết kiệm thời gian và tài nguyên", macro_ai_translate_file)
aegisub.register_macro("AI Studio/5. 🔄 Dịch Lại Phụ Đề Hiện Có (Gemini / DeepSeek)", "Dịch lại toàn bộ phụ đề hiện có với ngữ cảnh và xưng hô tự nhiên", macro_ai_retranslate)
aegisub.register_macro("AI Studio/6. 🎙️ Tạo Thuyết Minh AI (VieNeu-TTS)", "Tạo giọng đọc thuyết minh tiếng Việt tự động hoặc sao chép giọng mẫu", macro_ai_tts)
aegisub.register_macro("AI Studio/7. 🎬 Xuất Video MP4 (Hardsub + Thuyết Minh + Xóa Logo)", "Ghép phụ đề, lồng tiếng và làm mờ logo vào video MP4", macro_ai_export)
aegisub.register_macro("AI Studio/8. 🎨 Định Dạng Kiểu Phụ Đề Chuẩn (Hộp Đen Che Chữ Gốc)", "Áp dụng hộp đen và vị trí chuẩn che phụ đề cứng tiếng Trung", macro_ai_apply_style)
