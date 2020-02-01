
#include "Firmware.h"
#include "core_pins.h"

// The GPIO Pin Table maps from communicated pin numbers for DIO and AUX pins (12 of each).
uint8_t PinTableDIO[] = {
  DIO1, DIO2, DIO3, DIO4, DIO5, DIO6, DIO7, DIO8, DIO9, DIO10, DIO11, DIO12 
};

uint8_t PinTableAUX[] = {
  AUX1, AUX2, AUX3, AUX4, AUX5, AUX6, AUX7, AUX8, AUX9, AUX10, AUX11, AUX12 
};


void ConfigDIO(uint8_t pin, uint8_t mode) { // Pins are 1 indexed rather than 0 indexed!
  if ((pin > 0) & (pin <= MAX_DIO))
    pinMode(PinTableDIO[pin - 1], mode);
}

void WriteDIO(uint8_t pin, uint8_t value) { // Pins are 1 indexed rather than 0 indexed!
  if ((pin > 0) & (pin <= MAX_DIO))
    digitalWrite(PinTableDIO[pin - 1], value);
}

void ConfigAUX(uint8_t pin, uint8_t mode) { // Pins are 1 indexed rather than 0 indexed!
  if ((pin > 0) & (pin <= MAX_AUX))
    pinMode(PinTableAUX[pin - 1], mode);
}

void WriteAUX(uint8_t pin, uint8_t value) { // Pins are 1 indexed rather than 0 indexed!
  if ((pin > 0) & (pin <= MAX_AUX))
    digitalWrite(PinTableAUX[pin - 1], value);
}


void InitGPIO() {
  pinMode(LED0, OUTPUT);
  pinMode(LED1, OUTPUT);
  pinMode(LED2, OUTPUT);
  pinMode(LED3, OUTPUT);
  digitalWrite(LED0,0);
  digitalWrite(LED1,0);
  digitalWrite(LED2,0);
  digitalWrite(LED3,0);

  for (int i=1; i <= MAX_DIO; i++) {
    ConfigDIO(i, INPUT);
  }

  for (int i=1; i <= MAX_AUX; i++) {
    ConfigAUX(i, INPUT);
  }

}
