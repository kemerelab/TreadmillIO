
#include <stdint.h>

#define CLOCK_PIN 0 // B16

#define QUADZ 30 // C11
#define QUADA 31 // E0
#define QUADB 32 // B18

#define DIO1 2 // D0
#define DIO2 14 // ...
#define DIO3 7
#define DIO4 8
#define DIO5 6
#define DIO6 20
#define DIO7 21
#define DIO8 5 // D7
#define DIO9 16 // B0
#define DIO10 17 // B1
#define DIO11 19 // B2
#define DIO12 18 // B3

#define MAX_DIO 12


#define AUX1 15 // C0
#define AUX2 22 // ..
#define AUX3 23
#define AUX4 9
#define AUX5 10
#define AUX6 13
#define AUX7 11
#define AUX8 12 // C7
#define AUX9 35 // C8
#define AUX10 36 // C9
#define AUX11 37 // C10
#define AUX12 38 // C11

#define MAX_AUX 12


#define LED0 25 // A5
#define LED1 26 // A14
#define LED2 27 // A15
#define LED3 28 // A16

#define SerialCommandStart 0xA9
#define ConfigDIOFlag   'C'
#define ConfigAUXFlag   'X'
#define WriteDIOFlag    'D'
#define WriteDIOMirrorFlag    'M'
#define WriteAUXFlag    'A'


struct _TreadmillDataStruct {
  char StartChar;
  char DataLength;
  uint32_t MasterClock;
  int16_t  EncoderTicks;
  int32_t  UnwrappedEncoderTicks;
  uint16_t  GPIO;
  uint16_t  AUXIO;
  char EndChar;
} __attribute__((packed));
typedef struct _TreadmillDataStruct TreadmillDataStruct;



void InitGPIO();
void ConfigDIO(uint8_t pin, uint8_t mode);
void WriteDIO(uint8_t pin, uint8_t value);
void ConfigAUX(uint8_t pin, uint8_t mode);
void WriteAUX(uint8_t pin, uint8_t value);
