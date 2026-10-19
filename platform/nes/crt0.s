; retro_engine NES startup.
; NROM-256 (mapper 0) unless MMC5 is defined: then NES 2.0 mapper 5,
; 128KB PRG, 128KB CHR, 64KB WRAM. The reset stub lives in the last 8KB
; because MMC5 powers up with only that bank mapped at $E000.
.export __STARTUP__ : absolute = 1
.export _nmi_count, _vram_buf, _vram_len, _scroll_x, _ppu_ctrl, _split_line, _ex_on
.import _main, copydata, zerobss
.importzp sp

.segment "HEADER"
.ifdef MMC5
    ; NES 2.0: mapper 5, vertical mirror, 8x16KB PRG, 16x8KB CHR, 64KB PRG-RAM
    .byte "NES", $1A, 8, 16, $51, $08, 0, 0, $0A, 0, 0, 0, 0, 0
.else
    .byte "NES", $1A, 2, 1, $01, $00
    .res 8, 0
.endif

.segment "ZEROPAGE"
_nmi_count:  .res 1
_vram_len:   .res 1      ; committed bytes in $0300 buffer (C clears after each vblank)
_scroll_x:   .res 1
_ppu_ctrl:   .res 1      ; bit0 = nametable select (scroll >= 256), bit7 = NMI
_split_line: .res 1      ; MMC5 IRQ scanline, 0 = no split
_ex_on:      .res 1      ; MMC5 ExRAM extended attributes
_vram_buf = $0300

.ifdef MMC5
.segment "RESET"
reset:
    sei
    cld
    ldx #$40
    stx $4017
    ldx #$FF
    txs
    inx
    stx $2000
    stx $2001
    stx $4010
    stx $5204            ; scanline IRQ off
    stx $5015            ; expansion pulses off
    lda #3
    sta $5100            ; PRG mode 3: four 8KB banks
    lda #$80|13
    sta $5115            ; $A000 = bank 13
    lda #$80|14
    sta $5116            ; $C000 = bank 14
    lda #$80|15
    sta $5117            ; $E000 = bank 15 (this stub)
    lda #$80
    sta $5114            ; $8000 = bank 0
    lda #2
    sta $5102            ; allow PRG-RAM writes
    lda #1
    sta $5103
    lda #0
    sta $5113            ; WRAM bank 0 at $6000
    sta $5101            ; CHR mode 0: one 8KB page
    sta $5127            ; CHR page 0 covers $0000-$1FFF
    lda #$44
    sta $5105            ; vertical mirroring (A B A B)
    lda #0
    sta $5104            ; ExRAM off (not extended attributes)
    ldx #0               ; zero all 8 WRAM banks so the window matches a cleared BSS
@wbank:
    stx $5113
    lda #$60
    sta $01
    lda #0
    sta $00
    lda #$20
    sta $02
    lda #0
    ldy #0
@page:
    sta ($00),y
    iny
    bne @page
    inc $01
    dec $02
    bne @page
    inx
    cpx #8
    bne @wbank
    lda #0
    sta $5113
    jmp ramclr
.endif

.segment "STARTUP"
.ifndef MMC5
reset:
.endif
ramclr:
    sei
    cld
    ldx #$40
    stx $4017
    ldx #$FF
    txs
    inx
    stx $2000
    stx $2001
    stx $4010
:   bit $2002
    bpl :-
    lda #0
    tax
:   sta $0000,x
    sta $0100,x
    sta $0300,x
    sta $0400,x
    sta $0500,x
    sta $0600,x
    sta $0700,x
    inx
    bne :-
    lda #$F0
:   sta $0200,x
    inx
    bne :-
:   bit $2002
    bpl :-
    lda #$00
    sta sp
    lda #$08
    sta sp+1
    jsr zerobss
    jsr copydata
    jmp _main

nmi:
    pha
    txa
    pha
    tya
    pha
    lda #0
    sta $2003
    lda #$02
    sta $4014
    ldx #0
@next:
    cpx _vram_len
    bcs @done
    lda _vram_buf,x
    sta $2006
    inx
    lda _vram_buf,x
    sta $2006
    inx
    lda _vram_buf,x
    bmi @down          ; bit 7 is the column flag; INX would clobber N
    inx
    tay
@copy:
    lda _vram_buf,x
    sta $2007
    inx
    dey
    bne @copy
    jmp @next
@down:
    and #$7F
    inx
    tay
    lda _ppu_ctrl
    ora #$04
    sta $2000
@dcopy:
    lda _vram_buf,x
    sta $2007
    inx
    dey
    bne @dcopy
    lda _ppu_ctrl
    sta $2000
    jmp @next
@done:
.ifdef MMC5
    lda _split_line
    beq @noscroll
    lda #0
    sta $2005
    sta $2005
    lda _ppu_ctrl
    and #$FE
    sta $2000
    lda _split_line
    sta $5203
    lda #$80
    sta $5204
    jmp @nmi_out
@noscroll:
.endif
    lda _scroll_x
    sta $2005
    lda #0
    sta $2005
    lda _ppu_ctrl
    sta $2000
@nmi_out:
    inc _nmi_count
    pla
    tay
    pla
    tax
    pla
    rti

irq:
.ifdef MMC5
    pha
    lda $5204            ; ack the scanline IRQ
    lda _scroll_x
    sta $2005
    lda #0
    sta $2005
    lda _ppu_ctrl
    sta $2000
    pla
.endif
    rti

.segment "VECTORS"
    .word nmi, reset, irq

.segment "CHARS"
    .incbin "game.chr"
