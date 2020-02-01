/*
 * This file is part of the MSP430 hardware UART example.
 *
 * Copyright (C) 2012 Stefan Wendler <sw@kaltpost.de>
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program.  If not, see <http://www.gnu.org/licenses/>.
 */

// NOTE: see README.md for more details about code structure

// Include custom code
#include "quadrature.h"
#include "uart.h"
#include "TreadmillDataStruct.h"

// Include libraries
#include <msp430.h>
#include <stdint.h>

// Define LED connectivity
#define LED_POUT P1OUT // LED output signal = port 1
#define LED_PDIR P1DIR // LED I/O direction = port 1
#define PWR_LED 0x20 // Pin 2.0
#define STATUS_LED 0x10 // Pin 2.1

volatile uint16_t MasterClockHigh = 0; // upper 16 bits of 32-bit clock

TreadmillDataStruct TreadmillData; // 
unsigned char *pTreadmillData;


void SendData()
{
    // NOTE: We're using POLLING for serial comms to make
    //   sure that if there's a conflict between timing
    //   or quadrature measurements and data x-mission,
    //   timing/quadrature wins.
    // This structure ensures that the data copied to 
    // pTreadmillData is not changing while being written.

    // Copy current clock and encoder data atomically.
    __disable_interrupt();

    /*
    TreadmillData.MasterClockLow = TA0R;
    TreadmillData.MasterClockHigh = MasterClockHigh;
    TreadmillData.EncoderTicks = EncoderTicks;
    TreadmillData.UnwrappedEncoderTicks = UnwrappedEncoder;
    TreadmillData.GPIO = P3IN;    
    */
    
    *(uint16_t *)(&pTreadmillData[2]) = TA0R;
    *(uint16_t *)(&pTreadmillData[4]) = MasterClockHigh;
    *(int16_t *)(&pTreadmillData[6]) = EncoderTicks;
    *(int32_t *)(&pTreadmillData[8]) = UnwrappedEncoder;
    pTreadmillData[12] = P3IN;

    __enable_interrupt();

    uart_put_treadmill_struct((unsigned char *)&TreadmillData);

    return;
}


/**
 * Main routine
 */
int main(void)
{
 
    WDTCTL = WDTPW + WDTHOLD;                 // Stop WDT

    // Set up system clocks
    // Drive master clock at 8MHz
    BCSCTL1 = CALBC1_8MHZ;   // Set range
    DCOCTL = CALDCO_8MHZ;    // Set DCO step + modulation
    
    // Make sure everything is reset!
    P1DIR = 0x00;
    P2DIR = 0x00;
    P3DIR = 0x00;
    P1IE = 0x00;
    P2IE = 0x00;
    
    P1SEL = 0x01;
    P1SEL2 = 0x00;
    TA0CTL = TASSEL_0 + MC_2 + ID_1 + TAIE + TACLR;  // TA0CLK Input (2KHz), 
      // continuous mode, divide by 2 (1 kHz), enable timer overflow interrupt, reset counter
    TA0CCR0 = 100;            // interrupt on overflow
    TA0CCTL0 = CCIE;           // CCR0 interrupt enabled
 
    LED_PDIR |= STATUS_LED + PWR_LED;     
    LED_POUT |= STATUS_LED + PWR_LED;     // All LEDs on

    pTreadmillData = (unsigned char*) &TreadmillData;
    TreadmillData.StartChar = 'E';
    TreadmillData.EndChar = '\n';
    TreadmillData.DataLength = sizeof(TreadmillData);

    P3DIR = 0xE0; // No one else should be using Port 3!!!
    //P3REN = 0xFF; // Turn on pull up/down resistors
    P3OUT = 0; // Set to pull down

    quadrature_init();
    uart_init();

    __bis_SR_register(GIE);

    while(1) {
     LED_POUT ^= STATUS_LED;       // Toggle LED using exclusive-OR

     if (NewGPIOFlag) {
       P3OUT = NewGPIO;
       NewGPIOFlag = 0;
     }

     SendData();

     __bis_SR_register(CPUOFF + GIE); // Enter LPM0 w/ interrupts
    } 
}

// Increment time register by 2 ms
// Timer A0 CCR0 interrupt service routine => Wake up every 100 ms
//   Assumes TimerA0 is set up for 1 ms, continuous mode.
//#pragma vector=TIMER0_A0_VECTOR
//__interrupt void WakeupClockISR (void)
void __attribute__((interrupt(TIMER0_A0_VECTOR))) WakeupClockISR (void)
{
  //TA0CCR0 += 100;
  //__bic_SR_register_on_exit(CPUOFF);
  
  // Using assembly saves a push and pop
  __asm__("add #2, %[TIMERREG]\n" // SERIAL TRANSMIT PERIOD in milliseconds
          "bic #16,  0(R1)\n" // bic_SR_on_exit(CPUOFF) //"reti\n"
  :[TIMERREG] "=m" (TA0CCR0) );
}

// Handle overflows in LOW register every 2^16 = 65536 ms by incrementing HIGH register
// Timer A0 overflow interrupt service routine => increment higher 16bit counter
//   Assumes TimerA0 is set up for 1 ms, continuous mode.
//#pragma vector=TIMER0_A1_VECTOR
//__interrupt void MasterClockISR (void)
void __attribute__((interrupt(TIMER0_A1_VECTOR))) MasterClockISR (void)
{
  //if (TA0IV & TAIFG)
  //  MasterClockHigh++;

  // Use ISR table construction from Users Guide
  __asm__("add %[Offset], r0\n"
          "reti\n" // Vector 0: No Interrupt
          "reti\n" // Vector 2: TACCR1; would be a JMP if used
          "reti\n" // Vector 4: TACCR1; would be a JMP if used
          "reti\n" // Vector 4: Reserved
          "reti\n" // Vector 8: Reserved
          "inc %[MasterClockHigh]\n"
  : [MasterClockHigh] "=m" (MasterClockHigh) : [Offset] "m" (TA0IV) );
  // RETI is automatically added at end 
}
