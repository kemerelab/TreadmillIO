### Compiler notes
We went through a bunch of trouble to install the newest GCC for MSP430. Useful weblinks:
  + http://www.ti.com/tool/msp430-gcc-opensource
  + http://software-dl.ti.com/msp430/msp430_public_sw/mcu/msp430/MSPGCC/latest/index_FDS.html

To program, we use mspdebug (again, the newest version cloned from Github), and also have to
link to the dynamic library libmsp430.so, which is found in the CCS directory (see Makefile).
  + 

Useful documentation on toolchain:
  + https://sites.google.com/site/yeltrow/msp430-gcc-opensource-on-ubuntu

And someone's Makefile prototype.
  + https://github.com/m-thu/msp430/blob/master/apa102/Makefile

_In the end, the issue with struct packing that prompted the upgrade (wanting to be able to
specify endian-ness), was not actually useful. The bug was that when we cast a char* to a
int16* it just **truncates the last bit of the address**, meaning that it will always be even,
and if we write to this pointer, it will actually overwrite the **byte before it** if it was
trying to be at an odd address._

### MSP430 programming

#### Digitial I/O ports
The MSP430 (in this version, at least) has three ports that each consist of eight I/O pins on the external connections. Each port is characterized by several registers in memory, where each eight-bit register contains one bit for each I/O pin of that port. What that bit represents depends on the type of memory register; three important memory registers associated with each port are:
- **PxDIR** (read/write): sets the direction of the pin for all functions (0 = input, 1 = output)
- **PxIN** (read only): contains the input signal of pins configured for input (0 = low, 1 = high)
- **PxOUT** (read/write): sets the output signal of pins configured for output (0 = low, 1 = high))
where "x" represents the port number (1, 2, 3, etc.). For more information, see the attached user manual, or [this link](http://maxembedded.com/2013/12/io-port-operations-in-msp430/) for a quick overview.

In the custom hat, port 3 (P3) is connected to the eight GPIO pins in order (i.e. pin 1 ~ GPIO 16, pin 2 ~ GPIO 17, ...). Thus the direction and states of the GPIO pins can be set by altering the values in `P3DIR`, `P3IN`, and `P3OUT`. For example, `P3DIR = 0x03` configures GPIO pins 16 and 17 for output, and the rest for input (remember that `03` in hex is `0000 0011` in binary; also note that GPIO numerical order goes from LSB to MSB).