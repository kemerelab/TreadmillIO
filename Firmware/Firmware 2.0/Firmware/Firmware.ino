#include "Firmware.h"

#define ENCODER_OPTIMIZE_INTERRUPTS // this messes up attachInterrupts
#include <Encoder.h>

Encoder wheelPosition(QUADA, QUADB);

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
        TreadmillData.GPIO = (GPIOD_PDIR & 0xFF) + ((GPIOB_PDIR & 0x0F) << 8);
        TreadmillData.AUXIO = (GPIOC_PDIR & 0xFFF);
        TreadmillData.UnwrappedEncoderTicks = wheelPosition.read();
        Serial.write((char *) &TreadmillData, sizeof(TreadmillDataStruct));
        Serial.flush();
    }

}

void setup() {

    InitGPIO();

    TreadmillData.StartChar = 'F'; // version 2.0 start character is "F" (1.0 was "E")
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


    digitalWrite(LED0, 0);
    digitalWrite(LED1, 0);
    digitalWrite(LED2, 0);
    digitalWrite(LED3, 0);

    Serial.begin(256000);

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
       digitalWrite(LED2, 0);
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
       led = 0;
       break;
       case 3:
       digitalWrite(LED3, 1);
       digitalWrite(LED2, 0);
       led = 0;
       break;
    }
}


#define SERIAL_READS_BEFORE_LEAVING 20

int NextUpdate = 0;
int NextClear = 500;

void loop() {

    interrupts();
    if (SerialTransmitFlag) {
        sendData();
        SerialTransmitFlag = false; // I'm worried about the case where I set this right when the timer is trying to wake us up.
        // But I guess in that case, it would indicate we're on the hairy edge of stability, which is bad anyway.

        sequenceLEDs();
    }


/*    
    if (MasterClock > NextClear) {
        digitalWrite(LED0, 0);
        digitalWrite(LED1, 0);
        digitalWrite(LED2, 0);
        digitalWrite(LED3, 0);
        NextClear = MasterClock + 1000;
    }

    if (MasterClock > NextUpdate) {
        int BytesAvailable = Serial.available();
        if (BytesAvailable > 0) {
            digitalWrite(LED0, BytesAvailable & 0x01);
            digitalWrite(LED1, BytesAvailable & 0x02);
            digitalWrite(LED2, BytesAvailable & 0x04);
            digitalWrite(LED3, BytesAvailable & 0x08);
            NextUpdate = MasterClock + 1000;
        }
    }
*/

    int SerialBufferFlushCounter = SERIAL_READS_BEFORE_LEAVING;
    uint8_t IncomingByte = '\0';

    while ((Serial.available() > 0) &&
            (SerialBufferFlushCounter > 0)) {

        IncomingByte = Serial.read();
        SerialBufferFlushCounter--;


        while ((IncomingByte != SerialCommandStart) && 
                (SerialBufferFlushCounter > 0)) {
            SerialBufferFlushCounter--;
            IncomingByte = Serial.read();
        }

        if (IncomingByte == SerialCommandStart) {
            uint8_t CommandByte = Serial.read();
            uint8_t CommandPin = Serial.read();
            uint8_t CommandValue = Serial.read();

            switch(CommandByte) {
                case ConfigDIOFlag:
                    ConfigDIO(CommandPin, CommandValue);
                    break;
                case ConfigAUXFlag:
                    ConfigAUX(CommandPin, CommandValue);
                    break;
                case WriteDIOFlag:
                    WriteDIO(CommandPin, CommandValue);
                    break;
                case WriteDIOMirrorFlag:
                    WriteDIO(CommandPin, CommandValue);
                    WriteAUX(CommandPin, CommandValue);
                    break;
                case WriteAUXFlag:
                    WriteAUX(CommandPin, CommandValue);
                    break;
            }

            SerialBufferFlushCounter -= 4;
        }
    }

}
