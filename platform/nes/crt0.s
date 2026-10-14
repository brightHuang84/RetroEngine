; retro_engine NES startup: iNES header (NROM-256, vertical mirroring), reset, NMI.
.export __STARTUP__ : absolute = 1
.export _nmi_count, _vram_buf, _vram_len, _scroll_x, _ppu_ctrl
.import _main, copydata, zerobss
.importzp sp

.segment "HEADER"
    .byte "NES", $1A, 2, 1, $01, $00
    .res 8, 0

.segment "ZEROPAGE"
_nmi_count: .res 1
_vram_len:  .res 1      ; committed bytes in $0300 buffer (C clears after each vblank)
_scroll_x:  .res 1
_ppu_ctrl:  .res 1      ; bit0 = nametable select (scroll >= 256), bit7 = NMI
_vram_buf = $0300

.segment "STARTUP"
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
    ldy _vram_buf,x
    inx
@copy:
    lda _vram_buf,x
    sta $2007
    inx
    dey
    bne @copy
    jmp @next
@done:
    lda _scroll_x
    sta $2005
    lda #0
    sta $2005
    lda _ppu_ctrl
    sta $2000
    inc _nmi_count
    pla
    tay
    pla
    tax
    pla
irq:
    rti

.segment "VECTORS"
    .word nmi, reset, irq

.segment "CHARS"
    .incbin "game.chr"
