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

/******************************************************************************
 * Hardware UART example for MSP430.
 *
 * Stefan Wendler
 * sw@kaltpost.de
 * http://gpio.kaltpost.de
 ******************************************************************************/

#include <msp430.h>
//#include <legacymsp430.h>

#include "uart.h"


/**
 * Receive Data (RXD) at P1.1
 */
#define RXD BIT1

/**
 * Transmit Data (TXD) at P1.2
 */
#define TXD BIT2

/**
 * Callback handler for receive
 */
void (*uart_rx_isr_ptr)(unsigned char c);

unsigned char NewGPIOFlag = 0;
unsigned char NewGPIO = 0;

void uart_init(void)
{
  P1SEL  |= RXD + TXD;                       
  P1SEL2 |= RXD + TXD;                       
  UCA0CTL1 |= UCSSEL_2;                     // SMCLK
  //UCA0BR0 = 0x40;                            // 8MHz 9600
  //UCA0BR1 = 0x03;                              // 8MHz 9600
  //UCA0MCTL = UCBRS0;                        // Modulation UCBRSx = 1
  UCA0BR0 = 31;                            // 8MHz 256kHz
  UCA0BR1 = 0x00;                              // 8MHz 256kHz
  UCA0MCTL = UCBRS1;                        // Modulation UCBRSx = 2
  UCA0CTL1 &= ~UCSWRST;                     // Initialize USCI state machine
  IE2 |= UCA0RXIE;                          // Enable USCI_A0 RX interrupt
}

unsigned char uart_getc()
{
    while (!(IFG2&UCA0RXIFG));                // USCI_A0 RX buffer ready?
    return UCA0RXBUF;
}

inline void uart_putc(unsigned char c)
{
    while (!(IFG2&UCA0TXIFG));              // USCI_A0 TX buffer ready?
    UCA0TXBUF = c;                        // TX
}

#define STRINGIFY2(x) #x
#define STRINGIFY(x) STRINGIFY2(x)

/*
   See http://www.ti.com/lit/ug/slau646d/slau646d.pdf
*/


//void uart_putw(uint16_t w)
void uart_putw(unsigned int w)
{
    w = _swap_bytes(w);
    while (!(IFG2&UCA0TXIFG));              // USCI_A0 TX buffer ready?
    UCA0TXBUF = w;                        // TX
    w = _swap_bytes(w);
    while (!(IFG2&UCA0TXIFG));              // USCI_A0 TX buffer ready?
    UCA0TXBUF = w;                        // TX

}

void uart_put_treadmill_struct(unsigned char *dptr)
{
    register unsigned char *eptr = dptr + sizeof(TreadmillDataStruct);
    while (eptr != dptr) {
      while (!(IFG2&UCA0TXIFG));              // USCI_A0 TX buffer ready?
      UCA0TXBUF = *dptr++;                        // TX
     
    }
}

// UART RX interrupt
//#pragma vector=USCIAB0RX_VECTOR
//__interrupt void USCI0RX_ISR(void)
void __attribute__((interrupt(USCIAB0RX_VECTOR))) USCI0RX_ISR(void)
{
  NewGPIO = UCA0RXBUF;                    // TX -> RXed character
  NewGPIOFlag = 1;
  __bic_SR_register_on_exit(CPUOFF);
}
