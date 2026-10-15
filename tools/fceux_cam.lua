-- Headless camera shot. Reads the PPU with getscreenpixel (fceux's PNG
-- grab is a blank window under offscreen Qt).
-- RETRO_LEVEL, RETRO_CAM, RETRO_SHOTS, RETRO_ADDR_LEVEL, RETRO_ADDR_CAM.
local level = tonumber(os.getenv("RETRO_LEVEL")) or 2
local cam = tonumber(os.getenv("RETRO_CAM")) or 0
local out = os.getenv("RETRO_SHOTS") or "/tmp/nes_cam.ppm"
local addr_l = tonumber(os.getenv("RETRO_ADDR_LEVEL")) or 0x400
local addr_c = tonumber(os.getenv("RETRO_ADDR_CAM")) or 0x401
emu.speedmode("maximum")
local function run(n, pad)
  for i = 1, n do
    joypad.set(1, pad or {})
    emu.frameadvance()
  end
end
local function mask() return memory.readbyte(0x2001) end
local function tile0() return memory.readbyte(0x0201) end
-- Title upload blanks the picture. Wait until rendering is on.
local i = 0
while i < 120 and mask() ~= 0x1E do
  run(1)
  i = i + 1
end
run(4)
memory.writebyte(addr_l, level)
memory.writebyte(addr_c, cam % 256)
memory.writebyte(addr_c + 1, math.floor(cam / 256) % 256)
run(4)
run(10, {start = true})
-- play_init loads the level with the screen off, then the player sprite is tile 0xA0.
i = 0
while i < 120 do
  run(1)
  i = i + 1
  if mask() == 0x1E and tile0() == 0xA0 then break end
end
run(8)
local f = io.open(out, "wb")
f:write("P6\n256 224\n255\n")
for y = 0, 223 do
  for x = 0, 255 do
    local r, g, b = emu.getscreenpixel(x, y)
    f:write(string.char(r or 0, g or 0, b or 0))
  end
end
f:close()
emu.exit()
