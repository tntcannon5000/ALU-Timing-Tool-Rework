--[[
  ALU File Bridge  (paste into CE Lua Engine and hit Execute)
  ============================================================
  Writes game telemetry to a small temp file every ~10ms.
  Python reads the same file to get real-time values.

  Format:  timer|progress|rpm|gear|rpmRaw|checkpoint|visualTimer
  Fields:
    timer       — RaceTimer (int, microseconds)
    progress    — RaceProgress (float, 0.0–1.0)
    rpm         — RaceRPM_Int (int)
    gear        — RaceGear (int)
    rpmRaw      — RaceRPM_Raw (float)
    checkpoint  — Checkpoint pointer → dereference → int
    visualTimer — VisualTimer (int, raw ESI value)

  NO external libraries needed — uses only CE built-in io + os.

  Requires: All AA scripts enabled in the cheat table
            (Timer/Progress, Gearbox Info, CP Finder, Visual Timer)

  A status window pops up so you can see what's happening.
  Close the window or call ALU_stop() to shut down.
]]

-- ============================================================
-- Configuration
-- ============================================================
local ALU_SEND_INTERVAL = 1    -- ms  (CE timer min; effective ~5-15ms on Windows)

-- Shared file path:  %TEMP%\alu_ce_bridge.dat
local ALU_DATA_PATH = os.getenv("TEMP") .. "\\alu_ce_bridge.dat"

-- ============================================================
-- Globals (so ALU_stop can reach them)
-- ============================================================
ALU_pollTimer  = nil
ALU_statusForm = nil
ALU_statusLbl  = nil
ALU_writeCount = 0

-- ============================================================
-- Status window
-- ============================================================
ALU_statusForm = createForm(false)
ALU_statusForm.Caption     = "ALU File Bridge"
ALU_statusForm.Width       = 340
ALU_statusForm.Height      = 110
ALU_statusForm.Position    = "poScreenCenter"
ALU_statusForm.BorderStyle = "bsSingle"

ALU_statusLbl = createLabel(ALU_statusForm)
ALU_statusLbl.Caption  = "Starting..."
ALU_statusLbl.Left     = 12
ALU_statusLbl.Top      = 12
ALU_statusLbl.AutoSize = true

local pathLbl = createLabel(ALU_statusForm)
pathLbl.Caption  = "File: " .. ALU_DATA_PATH
pathLbl.Left     = 12
pathLbl.Top      = 36
pathLbl.AutoSize = true

-- ============================================================
-- Stop function  (call ALU_stop() from Lua Engine to shut down)
-- ============================================================
function ALU_stop()
  if ALU_pollTimer then
    ALU_pollTimer.Enabled = false
    ALU_pollTimer.destroy()
    ALU_pollTimer = nil
  end
  -- Clean up the data file
  pcall(os.remove, ALU_DATA_PATH)
  if ALU_statusForm then
    ALU_statusForm.destroy()
    ALU_statusForm = nil
    ALU_statusLbl  = nil
  end
  print("[ALU Bridge] Stopped")
end

-- Stop button
local stopBtn = createButton(ALU_statusForm)
stopBtn.Caption = "Stop"
stopBtn.Left    = 12
stopBtn.Top     = 64
stopBtn.Width   = 80
stopBtn.OnClick = ALU_stop

ALU_statusForm.OnClose = function()
  ALU_stop()
  return caFree
end

ALU_statusForm.Show()

-- ============================================================
-- Read game values
-- ============================================================
function ALU_readGameValues()
  local timerVal    = 0
  local progressVal = 0.0
  local rpmVal      = 0
  local gearVal     = 0
  local rpmRawVal   = 0.0
  local cpVal       = 0
  local vtVal       = 0

  -- RaceTimer (int, microseconds)
  local a1 = getAddressSafe("RaceTimer")
  if a1 and a1 ~= 0 then timerVal = readInteger(a1) or 0 end

  -- RaceProgress (float, 0.0–1.0)
  local a2 = getAddressSafe("RaceProgress")
  if a2 and a2 ~= 0 then progressVal = readFloat(a2) or 0.0 end

  -- RaceRPM_Int (int)
  local a3 = getAddressSafe("RaceRPM_Int")
  if a3 and a3 ~= 0 then rpmVal = readInteger(a3) or 0 end

  -- RaceGear (int)
  local a4 = getAddressSafe("RaceGear")
  if a4 and a4 ~= 0 then gearVal = readInteger(a4) or 0 end

  -- RaceRPM_Raw (float)
  local a5 = getAddressSafe("RaceRPM_Raw")
  if a5 and a5 ~= 0 then rpmRawVal = readFloat(a5) or 0.0 end

  -- Checkpoint (pointer → dereference to get int value)
  local a6 = getAddressSafe("Checkpoint")
  if a6 and a6 ~= 0 then
    local ptr = readQword(a6)
    if ptr and ptr ~= 0 then cpVal = readInteger(ptr) or 0 end
  end

  -- VisualTimer (int)
  local a7 = getAddressSafe("VisualTimer")
  if a7 and a7 ~= 0 then vtVal = readInteger(a7) or 0 end

  return timerVal, progressVal, rpmVal, gearVal, rpmRawVal, cpVal, vtVal
end

-- ============================================================
-- Write values to file (called by timer)
-- ============================================================
function ALU_writeToFile()
  local t, p, rpm, gear, rpmRaw, cp, vt = ALU_readGameValues()

  -- Format: timer|progress|rpm|gear|rpmRaw|checkpoint|visualTimer
  local payload = string.format("%d|%.6f|%d|%d|%.6f|%d|%d", t, p, rpm, gear, rpmRaw, cp, vt)

  -- Write directly to data file.  No remove+rename dance — on Windows
  -- the atomic rename pattern causes file-locking deadlocks when the
  -- Python reader holds a read handle at the instant we try to delete.
  -- A direct overwrite is safe: worst case Python sees a partial line,
  -- which _parse_line already handles gracefully.
  local f = io.open(ALU_DATA_PATH, "w")
  if f then
    f:write(payload)
    f:close()

    ALU_writeCount = ALU_writeCount + 1
    -- Update status label every ~1 second
    if ALU_writeCount % 100 == 0 and ALU_statusLbl then
      ALU_statusLbl.Caption = string.format(
        "Running | T=%d  P=%.1f%%  CP=%d  (#%d)",
        t, p * 100, cp, ALU_writeCount)
    end
  end
end

-- ============================================================
-- Start the poll timer
-- ============================================================
ALU_pollTimer = createTimer(nil, false)
ALU_pollTimer.Interval = ALU_SEND_INTERVAL
ALU_pollTimer.OnTimer  = ALU_writeToFile
ALU_pollTimer.Enabled  = true

if ALU_statusLbl then ALU_statusLbl.Caption = "Running — waiting for values..." end
print("[ALU Bridge] Writing to: " .. ALU_DATA_PATH)
print(string.format("[ALU Bridge] Interval: %dms", ALU_SEND_INTERVAL))
