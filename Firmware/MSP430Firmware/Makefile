# MSP430 toolchain
CCPREFIX=/mnt/d/Development/Ti/msp430-gcc-7.3.2.154_linux64
INCPREFIX=/mnt/d/Development/Ti/msp430-gcc-support-files
TILIBPATH=/home/ckemere/ti/ccs900/ccs/ccs_base/DebugServer/drivers/
# mspdebug
MSPDEBUG=mspdebug

DEVICE=msp430g2553

PROJECT=treadmill.elf

SRC=main.c quadrature.c uart.c

OBJ=$(SRC:.c=.o)

CC=$(CCPREFIX)/bin/msp430-elf-gcc
# -Wextra removed to get rid of -Wold-style-declaration warnings
# -ggdb include gdb debugging symbol information 
# -Wa,-ahldn produces a memory map with the assembly.  Can be pretty handy
# -gdwarf-2 includes more symbol information for gdb 
# -g3 includes more symbol information for gdb 
CFLAGS=-mmcu=$(DEVICE) -I. -I $(INCPREFIX)/include -ggdb -g3 -Os -pipe -pedantic -Wall# -Wextra 
LFLAGS=-L $(INCPREFIX)/include -lgcc

all: $(PROJECT)

$(PROJECT): $(OBJ)
	$(CC) -mmcu=$(DEVICE) $(LFLAGS) -o $(PROJECT) $(OBJ)

flash: $(PROJECT)
	LD_LIBRARY_PATH=$(TILIBPATH) $(MSPDEBUG) tilib 'prog $(PROJECT)'

# To debug, you first call `mspdebug tilib` (probably need the library path too.
# Then, 'prog treadmill.elf', followed by 'gdb'. Then in a different terminal,
# run the msp430 gdb. Then, 'target remote localhost:2000' (that's the usual port
# that gets opened), followed by 'file treadmill.elf'. Then you're debugging!
# See here: https://sites.google.com/site/yeltrow/msp430-gcc-opensource-on-ubuntu

clean:
	rm -f *.o
	rm -f $(PROJECT)

.PHONY: all flash clean
