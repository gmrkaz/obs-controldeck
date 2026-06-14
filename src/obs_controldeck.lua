-- OBS ControlDeck
-- Creator-focused toolkit for OBS Studio.
-- Version: 1.0.0

obs = obslua

local VERSION = "1.0.0"
local SOUND_SLOTS = 8

local output_dir = ""
local marker_note = ""
local marker_type = "Highlight"
local mic_source_name = ""
local desktop_audio_source_name = ""
local camera_source_name = ""
local panic_scene_name = ""
local intro_scene_name = ""
local main_scene_name = ""
local export_config_path = ""
local import_config_path = ""
local enable_recording_guard = true
local enable_auto_intro = false
local auto_intro_seconds = 5

local recording_started_at = nil
local current_scene_name = ""
local current_scene_entered_at = os.time()
local scene_totals = {}
local markers = {}
local session_saved = false

local sounds = {}
for i = 1, SOUND_SLOTS do
  sounds[i] = { title = "Sound " .. tostring(i), file = "", volume = 80 }
end

local hotkey_ids = {
  add_marker = obs.OBS_INVALID_HOTKEY_ID,
  reaction_marker = obs.OBS_INVALID_HOTKEY_ID,
  panic = obs.OBS_INVALID_HOTKEY_ID
}
for i = 1, SOUND_SLOTS do
  hotkey_ids["sound" .. tostring(i)] = obs.OBS_INVALID_HOTKEY_ID
end

local function log_info(message)
  obs.script_log(obs.LOG_INFO, "[OBS ControlDeck] " .. tostring(message))
end

local function log_warn(message)
  obs.script_log(obs.LOG_WARNING, "[OBS ControlDeck] " .. tostring(message))
end

local function is_blank(value)
  return value == nil or value == ""
end

local function clamp(value, min_value, max_value)
  value = tonumber(value) or min_value
  if value < min_value then return min_value end
  if value > max_value then return max_value end
  return value
end

local function pad2(value)
  value = tonumber(value) or 0
  if value < 10 then return "0" .. tostring(value) end
  return tostring(value)
end

local function seconds_to_time(total)
  total = math.max(0, tonumber(total) or 0)
  local h = math.floor(total / 3600)
  local m = math.floor((total % 3600) / 60)
  local s = math.floor(total % 60)
  return pad2(h) .. ":" .. pad2(m) .. ":" .. pad2(s)
end

local function get_session_seconds()
  if recording_started_at == nil then return 0 end
  return os.time() - recording_started_at
end

local function path_join(a, b)
  if is_blank(a) then return b end
  local sep = package.config:sub(1, 1)
  if a:sub(-1) == "/" or a:sub(-1) == "\\" then
    return a .. b
  end
  return a .. sep .. b
end

local function session_prefix()
  return os.date("%Y-%m-%d_%H-%M-%S")
end

local function escape_json(value)
  value = tostring(value or "")
  value = value:gsub('\\', '\\\\')
  value = value:gsub('"', '\\"')
  value = value:gsub('\n', '\\n')
  value = value:gsub('\r', '\\r')
  value = value:gsub('\t', '\\t')
  return value
end

local function write_file(path, content)
  if is_blank(path) then return false end
  local file = io.open(path, "w")
  if file == nil then
    log_warn("Could not write file: " .. path)
    return false
  end
  file:write(content)
  file:close()
  return true
end

local function read_file(path)
  if is_blank(path) then return nil end
  local file = io.open(path, "r")
  if file == nil then return nil end
  local content = file:read("*a")
  file:close()
  return content
end

local function get_current_scene_name()
  local source = obs.obs_frontend_get_current_scene()
  if source == nil then return "" end
  local name = obs.obs_source_get_name(source)
  obs.obs_source_release(source)
  return name or ""
end

local function switch_to_scene(scene_name)
  if is_blank(scene_name) then return false end
  local source = obs.obs_get_source_by_name(scene_name)
  if source == nil then
    log_warn("Scene not found: " .. scene_name)
    return false
  end
  obs.obs_frontend_set_current_scene(source)
  obs.obs_source_release(source)
  return true
end

local function set_source_muted(source_name, muted)
  if is_blank(source_name) then return false end
  local source = obs.obs_get_source_by_name(source_name)
  if source == nil then
    log_warn("Audio source not found: " .. source_name)
    return false
  end
  obs.obs_source_set_muted(source, muted)
  obs.obs_source_release(source)
  return true
end

local function hide_source_in_current_scene(source_name)
  if is_blank(source_name) then return false end
  local scene_source = obs.obs_frontend_get_current_scene()
  if scene_source == nil then return false end
  local scene = obs.obs_scene_from_source(scene_source)
  if scene == nil then
    obs.obs_source_release(scene_source)
    return false
  end
  local item = obs.obs_scene_find_source(scene, source_name)
  if item ~= nil then
    obs.obs_sceneitem_set_visible(item, false)
    obs.obs_source_release(scene_source)
    return true
  end
  obs.obs_source_release(scene_source)
  log_warn("Source not found in current scene: " .. source_name)
  return false
end

local function update_scene_timer()
  local now = os.time()
  if not is_blank(current_scene_name) then
    local delta = math.max(0, now - current_scene_entered_at)
    scene_totals[current_scene_name] = (scene_totals[current_scene_name] or 0) + delta
  end
  current_scene_name = get_current_scene_name()
  current_scene_entered_at = now
end

local function add_marker(note, kind)
  local marker = {
    time = seconds_to_time(get_session_seconds()),
    seconds = get_session_seconds(),
    type = kind or marker_type or "Highlight",
    note = note or marker_note or "",
    scene = get_current_scene_name(),
    created_at = os.date("%Y-%m-%d %H:%M:%S")
  }
  table.insert(markers, marker)
  log_info("Marker added: " .. marker.time .. " [" .. marker.type .. "] " .. marker.note)
end

local function build_markers_txt()
  local lines = {}
  table.insert(lines, "OBS ControlDeck Markers")
  table.insert(lines, "Version: " .. VERSION)
  table.insert(lines, "Generated: " .. os.date("%Y-%m-%d %H:%M:%S"))
  table.insert(lines, "")
  if #markers == 0 then
    table.insert(lines, "No markers were created in this session.")
  else
    for _, m in ipairs(markers) do
      table.insert(lines, m.time .. " - " .. m.type .. " - " .. m.scene .. " - " .. m.note)
    end
  end
  table.insert(lines, "")
  table.insert(lines, "Scene totals:")
  for scene, seconds in pairs(scene_totals) do
    table.insert(lines, "- " .. scene .. ": " .. seconds_to_time(seconds))
  end
  return table.concat(lines, "\n") .. "\n"
end

local function build_markers_json()
  local chunks = {}
  table.insert(chunks, "{\n")
  table.insert(chunks, "  \"version\": \"" .. VERSION .. "\",\n")
  table.insert(chunks, "  \"generatedAt\": \"" .. escape_json(os.date("%Y-%m-%d %H:%M:%S")) .. "\",\n")
  table.insert(chunks, "  \"markers\": [\n")
  for i, m in ipairs(markers) do
    table.insert(chunks, "    {\n")
    table.insert(chunks, "      \"time\": \"" .. escape_json(m.time) .. "\",\n")
    table.insert(chunks, "      \"seconds\": " .. tostring(m.seconds) .. ",\n")
    table.insert(chunks, "      \"type\": \"" .. escape_json(m.type) .. "\",\n")
    table.insert(chunks, "      \"scene\": \"" .. escape_json(m.scene) .. "\",\n")
    table.insert(chunks, "      \"note\": \"" .. escape_json(m.note) .. "\",\n")
    table.insert(chunks, "      \"createdAt\": \"" .. escape_json(m.created_at) .. "\"\n")
    table.insert(chunks, "    }")
    if i < #markers then table.insert(chunks, ",") end
    table.insert(chunks, "\n")
  end
  table.insert(chunks, "  ],\n")
  table.insert(chunks, "  \"sceneTotals\": {\n")
  local first = true
  for scene, seconds in pairs(scene_totals) do
    if not first then table.insert(chunks, ",\n") end
    table.insert(chunks, "    \"" .. escape_json(scene) .. "\": " .. tostring(seconds))
    first = false
  end
  table.insert(chunks, "\n  }\n")
  table.insert(chunks, "}\n")
  return table.concat(chunks, "")
end

local function save_session_files()
  if session_saved then return end
  if is_blank(output_dir) then
    log_warn("Output directory is empty. Session files were not saved.")
    return
  end
  update_scene_timer()
  local prefix = session_prefix()
  local txt_path = path_join(output_dir, prefix .. "-markers.txt")
  local json_path = path_join(output_dir, prefix .. "-markers.json")
  local txt_ok = write_file(txt_path, build_markers_txt())
  local json_ok = write_file(json_path, build_markers_json())
  if txt_ok or json_ok then
    session_saved = true
    log_info("Session files saved to: " .. output_dir)
  end
end

local function recording_guard_check()
  if not enable_recording_guard then return true end
  local ok = true
  if is_blank(output_dir) then
    log_warn("Recording Guard: output folder is not configured.")
    ok = false
  end
  if not is_blank(mic_source_name) then
    local mic = obs.obs_get_source_by_name(mic_source_name)
    if mic == nil then
      log_warn("Recording Guard: mic source not found: " .. mic_source_name)
      ok = false
    else
      if obs.obs_source_muted(mic) then
        log_warn("Recording Guard: mic source is muted: " .. mic_source_name)
        ok = false
      end
      obs.obs_source_release(mic)
    end
  end
  if not is_blank(desktop_audio_source_name) then
    local desktop = obs.obs_get_source_by_name(desktop_audio_source_name)
    if desktop == nil then
      log_warn("Recording Guard: desktop audio source not found: " .. desktop_audio_source_name)
      ok = false
    else
      if obs.obs_source_muted(desktop) then
        log_warn("Recording Guard: desktop audio source is muted: " .. desktop_audio_source_name)
        ok = false
      end
      obs.obs_source_release(desktop)
    end
  end
  if is_blank(get_current_scene_name()) then
    log_warn("Recording Guard: no current scene detected.")
    ok = false
  end
  if ok then log_info("Recording Guard: checks passed.") end
  return ok
end

local function sound_source_name(slot)
  local sound = sounds[slot]
  if sound == nil then return "ControlDeck Sound " .. tostring(slot) end
  return "ControlDeck Sound " .. tostring(slot) .. " - " .. tostring(sound.title or "Untitled")
end

local function ensure_sound_source(slot)
  local sound = sounds[slot]
  if sound == nil or is_blank(sound.file) then
    log_warn("Sound slot " .. tostring(slot) .. " has no file configured.")
    return nil
  end
  local source_name = sound_source_name(slot)
  local source = obs.obs_get_source_by_name(source_name)
  if source ~= nil then return source end

  local data = obs.obs_data_create()
  obs.obs_data_set_string(data, "local_file", sound.file)
  obs.obs_data_set_bool(data, "is_local_file", true)
  obs.obs_data_set_bool(data, "looping", false)
  obs.obs_data_set_bool(data, "close_when_inactive", false)
  source = obs.obs_source_create("ffmpeg_source", source_name, data, nil)
  obs.obs_data_release(data)

  if source == nil then
    log_warn("Could not create media source for sound slot " .. tostring(slot))
    return nil
  end

  local scene_source = obs.obs_frontend_get_current_scene()
  if scene_source ~= nil then
    local scene = obs.obs_scene_from_source(scene_source)
    if scene ~= nil then
      local item = obs.obs_scene_add(scene, source)
      if item ~= nil then obs.obs_sceneitem_set_visible(item, false) end
    end
    obs.obs_source_release(scene_source)
  end

  return source
end

local function play_sound(slot)
  local source = ensure_sound_source(slot)
  if source == nil then return end
  local volume = clamp(sounds[slot].volume, 0, 100)
  obs.obs_source_set_volume(source, volume / 100.0)
  if obs.obs_source_media_restart ~= nil then obs.obs_source_media_restart(source) end
  if obs.obs_source_media_play_pause ~= nil then obs.obs_source_media_play_pause(source, false) end
  log_info("Playing sound slot " .. tostring(slot) .. ": " .. tostring(sounds[slot].title))
  obs.obs_source_release(source)
end

local function stop_sound(slot)
  local source = obs.obs_get_source_by_name(sound_source_name(slot))
  if source ~= nil then
    if obs.obs_source_media_stop ~= nil then obs.obs_source_media_stop(source) end
    obs.obs_source_release(source)
  end
end

local function stop_all_sounds()
  for i = 1, SOUND_SLOTS do stop_sound(i) end
end

local function panic_action()
  add_marker("Panic Button pressed", "Panic")
  if not is_blank(mic_source_name) then set_source_muted(mic_source_name, true) end
  if not is_blank(camera_source_name) then hide_source_in_current_scene(camera_source_name) end
  stop_all_sounds()
  if not is_blank(panic_scene_name) then switch_to_scene(panic_scene_name) end
  log_warn("Panic Button executed.")
end

local function export_config()
  if is_blank(export_config_path) then
    log_warn("Export config path is empty.")
    return
  end
  local json = {}
  table.insert(json, "{\n")
  table.insert(json, "  \"profileName\": \"OBS ControlDeck Export\",\n")
  table.insert(json, "  \"version\": \"" .. VERSION .. "\",\n")
  table.insert(json, "  \"sources\": {\n")
  table.insert(json, "    \"mic\": \"" .. escape_json(mic_source_name) .. "\",\n")
  table.insert(json, "    \"desktopAudio\": \"" .. escape_json(desktop_audio_source_name) .. "\",\n")
  table.insert(json, "    \"camera\": \"" .. escape_json(camera_source_name) .. "\"\n")
  table.insert(json, "  },\n")
  table.insert(json, "  \"scenes\": {\n")
  table.insert(json, "    \"panic\": \"" .. escape_json(panic_scene_name) .. "\",\n")
  table.insert(json, "    \"intro\": \"" .. escape_json(intro_scene_name) .. "\",\n")
  table.insert(json, "    \"main\": \"" .. escape_json(main_scene_name) .. "\"\n")
  table.insert(json, "  },\n")
  table.insert(json, "  \"recordingGuard\": { \"enabled\": " .. tostring(enable_recording_guard) .. " },\n")
  table.insert(json, "  \"autoIntro\": { \"enabled\": " .. tostring(enable_auto_intro) .. ", \"delaySeconds\": " .. tostring(auto_intro_seconds) .. " },\n")
  table.insert(json, "  \"soundpad\": [\n")
  for i, s in ipairs(sounds) do
    table.insert(json, "    { \"title\": \"" .. escape_json(s.title) .. "\", \"file\": \"" .. escape_json(s.file) .. "\", \"volume\": " .. tostring(clamp(s.volume, 0, 100)) .. " }")
    if i < #sounds then table.insert(json, ",") end
    table.insert(json, "\n")
  end
  table.insert(json, "  ]\n")
  table.insert(json, "}\n")
  if write_file(export_config_path, table.concat(json, "")) then
    log_info("Config exported to: " .. export_config_path)
  end
end

local function import_config_preview()
  if is_blank(import_config_path) then
    log_warn("Import config path is empty.")
    return
  end
  local content = read_file(import_config_path)
  if content == nil then
    log_warn("Could not read config: " .. import_config_path)
    return
  end
  log_info("Config preview loaded. v1.0.0 does not silently apply third-party configs.")
  log_info("Preview first 1000 characters:\n" .. content:sub(1, 1000))
end

function control_deck_auto_intro_finish()
  if not is_blank(main_scene_name) then
    switch_to_scene(main_scene_name)
    add_marker("AutoIntro switched to main scene", "AutoIntro")
  end
  obs.timer_remove(control_deck_auto_intro_finish)
end

local function auto_intro_start()
  if not enable_auto_intro then return end
  if is_blank(intro_scene_name) or is_blank(main_scene_name) then return end
  switch_to_scene(intro_scene_name)
  add_marker("AutoIntro started", "AutoIntro")
  obs.timer_remove(control_deck_auto_intro_finish)
  obs.timer_add(control_deck_auto_intro_finish, clamp(auto_intro_seconds, 1, 60) * 1000)
end

local function on_event(event)
  if event == obs.OBS_FRONTEND_EVENT_RECORDING_STARTED then
    markers = {}
    scene_totals = {}
    session_saved = false
    recording_started_at = os.time()
    current_scene_name = get_current_scene_name()
    current_scene_entered_at = os.time()
    recording_guard_check()
    add_marker("Recording started", "Start")
    auto_intro_start()
  elseif event == obs.OBS_FRONTEND_EVENT_RECORDING_STOPPED then
    add_marker("Recording stopped", "Stop")
    save_session_files()
    recording_started_at = nil
  elseif event == obs.OBS_FRONTEND_EVENT_SCENE_CHANGED then
    update_scene_timer()
  end
end

local function hotkey_marker(pressed)
  if pressed then add_marker(marker_note, marker_type) end
end

local function hotkey_reaction_marker(pressed)
  if pressed then add_marker("Reaction moment", "Reaction") end
end

local function hotkey_panic(pressed)
  if pressed then panic_action() end
end

local function hotkey_sound(slot)
  return function(pressed)
    if pressed then play_sound(slot) end
  end
end

function script_description()
  return "OBS ControlDeck " .. VERSION .. "\n\n" ..
         "Release-ready toolkit: markers, clip notes, scene timer, panic button, recording guard, soundpad, and safe config presets."
end

function script_properties()
  local props = obs.obs_properties_create()

  obs.obs_properties_add_path(props, "output_dir", "Output folder for notes", obs.OBS_PATH_DIRECTORY, nil, nil)
  obs.obs_properties_add_text(props, "marker_note", "Default marker note", obs.OBS_TEXT_DEFAULT)

  local type_list = obs.obs_properties_add_list(props, "marker_type", "Default marker type", obs.OBS_COMBO_TYPE_LIST, obs.OBS_COMBO_FORMAT_STRING)
  for _, value in ipairs({"Highlight", "Funny", "Mistake", "Audio", "Panic", "Reaction", "Custom"}) do
    obs.obs_property_list_add_string(type_list, value, value)
  end

  obs.obs_properties_add_bool(props, "enable_recording_guard", "Enable Recording Guard")
  obs.obs_properties_add_text(props, "mic_source_name", "Microphone source name", obs.OBS_TEXT_DEFAULT)
  obs.obs_properties_add_text(props, "desktop_audio_source_name", "Desktop audio source name", obs.OBS_TEXT_DEFAULT)
  obs.obs_properties_add_text(props, "camera_source_name", "Camera source name", obs.OBS_TEXT_DEFAULT)
  obs.obs_properties_add_text(props, "panic_scene_name", "Panic/safe scene name", obs.OBS_TEXT_DEFAULT)

  obs.obs_properties_add_bool(props, "enable_auto_intro", "Enable AutoIntro")
  obs.obs_properties_add_text(props, "intro_scene_name", "Intro scene name", obs.OBS_TEXT_DEFAULT)
  obs.obs_properties_add_text(props, "main_scene_name", "Main scene name", obs.OBS_TEXT_DEFAULT)
  obs.obs_properties_add_int(props, "auto_intro_seconds", "AutoIntro seconds", 1, 60, 1)

  for i = 1, SOUND_SLOTS do
    obs.obs_properties_add_text(props, "sound" .. i .. "_title", "Sound " .. i .. " title", obs.OBS_TEXT_DEFAULT)
    obs.obs_properties_add_path(props, "sound" .. i .. "_file", "Sound " .. i .. " file", obs.OBS_PATH_FILE, "Audio Files (*.mp3 *.wav *.ogg *.flac)", nil)
    obs.obs_properties_add_int(props, "sound" .. i .. "_volume", "Sound " .. i .. " volume", 0, 100, 1)
  end

  obs.obs_properties_add_path(props, "import_config_path", "Import config path", obs.OBS_PATH_FILE, "JSON Files (*.json)", nil)
  obs.obs_properties_add_button(props, "import_config_button", "Preview imported config", function() import_config_preview(); return true end)
  obs.obs_properties_add_path(props, "export_config_path", "Export config path", obs.OBS_PATH_FILE_SAVE, "JSON Files (*.json)", nil)
  obs.obs_properties_add_button(props, "export_config_button", "Export current config", function() export_config(); return true end)

  return props
end

function script_defaults(settings)
  obs.obs_data_set_default_bool(settings, "enable_recording_guard", true)
  obs.obs_data_set_default_bool(settings, "enable_auto_intro", false)
  obs.obs_data_set_default_int(settings, "auto_intro_seconds", 5)
  obs.obs_data_set_default_string(settings, "marker_type", "Highlight")
  for i = 1, SOUND_SLOTS do
    obs.obs_data_set_default_string(settings, "sound" .. i .. "_title", "Sound " .. i)
    obs.obs_data_set_default_int(settings, "sound" .. i .. "_volume", 80)
  end
end

function script_update(settings)
  output_dir = obs.obs_data_get_string(settings, "output_dir")
  marker_note = obs.obs_data_get_string(settings, "marker_note")
  marker_type = obs.obs_data_get_string(settings, "marker_type")
  enable_recording_guard = obs.obs_data_get_bool(settings, "enable_recording_guard")
  mic_source_name = obs.obs_data_get_string(settings, "mic_source_name")
  desktop_audio_source_name = obs.obs_data_get_string(settings, "desktop_audio_source_name")
  camera_source_name = obs.obs_data_get_string(settings, "camera_source_name")
  panic_scene_name = obs.obs_data_get_string(settings, "panic_scene_name")
  enable_auto_intro = obs.obs_data_get_bool(settings, "enable_auto_intro")
  intro_scene_name = obs.obs_data_get_string(settings, "intro_scene_name")
  main_scene_name = obs.obs_data_get_string(settings, "main_scene_name")
  auto_intro_seconds = obs.obs_data_get_int(settings, "auto_intro_seconds")
  import_config_path = obs.obs_data_get_string(settings, "import_config_path")
  export_config_path = obs.obs_data_get_string(settings, "export_config_path")

  for i = 1, SOUND_SLOTS do
    sounds[i].title = obs.obs_data_get_string(settings, "sound" .. i .. "_title")
    sounds[i].file = obs.obs_data_get_string(settings, "sound" .. i .. "_file")
    sounds[i].volume = obs.obs_data_get_int(settings, "sound" .. i .. "_volume")
  end
end

function script_load(settings)
  hotkey_ids.add_marker = obs.obs_hotkey_register_frontend("obs_controldeck.add_marker", "ControlDeck: Add marker", hotkey_marker)
  hotkey_ids.reaction_marker = obs.obs_hotkey_register_frontend("obs_controldeck.reaction_marker", "ControlDeck: Add reaction marker", hotkey_reaction_marker)
  hotkey_ids.panic = obs.obs_hotkey_register_frontend("obs_controldeck.panic", "ControlDeck: Panic Button", hotkey_panic)
  for i = 1, SOUND_SLOTS do
    hotkey_ids["sound" .. tostring(i)] = obs.obs_hotkey_register_frontend("obs_controldeck.sound" .. tostring(i), "ControlDeck: Play Sound " .. tostring(i), hotkey_sound(i))
  end

  for name, id in pairs(hotkey_ids) do
    local saved = obs.obs_data_get_array(settings, "hotkey_" .. name)
    obs.obs_hotkey_load(id, saved)
    obs.obs_data_array_release(saved)
  end

  obs.obs_frontend_add_event_callback(on_event)
  current_scene_name = get_current_scene_name()
  current_scene_entered_at = os.time()
  log_info("Loaded version " .. VERSION)
end

function script_save(settings)
  for name, id in pairs(hotkey_ids) do
    local saved = obs.obs_hotkey_save(id)
    obs.obs_data_set_array(settings, "hotkey_" .. name, saved)
    obs.obs_data_array_release(saved)
  end
end

function script_unload()
  if recording_started_at ~= nil then save_session_files() end
  obs.timer_remove(control_deck_auto_intro_finish)
  obs.obs_frontend_remove_event_callback(on_event)
  log_info("Unloaded")
end
