@ GBA ROM entry. Header bytes 0x04..0x9F stay zero: tools/gbafix.py fills the
@ title and complement, not the Nintendo logo. mGBA's built-in BIOS boots this.
@ A devkitARM gbafix on PATH can overwrite the logo for real hardware.
.syntax unified
.cpu arm7tdmi
.arch armv4t
.section .text.startup, "ax", %progbits
.arm
.global _start
_start:
    b _entry
    .space 0xBC, 0

_entry:
    mov r0, #0xD2              @ IRQ mode, IRQs masked
    msr cpsr_c, r0
    ldr sp, =0x03007FA0
    mov r0, #0x1F              @ System mode, IRQs unmasked
    msr cpsr_c, r0
    ldr sp, =0x03007000

    ldr r0, =__data_lma
    ldr r1, =__data_start
    ldr r2, =__data_end
1:
    cmp r1, r2
    bcs 2f
    ldr r3, [r0], #4
    str r3, [r1], #4
    b 1b
2:
    mov r3, #0
    ldr r1, =__bss_start
    ldr r2, =__bss_end
3:
    cmp r1, r2
    bcs 4f
    str r3, [r1], #4
    b 3b
4:
    ldr r0, =gba_irq
    ldr r1, =0x03007FFC        @ BIOS user IRQ vector
    str r0, [r1]
    ldr r1, =0x04000208        @ IME off until the renderer asks for HBlank
    mov r0, #0
    strh r0, [r1]
    bl main
hang:
    b hang

@ HBlank is short (~272 cycles), so the split stays in assembly.
@ Line 15: switch BG0 from the HUD strip to the playfield.
@ Line 159: back to the HUD, ready for the next frame's line 0.
.global gba_irq
gba_irq:
    ldr r0, =0x04000000
    ldrh r1, [r0, #6]          @ VCOUNT
    cmp r1, #15
    beq 1f
    cmp r1, #159
    bne 2f
    mov r3, #0
    b 3f
1:
    ldr r2, =gba_vofs_play
    ldrh r3, [r2]
3:
    strh r3, [r0, #0x12]       @ BG0VOFS
2:
    ldr r2, =0x04000202        @ IF, acknowledge HBlank
    mov r1, #2
    strh r1, [r2]
    bx lr
.ltorg
