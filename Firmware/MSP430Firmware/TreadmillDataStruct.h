#ifndef __TREADMILLDATASTRUCT_H
#define __TREADMILLDATASTRUCT_H

#include <stdint.h>

struct _TreadmillDataStruct {
  char StartChar;
  char DataLength;
  uint16_t MasterClockLow;
  uint16_t MasterClockHigh;
  int16_t  EncoderTicks;
  int32_t  UnwrappedEncoderTicks;
  uint8_t  GPIO;
  char EndChar;
} __attribute__((packed));


typedef struct _TreadmillDataStruct TreadmillDataStruct;

#endif
