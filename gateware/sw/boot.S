/* The program's start: the A25 out of reset at 0x80000000 (the program's RAM: rtl/cpu.v).  Its
 * data and stack in the core's DLM (0xA0200000): .data copied there, .bss cleared, the caches on
 * (Andes' mcache_ctl: off at reset), then main().  A trap: its cause and place left for the host
 * (registers 66, 67), and it stops.
 */

    .section .text.start, "ax"
    .global _start
_start:
    j       1f
    .balign 4
    .word   0x32435641              /* "AVC2": at 4 */
    .global build_stamp
build_stamp:
    .word   BUILD                   /* at 8: when it was built */
1:
    .option push
    .option norelax
    la      gp, __global_pointer$
    .option pop
    la      sp, __stack_top
    la      t0, trap
    csrw    mtvec, t0
    csrsi   0x7ca, 3

    la      t0, __data_load
    la      t1, __data_start
    la      t2, __data_end
1:  bgeu    t1, t2, 2f
    lw      t3, 0(t0)
    sw      t3, 0(t1)
    addi    t0, t0, 4
    addi    t1, t1, 4
    j       1b
2:  la      t1, __bss_start
    la      t2, __bss_end
3:  bgeu    t1, t2, 4f
    sw      zero, 0(t1)
    addi    t1, t1, 4
    j       3b
4:  call    main
5:  wfi
    j       5b

    .balign 4
trap:
    li      t0, 0xe8000000
    csrr    t1, mcause
    li      t2, 0xdead0000
    or      t1, t1, t2
    sw      t1, 0x198(t0)           /* register 66 */
    csrr    t1, mepc
    sw      t1, 0x19c(t0)           /* register 67 */
6:  j       6b
