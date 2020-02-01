
#include "quadrature.h"

volatile uint16_t IndexTicks = 0;
volatile int16_t EncoderTicks = 0;
volatile int LastFullCycle = -1;
volatile int16_t FullCycleTicks = 0;
volatile int32_t UnwrappedEncoder = 0;

void quadrature_init(void)
{
    EncPIE |= BitA + BitZ;
    EncPIFG = 0;
}

#define STRINGIFY2(x) #x
#define STRINGIFY(x) STRINGIFY2(x)

//#pragma vector=PORT2_VECTOR
//__interrupt void QuadratureISR(void) 
void __attribute__((interrupt(PORT2_VECTOR))) QuadratureISR (void)
{
  /*
  static int ZInterlock = 4;

  __asm__(
    "mov.b %[PxIE], R15\n"
    "mov.b %[PxIN], R14\n"
    "bit.b #" STRINGIFY(BitA) ", R15\n"
    "jz CHECK_B\n"
    "A_TRIGGERED:\n"
    "bit.b #" STRINGIFY(BitB) ", R14\n"
    "jnz DEC_COUNTER\n"
    "jmp INC_COUNTER\n"
    
    "CHECK_B:\n"
    "bit.b #" STRINGIFY(BitB) ", R15\n"
    "jz CHECK_Z\n"
    "B_TRIGGERED:\n"
    "bit.b #" STRINGIFY(BitA) ", R14\n"
    "jnz INC_COUNTER\n"

    "DEC_COUNTER:\n"
    "dec %[EncoderTicks]\n"
    "jmp TOGGLE_CHANNEL\n"
    
    "INC_COUNTER:\n"
    "inc %[EncoderTicks]\n"
    
    "TOGGLE_CHANNEL:\n"
    "xor.b #" STRINGIFY(BitA+BitB) ", %[PxIE]\n"
    "bic.b #" STRINGIFY(BitA+BitB) ", %[PxIFG]\n"
    
    "bit.b #" STRINGIFY(BitZ) ", R14\n" // Check if Z pin is low
    "jnz CHECK_Z\n"
    "DECREMENT_Z_INTERLOCK:\n"
    "dec %[ZInterlock]\n"
    "jnz CHECK_Z\n"
    "bis.b #" STRINGIFY(BitZ) ", %[PxIE]\n"
    "mov #4, %[ZInterlock]\n"
    
    "CHECK_Z:\n"  
    "bit.b #" STRINGIFY(BitZ) ", %[PxIE]\n"
    "jz CONCLUDE\n"
    "bit.b #" STRINGIFY(BitZ) ", %[PxIFG]\n"
    "jz CONCLUDE\n"
    "inc %[IndexTicks]\n"
    "mov %[EncoderTicks], %[FullCycleTicks]\n"
    "mov #0, %[EncoderTicks]\n"
    "bic.b #" STRINGIFY(BitZ) ", %[PxIE]\n"
    "bic.b #" STRINGIFY(BitZ) ", %[PxIFG]\n"
    "CONCLUDE:\n"
  : [PxIE] "=m" (EncPIE), [PxIFG] "=m" (EncPIFG), [EncoderTicks] "=m" (EncoderTicks), 
    [ZInterlock] "=m" (ZInterlock), [IndexTicks] "=m" (IndexTicks), [FullCycleTicks] "=m" (FullCycleTicks)
  : [PxIN] "m" (EncPIN) : "R14", "R15" );

*/
/*
  if ((EncPIE & BitA) > 0) {
    if (!(EncPIN && BitB)) {
      EncoderTicks += 1; 
    }
    else {
      EncoderTicks -= 1;
    }
    EncPIE &= ~BitA;  // Turn off A
    EncPIE |= BitB;  // Turn on B
    //EncPIE ^= BitA + BitB;
    EncPIFG &= ~(BitA + BitB); // Clear A Flag (why do I have to clear B here???)
    if ((EncPIN & BitZ) == 0) {
      ZInterlock--;
      if (ZInterlock == 0){
        EncPIE |= BitZ;
        ZInterlock = 4;
      }
    }
  }
  else if ((EncPIE & BitB) > 0)  {
    if (EncPIN && BitA) {
      EncoderTicks += 1; 
    }
    else {
      EncoderTicks -= 1;
    }
    EncPIE &= ~BitB; // Turn off B
    EncPIE = BitA; // Turn on A
    //EncPIE ^= BitA + BitB;
    EncPIFG &= ~(BitA + BitB); // Clear A Flag (why do I have to clear B here???)
    if ((EncPIN & BitZ) == 0) {
      ZInterlock--;
      if (ZInterlock == 0){
        EncPIE |= BitZ;
        ZInterlock = 4;
      }
    }
  }

  if ((EncPIE & BitZ) > 0) { // Index!
    if ((EncPIFG & BitZ) > 0) {
      IndexTicks++;
      FullCycleTicks = EncoderTicks;
      EncoderTicks = 0;
      EncPIFG &= ~(BitZ);
      EncPIE &= ~(BitZ); // Disable for a while
    }
  }
*/


  if ((EncPIFG & BitA) > 0) {
    EncPIE &= ~BitA;  // Turn off A

    if ((EncPIES & BitA) == 0) { // Rising edge interrupt
      if ((EncPIN & BitA) == BitA) {
        if ((EncPIN & BitB) == 0) {
          EncoderTicks += 1;
          UnwrappedEncoder += 1;
        }
        else {
          EncoderTicks -= 1;
          UnwrappedEncoder -= 1;
        }
        EncPIES |= BitA; // Switch to rising edge
      }
    }
    else { // Falling Edge
      if ((EncPIN & BitA) == 0) {
        if ((EncPIN & BitB) == BitB) {
          EncoderTicks += 1;
          UnwrappedEncoder += 1; 
        }
        else {
          EncoderTicks -= 1;
          UnwrappedEncoder -= 1;
        }
      }
      EncPIES &= ~BitA; // Switch to falling edge 
    }
    EncPIFG &= ~(BitA); // Clear A Flag
    EncPIE |= BitA;  
  }

  if ((EncPIFG & BitZ) > 0) {
    EncoderTicks = 0;
    EncPIFG &= ~(BitZ);
  }

}  
