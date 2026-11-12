// The SOM's hard CPU (the GW5AST's Andes A25: Gowin's RiscV_AE350_SOC) as its IP generator would
// configure it: the defines its encrypted sources and riscv_ae350_top.v read.  Written by hand
// (the generator is a GUI), after the fpc console's (the same chip), where this set runs.
//
//   instruction memory  ours: the program's RAM on the ROM AHB port (0x80000000: rtl/cpu.v)
//   data memory         a port that answers nothing (the program's data is in the core's DLM,
//                       0xA0200000)
//   extended AHB slave  0xE8000000: the register bus (rtl/cpu.v)
//   UART2, PIT, GPIO, SMU   the SoC's own

`define AE350_EXT_I_MEM_EN
`define AE350_EXT_D_MEM_EN
`define AE350_EXT_INT_EN
`define AE350_EXT_AHB_SLAVE_EN
`define AE350_APB_UART2_EN
`define AE350_APB_PIT_EN
`define AE350_APB_GPIO_EN
`define AE350_APB_SMU_EN
