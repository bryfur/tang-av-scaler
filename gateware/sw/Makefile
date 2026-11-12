# The hard CPU's program (the GW5AST-138's Andes A25; rtl/cpu.v): build/cpu.hex for the bitstream
# (a 32-bit word a line, the first at 0x80000000) and build/cpu.bin for tools/cpu.py (a new program
# into a running board).  On fpga: make

CROSS ?= $(HOME)/tools/xpack-riscv-none-elf-gcc-15.2.0-1/bin/riscv-none-elf-
SRC = boot.S main.c board.c i2c.c osd.c time.c
DEP = $(SRC) hw.h link.h link.ld
# (BUILD: the newest source's time: the link gives the CPU the newer of its own copy and the bitstream's,
# and the same sources are the same program)
BUILD := $(shell stat -c %Y $(DEP) | sort -n | tail -1)
CFLAGS = -DBUILD=$(BUILD) -march=rv32imac_zicsr_zifencei -mabi=ilp32 -Os -g -ffreestanding -nostdlib -Wall -Wextra \
         -ffunction-sections -fdata-sections
B = build

all: $(B)/cpu.hex

$(B)/cpu.elf: $(DEP) | $(B)
	$(CROSS)gcc $(CFLAGS) -Wl,--gc-sections -T link.ld -o $@ $(SRC) -lgcc
	$(CROSS)size $@

$(B)/cpu.bin: $(B)/cpu.elf
	$(CROSS)objcopy -O binary $< $@

$(B)/cpu.hex: $(B)/cpu.bin
	python3 -c "import sys,struct; d=open(sys.argv[1],'rb').read(); d+=b'\0'*(-len(d)%4); open(sys.argv[2],'w').write(''.join('%08x\n'%w for w in struct.unpack('<%dI'%(len(d)//4),d)))" $< $@

$(B):
	mkdir -p $@

clean:
	rm -rf $(B)
