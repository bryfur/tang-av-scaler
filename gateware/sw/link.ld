/* The CPU's program: code and constants in its RAM at 0x80000000 (32 KB: rtl/cpu.v), data and
 * stack in the core's DLM (0xA0200000: 32 KB of it used)
 */

OUTPUT_ARCH("riscv")
ENTRY(_start)

MEMORY
{
    rom  (rx)  : ORIGIN = 0x80000000, LENGTH = 32K
    dlm  (rwx) : ORIGIN = 0xA0200000, LENGTH = 32K
}

SECTIONS
{
    .text : {
        KEEP(*(.text.start))
        *(.text .text.*)
        *(.rodata .rodata.* .srodata .srodata.*)
        . = ALIGN(4);
    } > rom

    .data : {
        __data_start = .;
        *(.data .data.*)
        __global_pointer$ = . + 0x800;
        *(.sdata .sdata.*)
        . = ALIGN(4);
        __data_end = .;
    } > dlm AT > rom
    __data_load = LOADADDR(.data);

    .bss (NOLOAD) : {
        __bss_start = .;
        *(.sbss .sbss.*) *(.bss .bss.*) *(COMMON)
        . = ALIGN(4);
        __bss_end = .;
    } > dlm

    __stack_top = ORIGIN(dlm) + LENGTH(dlm);
}
