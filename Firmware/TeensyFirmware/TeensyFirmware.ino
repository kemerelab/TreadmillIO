


#define CLOCK_PIN 0 // B16

#define QUADZ 30 // C11
#define QUADA 31 // E0
#define QUADB 32 // B18

#define D0 2 // D0
#define D1 14 // ...
#define D2 7
#define D3 8
#define D4 6
#define D5 20
#define D6 21
#define D7 5 // D7
#define D8 16 // B0
#define D9 17 // B1
#define D10 19 // B2
#define D11 18 // B3

#define C0 15 // C0
#define C1 22 // ..
#define C2 23
#define C3 9
#define C4 10
#define C5 13
#define C6 11
#define C7 12 // C7
#define C8 35 // C8
#define C9 36 // C9
#define C10 37 // C10
#define C11 38 // C11


#define LED0 25 // A5
#define LED1 26 // A14
#define LED2 27 // A15
#define LED3 28 // A16

#define ENCODER_OPTIMIZE_INTERRUPTS // this messes up attachInterrupts
#include <Encoder.h>


IntervalTimer sendDataTimer;

Encoder wheelPosition(QUADA, QUADB);

uint32_t ledState = 0x11111111;

struct _TreadmillDataStruct {
  char StartChar;
  char DataLength;
//  uint16_t MasterClockLow;
//  uint16_t MasterClockHigh;
  uint32_t MasterClock;
  int16_t  EncoderTicks;
  int32_t  UnwrappedEncoderTicks;
  uint8_t  GPIO;
  char EndChar;
} __attribute__((packed));
typedef struct _TreadmillDataStruct TreadmillDataStruct;

TreadmillDataStruct TreadmillData;

volatile uint32_t MasterClock = 0;

boolean SerialTransmitFlag = false;

// ISR routine for FlexTimer1 Module
extern "C" void ftm1_isr(void) {
  if ((FTM1_SC & FTM_SC_TOF) != 0) {  //read the timer overflow flag (TOF in FTM1_SC)
    MasterClock++;
    FTM1_SC &= ~FTM_SC_TOF;           //if set, clear overflow flag

    if ((MasterClock & 0x01) == 0)
      SerialTransmitFlag  = true;
  }
}

void sendData() {

  if (Serial.dtr()) {
    TreadmillData.MasterClock = MasterClock;
    TreadmillData.GPIO = GPIOD_PDIR;
    TreadmillData.UnwrappedEncoderTicks = wheelPosition.read();
    Serial.write((char *) &TreadmillData, sizeof(TreadmillDataStruct));
    Serial.flush();
  }

}


void setup() {
  pinMode(LED0, OUTPUT);
  pinMode(LED1, OUTPUT);
  pinMode(LED2, OUTPUT);
  pinMode(LED3, OUTPUT);
  digitalWrite(LED0,0);
  digitalWrite(LED1,0);
  digitalWrite(LED2,0);
  digitalWrite(LED3,0);

  pinMode(D0, INPUT);
  pinMode(D1, INPUT);
  pinMode(D2, INPUT);
  pinMode(D3, INPUT);
  pinMode(D4, OUTPUT);
  pinMode(D5, OUTPUT);
  pinMode(D6, OUTPUT);
  pinMode(D7, OUTPUT);
  pinMode(D8, OUTPUT);
  pinMode(D9, OUTPUT);
  pinMode(D10, OUTPUT);
  pinMode(D11, OUTPUT);

  pinMode(C0, OUTPUT);
  pinMode(C1, OUTPUT);
  pinMode(C2, OUTPUT);
  pinMode(C3, OUTPUT);
  pinMode(C4, OUTPUT);
  pinMode(C5, OUTPUT);
  pinMode(C6, OUTPUT);
  pinMode(C7, OUTPUT);
  pinMode(C8, INPUT);
  pinMode(C9, INPUT);
  pinMode(C10, INPUT);
  pinMode(C11, INPUT);
  digitalWrite(C0,1);
  digitalWrite(C1,1);
  digitalWrite(C2,1);
  digitalWrite(C3,1);
  digitalWrite(C4,0);
  digitalWrite(C5,0);
  digitalWrite(C6,0);
  digitalWrite(C7,0);


  digitalWrite(D4, 0);
  digitalWrite(D5, 0);
  digitalWrite(D6, 0);
  digitalWrite(D7, 0);
  digitalWrite(D8, 0);
  digitalWrite(D9, 0);
  digitalWrite(D10, 0);
  digitalWrite(D11, 0);
  
  TreadmillData.StartChar = 'E';
  TreadmillData.EndChar = '\n';
  TreadmillData.DataLength = sizeof(TreadmillDataStruct);

  /* 
   *  Set up FTM timer module which connects to external 2kHz
   *   clock for master timing. The clock is set up both to increment
   *   the master clock counter. When it overflows, this also triggers
   *   the high 16 bits of the master clock to increment.
   *   
   *   Note that unlike with the MSP430, we can't independently set
   *   a second interrupt to trigger every millisecond to drive serial
   *   data transmission, so we'll just use the Teensy for that.
   *   
   */
  CORE_PIN0_CONFIG = PORT_PCR_MUX(4);
  NVIC_DISABLE_IRQ(IRQ_FTM1);
  FTM1_SC = 0;
  FTM1_CNT = 0;
  FTM1_MOD = 0x1; // set to overflow every two ticks (1 kHz)
  FTM1_SC = FTM_SC_CLKS(3) + FTM_SC_PS(0) + FTM_SC_TOIE; // External clock input
  NVIC_ENABLE_IRQ(IRQ_FTM1);
  
  Serial.begin(256000);
  //sendDataTimer.begin(sendData, 2000); // 2 ms
}

void sequenceLEDs(void) {
  static int led = 0;
  static int count = 50;
  
  if (count-- == 0) {
    count = 50;
  }
  else {
    return;
  }
  
  
  switch (led) {
    case 0:
      digitalWrite(LED0, 1);
      digitalWrite(LED3, 0);
      led = 1;
      break;
    case 1:
      digitalWrite(LED1, 1);
      digitalWrite(LED0, 0);
      led = 2;
      break;
    case 2:
      digitalWrite(LED2, 1);
      digitalWrite(LED1, 0);
      led = 3;
      break;
    case 3:
      digitalWrite(LED3, 1);
      digitalWrite(LED2, 0);
      led = 0;
      break;
  }
}

void loop() {
  
  interrupts();
  if (SerialTransmitFlag) {
    sendData();
    SerialTransmitFlag = false; // I'm worried about the case where I set this right when the timer is trying to wake us up.
                                // But I guess in that case, it would indicate we're on the hairy edge of stability, which is bad anyway.

    sequenceLEDs();
  }
  
  if (Serial.available()) {
    uint8_t incomingByte = Serial.read();  // will not be -1
    GPIOD_PDOR = incomingByte & 0xF0; // Recalling that higher order bits are output
    GPIOC_PDOR = incomingByte & 0xF0; // Recalling that higher order bits are output
  }
}
