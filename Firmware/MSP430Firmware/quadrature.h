#ifndef __QUADRATURE_H
#define __QUADRATURE_H

#include <msp430.h>
#include <stdint.h>

// Macros to shortcut which ports / pins are used for Quadrature encoder
//    interface. 

#define EncPIN P2IN
#define EncPIE P2IE
#define EncPIES P2IES
#define EncPIFG P2IFG

#define BitA 0x02 // Pin 2.1
#define BitB 0x01 // Pin 2.0
#define BitZ 0x04 // Pin 2.2

extern volatile uint16_t IndexTicks;
extern volatile int16_t EncoderTicks;
extern volatile int LastFullCycle;
extern volatile int16_t FullCycleTicks;
extern volatile int32_t UnwrappedEncoder;


void quadrature_init(void);


#endif
