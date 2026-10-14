/* GBA cartridge at 0x08000000. EWRAM holds .data/.bss. .bss is NOLOAD so
   objcopy -O binary does not pad the ROM out to EWRAM. */
OUTPUT_FORMAT("elf32-littlearm")
OUTPUT_ARCH(arm)
ENTRY(_start)

MEMORY {
    rom   : ORIGIN = 0x08000000, LENGTH = 32M
    ewram : ORIGIN = 0x02000000, LENGTH = 256K
}

SECTIONS {
    .text : {
        KEEP(*(.text.startup))
        *(.text*)
        *(.rodata*)
        . = ALIGN(4);
    } > rom

    .data : {
        . = ALIGN(4);
        __data_start = .;
        *(.data*)
        . = ALIGN(4);
        __data_end = .;
    } > ewram AT > rom
    __data_lma = LOADADDR(.data);

    .bss (NOLOAD) : {
        . = ALIGN(4);
        __bss_start = .;
        *(.bss*)
        *(COMMON)
        . = ALIGN(4);
        __bss_end = .;
    } > ewram

    /DISCARD/ : {
        *(.eh_frame*)
        *(.ARM.exidx*)
        *(.ARM.extab*)
        *(.comment)
        *(.note*)
        *(.gnu.attributes)
    }
}
