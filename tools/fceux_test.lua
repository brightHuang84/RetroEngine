-- fceux headless test. env RETRO_GAME=breakout|platformer, RETRO_SHOTS=<prefix>
local game = os.getenv("RETRO_GAME") or "breakout"
local pre = os.getenv("RETRO_SHOTS") or "/tmp/nes"
local function run(n, pad) for i = 1, n do joypad.set(1, pad or {}) emu.frameadvance() end end
run(60)
gui.savescreenshotas(pre .. "_a.png"); run(2)
run(10, {start = true}); run(30)
if game == "breakout" then
  for i = 1, 700 do                      -- follow ball (sprite 0 x at $0203, paddle sprite 1 x at $0207)
    local bx, px = memory.readbyte(0x0203), memory.readbyte(0x0207)
    local p = {}
    if px + 16 < bx then p.right = true elseif px + 12 > bx then p.left = true end
    if i % 32 == 0 then p.A = true end
    joypad.set(1, p); emu.frameadvance()
  end
else
  run(40, {right = true}); run(15, {right = true, A = true})
  for i = 1, 160 do joypad.set(1, {right = true, A = (math.floor(i / 16) % 4 == 0)}) emu.frameadvance() end
end
gui.savescreenshotas(pre .. "_b.png"); run(2)
emu.exit()
