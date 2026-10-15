; Column RLE decode and nametable upload. The C versions of these loops
; keep a 64-column level_load blank for dozens of frames on a 6502.
; cc65 fastcall: the rightmost argument is in A, earlier ones sit on the
; soft stack with the last pushed byte at (sp). A 16-bit pointer is stored
; low byte first. Callees pop what the caller pushed.

.importzp sp, _vram_len
.import _ppu_direct, _wait_vblank, _lv, _lv_col
_vram_buf = $0300

.segment "ZEROPAGE"
src:    .res 2
endp:   .res 2
pack:   .res 2
idxp:   .res 2
lvl:    .res 2
nrows:  .res 1
colx:   .res 1
ahi:    .res 1
alo:    .res 1
aval:   .res 1
tmp:    .res 1

.segment "CODE"

.proc drop3
    lda sp
    clc
    adc #3
    sta sp
    bcc :+
    inc sp+1
:   rts
.endproc

.proc drop2
    lda sp
    clc
    adc #2
    sta sp
    bcc :+
    inc sp+1
:   rts
.endproc

; void r_column(u8 x, const u8 *t, u8 rows)
.export _r_column
.proc _r_column
    cmp #31
    bcc @clamped
    lda #30
@clamped:
    sta nrows
    ldy #0
    lda (sp),y
    sta src
    iny
    lda (sp),y
    sta src+1
    iny
    lda (sp),y
    sta colx
    jsr drop3
    lda nrows
    beq @ret
    lda colx
    and #$20
    beq @page0
    lda #$24
    bne @have
@page0:
    lda #$20
@have:
    sta ahi
    lda colx
    and #$1F
    sta alo
    lda _ppu_direct
    bne @direct
    lda _vram_len
    clc
    adc #3
    bcs @lag
    adc nrows
    bcs @lag
    cmp #97
    bcc @fit
@lag:
    jsr _wait_vblank
@fit:
    ldx _vram_len
    lda ahi
    sta _vram_buf,x
    inx
    lda alo
    sta _vram_buf,x
    inx
    lda nrows
    ora #$80
    sta _vram_buf,x
    inx
    ldy #0
@q:
    lda (src),y
    sta _vram_buf,x
    inx
    iny
    cpy nrows
    bne @q
    stx _vram_len
@ret:
    rts
@direct:
    lda #$04
    sta $2000
    lda ahi
    sta $2006
    lda alo
    sta $2006
    ldy #0
@d:
    lda (src),y
    sta $2007
    iny
    cpy nrows
    bne @d
    lda #0
    sta $2000
    rts
.endproc

; void r_attr(u8 page, u8 idx, u8 value)
.export _r_attr
.proc _r_attr
    sta aval
    ldy #0
    lda (sp),y
    sta alo
    iny
    lda (sp),y
    jsr drop2
    ldx #$23
    cmp #0
    beq @p0
    ldx #$27
@p0:
    lda alo
    clc
    adc #$C0
    bcc @nc
    inx
@nc:
    sta alo
    stx ahi
    lda _ppu_direct
    bne @direct
    lda _vram_len
    cmp #93
    bcc @fit
    jsr _wait_vblank
@fit:
    ldx _vram_len
    lda ahi
    sta _vram_buf,x
    inx
    lda alo
    sta _vram_buf,x
    inx
    lda #1
    sta _vram_buf,x
    inx
    lda aval
    sta _vram_buf,x
    inx
    stx _vram_len
    rts
@direct:
    lda ahi
    sta $2006
    lda alo
    sta $2006
    lda aval
    sta $2007
    rts
.endproc

; void lv_decode(unsigned int column)
; A = low byte of the column, X = high byte.
.export _lv_decode
.proc _lv_decode
    sta alo
    stx ahi
    lda _lv
    sta lvl
    lda _lv+1
    sta lvl+1
    ldy #0
    lda (lvl),y
    sta pack
    iny
    lda (lvl),y
    sta pack+1
    iny
    lda (lvl),y
    sta idxp
    iny
    lda (lvl),y
    sta idxp+1
    ldy #12
    lda (lvl),y
    cmp #31
    bcc @rows
    lda #30
@rows:
    sta nrows
    lda alo
    asl
    sta alo
    lda ahi
    rol
    sta ahi
    jsr @word
    lda src
    pha
    lda src+1
    pha
    lda alo
    clc
    adc #2
    sta alo
    bcc @no
    inc ahi
@no:
    jsr @word
    lda src
    sta endp
    lda src+1
    sta endp+1
    pla
    sta src+1
    pla
    sta src
    ldx #0
@loop:
    cpx nrows
    bcs @pad
    lda src+1
    cmp endp+1
    bcc @go
    bne @pad
    lda src
    cmp endp
    bcs @pad
@go:
    ldy #0
    lda (src),y
    sta tmp
    jsr @incsrc
    and #$7F
    beq @loop
    sta aval
    lda tmp
    bmi @run
@lits:
    lda aval
    beq @loop
    cpx nrows
    bcs @loop
    ldy #0
    lda (src),y
    sta _lv_col,x
    jsr @incsrc
    inx
    dec aval
    jmp @lits
@run:
    ldy #0
    lda (src),y
    sta colx
    jsr @incsrc
@runb:
    lda aval
    beq @loop
    cpx nrows
    bcs @loop
    lda colx
    sta _lv_col,x
    inx
    dec aval
    jmp @runb
@pad:
    cpx nrows
    bcs @done
    lda #0
    sta _lv_col,x
    inx
    jmp @pad
@done:
    rts
; alo/ahi is the byte offset into the index. Leaves the pack pointer in src
; and advances alo/ahi so it is not needed again. Preserves nothing else.
@word:
    lda idxp
    clc
    adc alo
    sta src
    lda idxp+1
    adc ahi
    sta src+1
    ldy #0
    lda (src),y
    clc
    adc pack
    pha
    iny
    lda (src),y
    adc pack+1
    sta src+1
    pla
    sta src
    rts
@incsrc:
    inc src
    bne :+
    inc src+1
:   rts
.endproc
