# Setting up a SyringePump.com NE-500

1. Plug in the programming cable to the "Computer" port on the pump. Plug
the other end into a USB-to-RS232-serial adapter, and plug that USB into a  port 
on the computer. On my system, this creates a serial port at `/dev/ttyUSB0`.

2. Use a serial terminal program (e.g., `gtkterm`) to connect to this serial port.
The speed should be `19200` baud and the configuration is `8N1` (which should
be the default). It may be helpful to enable `Local Echo` and `CR LF Auto`, though
the later is not necessary.

3. If you press the enter key, you should get a message that's something like `00S`.
This is a status message that I think means that nothing is going on and the pump
is "stopped".

4. Program the syringe diameter using the table at the end of the NE-500 manual
(reproduced below). For example, for a B-D 5 ml syringe, `DIA 11.99` (press the
"Enter" key at the end of commands. Type `DIA` and check that it now reports `11.99`.

5. Set the trigger mode to be active high. The manual refers to this as "Foot Switch Reversed"
mode in section 6.5 (p. 10). Type `TRG F2` to set this mode. Type `TRG` and check
that it has updated to `F2`.

6. We need to tell the pump that when triggered to dispense the appropriate volume. We'll
use the constant-rate infusion mode, `FUN RAT`. We'll need to set an infusion rate and
volume, and make sure that the direction is set to "infusion" (rather than "fill"). For example
using a rate of 250 mL/hr, and a volume of 4 μL, we type: 
`FUN RAT<enter>RAT 250 MH<enter>VOL 4<enter>DIR INF<enter>`. (Note that the default volume units
are microliters!)

7. If everything is working right, when you trigger the syringe pump, you should now get
droplets the right size emerging!

## Syringe Diameters:
|Manufacturer          |Size (mL)|Inside Diameter (mm)|Maxmium Rate (mL/hr)|Minimum Rate
(μL/hr)|Maximum Rate (mL/min)|
|----------------------|---------|--------------------|--------------------|--------------------|---------------------|
|B-D                   |1        |4.699               |53.07               |0.73
|0.884                |
|B-D                   |3        |8.585               |177.1               |2.434
|2.952                |
|B-D                   |5        |11.99               |345.5               |4.748
|5.758                |
|B-D                   |10       |14.43               |500.4               |6.876
|8.341                |
|B-D                   |20       |19.05               |872.2               |11.99
|14.53                |
|B-D                   |30       |21.59               |1120                |15.4
|18.67                |
|B-D                   |60       |26.59               |1699                |23.35
|28.32                |
|HSW Norm-Ject         |1        |4.69                |52.86               |0.727
|0.881                |
|HSW Norm-Ject         |3        |9.65                |223.8               |3.076
|3.73                 |
|HSW Norm-Ject         |5        |12.45               |372.5               |5.119
|6.209                |
|HSW Norm-Ject         |10       |15.9                |607.6               |8.349
|10.12                |
|HSW Norm-Ject         |20       |20.05               |966.2               |13.28
|16.1                 |
|HSW Norm-Ject         |30       |22.9                |1260                |17.32               |21
|
|HSW Norm-Ject         |50       |29.2                |2049                |28.16
|34.15                |
|Monoject              |1        |5.74                |79.18               |1.088
|1.319                |
|Monoject              |3        |8.941               |192.1               |2.64
|3.202                |
|Monoject              |6        |12.7                |387.6               |5.326
|6.46                 |
|Monoject              |12       |15.72               |593.9               |8.161
|9.899                |
|Monoject              |20       |20.12               |972.9               |13.37
|16.21                |
|Monoject              |35       |23.52               |1329                |18.27
|22.15                |
|Monoject              |60       |26.64               |1705                |23.44
|28.42                |
|Monoject              |140      |38                  |3470                |47.69
|57.84                |
|Terumo                |1        |4.7                 |53.09               |0.73
|0.884                |
|Terumo                |3        |8.95                |192.5               |2.646
|3.208                |
|Terumo                |5        |13                  |406.1               |5.581
|6.769                |
|Terumo                |10       |15.8                |600                 |8.244               |10
|
|Terumo                |20       |20.15               |975.8               |13.41
|16.26                |
|Terumo                |30       |23.1                |1282                |17.63
|21.37                |
|Terumo                |60       |29.7                |2120                |29.13
|35.33                |
|Poulten & Graf (Glass)|1        |6.7                 |107.8               |1.483
|1.798                |
|Poulten & Graf (Glass)|2        |8.91                |190.8               |2.622
|3.18                 |
|Poulten & Graf (Glass)|3        |9.06                |197.2               |2.711
|3.288                |
|Poulten & Graf (Glass)|5        |11.75               |331.8               |4.559
|5.53                 |
|Poulten & Graf (Glass)|10       |14.67               |517.2               |7.107
|8.62                 |
|Poulten & Graf (Glass)|20       |19.62               |925.2               |12.72
|15.42                |
|Poulten & Graf (Glass)|30       |22.69               |1237                |17.01
|20.62                |
|Poulten & Graf (Glass)|50       |26.96               |1746                |24.01
|29.11                |
|Steel Syringes        |1        |9.538               |218.6               |3.005
|3.644                |
|Steel Syringes        |3        |9.538               |218.6               |3.005
|3.644                |
|Steel Syringes        |5        |12.7                |387.6               |5.326
|6.46                 |
|Steel Syringes        |8        |9.538               |218.6               |3.005
|3.644                |
|Steel Syringes        |20       |19.13               |879.5               |12.09
|14.65                |
|Steel Syringes        |50       |28.6                |1965                |27.01
|32.76                |
## Syringe Diameters:
|Manufacturer          |Size (mL)|Inside Diameter (mm)|Maxmium Rate (mL/hr)|Minimum Rate
(μL/hr)|Maximum Rate (mL/min)|
|----------------------|---------|--------------------|--------------------|--------------------|---------------------|
|B-D                   |1        |4.699               |53.07               |0.73
|0.884                |
|B-D                   |3        |8.585               |177.1               |2.434
|2.952                |
|B-D                   |5        |11.99               |345.5               |4.748
|5.758                |
|B-D                   |10       |14.43               |500.4               |6.876
|8.341                |
|B-D                   |20       |19.05               |872.2               |11.99
|14.53                |
|B-D                   |30       |21.59               |1120                |15.4
|18.67                |
|B-D                   |60       |26.59               |1699                |23.35
|28.32                |
|HSW Norm-Ject         |1        |4.69                |52.86               |0.727
|0.881                |
|HSW Norm-Ject         |3        |9.65                |223.8               |3.076
|3.73                 |
|HSW Norm-Ject         |5        |12.45               |372.5               |5.119
|6.209                |
|HSW Norm-Ject         |10       |15.9                |607.6               |8.349
|10.12                |
|HSW Norm-Ject         |20       |20.05               |966.2               |13.28
|16.1                 |
|HSW Norm-Ject         |30       |22.9                |1260                |17.32               |21
|
|HSW Norm-Ject         |50       |29.2                |2049                |28.16
|34.15                |
|Monoject              |1        |5.74                |79.18               |1.088
|1.319                |
|Monoject              |3        |8.941               |192.1               |2.64
|3.202                |
|Monoject              |6        |12.7                |387.6               |5.326
|6.46                 |
|Monoject              |12       |15.72               |593.9               |8.161
|9.899                |
|Monoject              |20       |20.12               |972.9               |13.37
|16.21                |
|Monoject              |35       |23.52               |1329                |18.27
|22.15                |
|Monoject              |60       |26.64               |1705                |23.44
|28.42                |
|Monoject              |140      |38                  |3470                |47.69
|57.84                |
|Terumo                |1        |4.7                 |53.09               |0.73
|0.884                |
|Terumo                |3        |8.95                |192.5               |2.646
|3.208                |
|Terumo                |5        |13                  |406.1               |5.581
|6.769                |
|Terumo                |10       |15.8                |600                 |8.244               |10
|
|Terumo                |20       |20.15               |975.8               |13.41
|16.26                |
|Terumo                |30       |23.1                |1282                |17.63
|21.37                |
|Terumo                |60       |29.7                |2120                |29.13
|35.33                |
|Poulten & Graf (Glass)|1        |6.7                 |107.8               |1.483
|1.798                |
|Poulten & Graf (Glass)|2        |8.91                |190.8               |2.622
|3.18                 |
|Poulten & Graf (Glass)|3        |9.06                |197.2               |2.711
|3.288                |
|Poulten & Graf (Glass)|5        |11.75               |331.8               |4.559
|5.53                 |
|Poulten & Graf (Glass)|10       |14.67               |517.2               |7.107
|8.62                 |
|Poulten & Graf (Glass)|20       |19.62               |925.2               |12.72
|15.42                |
|Poulten & Graf (Glass)|30       |22.69               |1237                |17.01
|20.62                |
|Poulten & Graf (Glass)|50       |26.96               |1746                |24.01
|29.11                |
|Steel Syringes        |1        |9.538               |218.6               |3.005
|3.644                |
|Steel Syringes        |3        |9.538               |218.6               |3.005
|3.644                |
|Steel Syringes        |5        |12.7                |387.6               |5.326
|6.46                 |
|Steel Syringes        |8        |9.538               |218.6               |3.005
|3.644                |
|Steel Syringes        |20       |19.13               |879.5               |12.09
|14.65                |
|Steel Syringes        |50       |28.6                |1965                |27.01
|32.76                |
## Syringe Diameters:
|Manufacturer          |Size (mL)|Inside Diameter (mm)|Maxmium Rate (mL/hr)|Minimum Rate
(μL/hr)|Maximum Rate (mL/min)|
|----------------------|---------|--------------------|--------------------|--------------------|---------------------|
|B-D                   |1        |4.699               |53.07               |0.73
|0.884                |
|B-D                   |3        |8.585               |177.1               |2.434
|2.952                |
|B-D                   |5        |11.99               |345.5               |4.748
|5.758                |
|B-D                   |10       |14.43               |500.4               |6.876
|8.341                |
|B-D                   |20       |19.05               |872.2               |11.99
|14.53                |
|B-D                   |30       |21.59               |1120                |15.4
|18.67                |
|B-D                   |60       |26.59               |1699                |23.35
|28.32                |
|HSW Norm-Ject         |1        |4.69                |52.86               |0.727
|0.881                |
|HSW Norm-Ject         |3        |9.65                |223.8               |3.076
|3.73                 |
|HSW Norm-Ject         |5        |12.45               |372.5               |5.119
|6.209                |
|HSW Norm-Ject         |10       |15.9                |607.6               |8.349
|10.12                |
|HSW Norm-Ject         |20       |20.05               |966.2               |13.28
|16.1                 |
|HSW Norm-Ject         |30       |22.9                |1260                |17.32               |21
|
|HSW Norm-Ject         |50       |29.2                |2049                |28.16
|34.15                |
|Monoject              |1        |5.74                |79.18               |1.088
|1.319                |
|Monoject              |3        |8.941               |192.1               |2.64
|3.202                |
|Monoject              |6        |12.7                |387.6               |5.326
|6.46                 |
|Monoject              |12       |15.72               |593.9               |8.161
|9.899                |
|Monoject              |20       |20.12               |972.9               |13.37
|16.21                |
|Monoject              |35       |23.52               |1329                |18.27
|22.15                |
|Monoject              |60       |26.64               |1705                |23.44
|28.42                |
|Monoject              |140      |38                  |3470                |47.69
|57.84                |
|Terumo                |1        |4.7                 |53.09               |0.73
|0.884                |
|Terumo                |3        |8.95                |192.5               |2.646
|3.208                |
|Terumo                |5        |13                  |406.1               |5.581
|6.769                |
|Terumo                |10       |15.8                |600                 |8.244               |10
|
|Terumo                |20       |20.15               |975.8               |13.41
|16.26                |
|Terumo                |30       |23.1                |1282                |17.63
|21.37                |
|Terumo                |60       |29.7                |2120                |29.13
|35.33                |
|Poulten & Graf (Glass)|1        |6.7                 |107.8               |1.483
|1.798                |
|Poulten & Graf (Glass)|2        |8.91                |190.8               |2.622
|3.18                 |
|Poulten & Graf (Glass)|3        |9.06                |197.2               |2.711
|3.288                |
|Poulten & Graf (Glass)|5        |11.75               |331.8               |4.559
|5.53                 |
|Poulten & Graf (Glass)|10       |14.67               |517.2               |7.107
|8.62                 |
|Poulten & Graf (Glass)|20       |19.62               |925.2               |12.72
|15.42                |
|Poulten & Graf (Glass)|30       |22.69               |1237                |17.01
|20.62                |
|Poulten & Graf (Glass)|50       |26.96               |1746                |24.01
|29.11                |
|Steel Syringes        |1        |9.538               |218.6               |3.005
|3.644                |
|Steel Syringes        |3        |9.538               |218.6               |3.005
|3.644                |
|Steel Syringes        |5        |12.7                |387.6               |5.326
|6.46                 |
|Steel Syringes        |8        |9.538               |218.6               |3.005
|3.644                |
|Steel Syringes        |20       |19.13               |879.5               |12.09
|14.65                |
|Steel Syringes        |50       |28.6                |1965                |27.01
|32.76                |
## Syringe Diameters:
|Manufacturer          |Size (mL)|Inside Diameter (mm)|Maxmium Rate (mL/hr)|Minimum Rate
(μL/hr)|Maximum Rate (mL/min)|
|----------------------|---------|--------------------|--------------------|--------------------|---------------------|
|B-D                   |1        |4.699               |53.07               |0.73
|0.884                |
|B-D                   |3        |8.585               |177.1               |2.434
|2.952                |
|B-D                   |5        |11.99               |345.5               |4.748
|5.758                |
|B-D                   |10       |14.43               |500.4               |6.876
|8.341                |
|B-D                   |20       |19.05               |872.2               |11.99
|14.53                |
|B-D                   |30       |21.59               |1120                |15.4
|18.67                |
|B-D                   |60       |26.59               |1699                |23.35
|28.32                |
|HSW Norm-Ject         |1        |4.69                |52.86               |0.727
|0.881                |
|HSW Norm-Ject         |3        |9.65                |223.8               |3.076
|3.73                 |
|HSW Norm-Ject         |5        |12.45               |372.5               |5.119
|6.209                |
|HSW Norm-Ject         |10       |15.9                |607.6               |8.349
|10.12                |
|HSW Norm-Ject         |20       |20.05               |966.2               |13.28
|16.1                 |
|HSW Norm-Ject         |30       |22.9                |1260                |17.32               |21
|
|HSW Norm-Ject         |50       |29.2                |2049                |28.16
|34.15                |
|Monoject              |1        |5.74                |79.18               |1.088
|1.319                |
|Monoject              |3        |8.941               |192.1               |2.64
|3.202                |
|Monoject              |6        |12.7                |387.6               |5.326
|6.46                 |
|Monoject              |12       |15.72               |593.9               |8.161
|9.899                |
|Monoject              |20       |20.12               |972.9               |13.37
|16.21                |
|Monoject              |35       |23.52               |1329                |18.27
|22.15                |
|Monoject              |60       |26.64               |1705                |23.44
|28.42                |
|Monoject              |140      |38                  |3470                |47.69
|57.84                |
|Terumo                |1        |4.7                 |53.09               |0.73
|0.884                |
|Terumo                |3        |8.95                |192.5               |2.646
|3.208                |
|Terumo                |5        |13                  |406.1               |5.581
|6.769                |
|Terumo                |10       |15.8                |600                 |8.244               |10
|
|Terumo                |20       |20.15               |975.8               |13.41
|16.26                |
|Terumo                |30       |23.1                |1282                |17.63
|21.37                |
|Terumo                |60       |29.7                |2120                |29.13
|35.33                |
|Poulten & Graf (Glass)|1        |6.7                 |107.8               |1.483
|1.798                |
|Poulten & Graf (Glass)|2        |8.91                |190.8               |2.622
|3.18                 |
|Poulten & Graf (Glass)|3        |9.06                |197.2               |2.711
|3.288                |
|Poulten & Graf (Glass)|5        |11.75               |331.8               |4.559
|5.53                 |
|Poulten & Graf (Glass)|10       |14.67               |517.2               |7.107
|8.62                 |
|Poulten & Graf (Glass)|20       |19.62               |925.2               |12.72
|15.42                |
|Poulten & Graf (Glass)|30       |22.69               |1237                |17.01
|20.62                |
|Poulten & Graf (Glass)|50       |26.96               |1746                |24.01
|29.11                |
|Steel Syringes        |1        |9.538               |218.6               |3.005
|3.644                |
|Steel Syringes        |3        |9.538               |218.6               |3.005
|3.644                |
|Steel Syringes        |5        |12.7                |387.6               |5.326
|6.46                 |
|Steel Syringes        |8        |9.538               |218.6               |3.005
|3.644                |
|Steel Syringes        |20       |19.13               |879.5               |12.09
|14.65                |
|Steel Syringes        |50       |28.6                |1965                |27.01
|32.76                |
## Syringe Diameters:
|Manufacturer          |Size (mL)|Inside Diameter (mm)|Maxmium Rate (mL/hr)|Minimum Rate
(μL/hr)|Maximum Rate (mL/min)|
|----------------------|---------|--------------------|--------------------|--------------------|---------------------|
|B-D                   |1        |4.699               |53.07               |0.73
|0.884                |
|B-D                   |3        |8.585               |177.1               |2.434
|2.952                |
|B-D                   |5        |11.99               |345.5               |4.748
|5.758                |
|B-D                   |10       |14.43               |500.4               |6.876
|8.341                |
|B-D                   |20       |19.05               |872.2               |11.99
|14.53                |
|B-D                   |30       |21.59               |1120                |15.4
|18.67                |
|B-D                   |60       |26.59               |1699                |23.35
|28.32                |
|HSW Norm-Ject         |1        |4.69                |52.86               |0.727
|0.881                |
|HSW Norm-Ject         |3        |9.65                |223.8               |3.076
|3.73                 |
|HSW Norm-Ject         |5        |12.45               |372.5               |5.119
|6.209                |
|HSW Norm-Ject         |10       |15.9                |607.6               |8.349
|10.12                |
|HSW Norm-Ject         |20       |20.05               |966.2               |13.28
|16.1                 |
|HSW Norm-Ject         |30       |22.9                |1260                |17.32               |21
|
|HSW Norm-Ject         |50       |29.2                |2049                |28.16
|34.15                |
|Monoject              |1        |5.74                |79.18               |1.088
|1.319                |
|Monoject              |3        |8.941               |192.1               |2.64
|3.202                |
|Monoject              |6        |12.7                |387.6               |5.326
|6.46                 |
|Monoject              |12       |15.72               |593.9               |8.161
|9.899                |
|Monoject              |20       |20.12               |972.9               |13.37
|16.21                |
|Monoject              |35       |23.52               |1329                |18.27
|22.15                |
|Monoject              |60       |26.64               |1705                |23.44
|28.42                |
|Monoject              |140      |38                  |3470                |47.69
|57.84                |
|Terumo                |1        |4.7                 |53.09               |0.73
|0.884                |
|Terumo                |3        |8.95                |192.5               |2.646
|3.208                |
|Terumo                |5        |13                  |406.1               |5.581
|6.769                |
|Terumo                |10       |15.8                |600                 |8.244               |10
|
|Terumo                |20       |20.15               |975.8               |13.41
|16.26                |
|Terumo                |30       |23.1                |1282                |17.63
|21.37                |
|Terumo                |60       |29.7                |2120                |29.13
|35.33                |
|Poulten & Graf (Glass)|1        |6.7                 |107.8               |1.483
|1.798                |
|Poulten & Graf (Glass)|2        |8.91                |190.8               |2.622
|3.18                 |
|Poulten & Graf (Glass)|3        |9.06                |197.2               |2.711
|3.288                |
|Poulten & Graf (Glass)|5        |11.75               |331.8               |4.559
|5.53                 |
|Poulten & Graf (Glass)|10       |14.67               |517.2               |7.107
|8.62                 |
|Poulten & Graf (Glass)|20       |19.62               |925.2               |12.72
|15.42                |
|Poulten & Graf (Glass)|30       |22.69               |1237                |17.01
|20.62                |
|Poulten & Graf (Glass)|50       |26.96               |1746                |24.01
|29.11                |
|Steel Syringes        |1        |9.538               |218.6               |3.005
|3.644                |
|Steel Syringes        |3        |9.538               |218.6               |3.005
|3.644                |
|Steel Syringes        |5        |12.7                |387.6               |5.326
|6.46                 |
|Steel Syringes        |8        |9.538               |218.6               |3.005
|3.644                |
|Steel Syringes        |20       |19.13               |879.5               |12.09
|14.65                |
|Steel Syringes        |50       |28.6                |1965                |27.01
|32.76                |













## Syringe Diameters:
|Manufacturer          |Size (mL)|Inside Diameter (mm)|Maxmium Rate (mL/hr)|Minimum Rate (μL/hr)|Maximum Rate (mL/min)|
|----------------------|---------|--------------------|--------------------|--------------------|---------------------|
|B-D                   |1        |4.699               |53.07               |0.73                |0.884                |
|B-D                   |3        |8.585               |177.1               |2.434               |2.952                |
|B-D                   |5        |11.99               |345.5               |4.748               |5.758                |
|B-D                   |10       |14.43               |500.4               |6.876               |8.341                |
|B-D                   |20       |19.05               |872.2               |11.99               |14.53                |
|B-D                   |30       |21.59               |1120                |15.4                |18.67                |
|B-D                   |60       |26.59               |1699                |23.35               |28.32                |
|HSW Norm-Ject         |1        |4.69                |52.86               |0.727               |0.881                |
|HSW Norm-Ject         |3        |9.65                |223.8               |3.076               |3.73                 |
|HSW Norm-Ject         |5        |12.45               |372.5               |5.119               |6.209                |
|HSW Norm-Ject         |10       |15.9                |607.6               |8.349               |10.12                |
|HSW Norm-Ject         |20       |20.05               |966.2               |13.28               |16.1                 |
|HSW Norm-Ject         |30       |22.9                |1260                |17.32               |21                   |
|HSW Norm-Ject         |50       |29.2                |2049                |28.16               |34.15                |
|Monoject              |1        |5.74                |79.18               |1.088               |1.319                |
|Monoject              |3        |8.941               |192.1               |2.64                |3.202                |
|Monoject              |6        |12.7                |387.6               |5.326               |6.46                 |
|Monoject              |12       |15.72               |593.9               |8.161               |9.899                |
|Monoject              |20       |20.12               |972.9               |13.37               |16.21                |
|Monoject              |35       |23.52               |1329                |18.27               |22.15                |
|Monoject              |60       |26.64               |1705                |23.44               |28.42                |
|Monoject              |140      |38                  |3470                |47.69               |57.84                |
|Terumo                |1        |4.7                 |53.09               |0.73                |0.884                |
|Terumo                |3        |8.95                |192.5               |2.646               |3.208                |
|Terumo                |5        |13                  |406.1               |5.581               |6.769                |
|Terumo                |10       |15.8                |600                 |8.244               |10                   |
|Terumo                |20       |20.15               |975.8               |13.41               |16.26                |
|Terumo                |30       |23.1                |1282                |17.63               |21.37                |
|Terumo                |60       |29.7                |2120                |29.13               |35.33                |
|Poulten & Graf (Glass)|1        |6.7                 |107.8               |1.483               |1.798                |
|Poulten & Graf (Glass)|2        |8.91                |190.8               |2.622               |3.18                 |
|Poulten & Graf (Glass)|3        |9.06                |197.2               |2.711               |3.288                |
|Poulten & Graf (Glass)|5        |11.75               |331.8               |4.559               |5.53                 |
|Poulten & Graf (Glass)|10       |14.67               |517.2               |7.107               |8.62                 |
|Poulten & Graf (Glass)|20       |19.62               |925.2               |12.72               |15.42                |
|Poulten & Graf (Glass)|30       |22.69               |1237                |17.01               |20.62                |
|Poulten & Graf (Glass)|50       |26.96               |1746                |24.01               |29.11                |
|Steel Syringes        |1        |9.538               |218.6               |3.005               |3.644                |
|Steel Syringes        |3        |9.538               |218.6               |3.005               |3.644                |
|Steel Syringes        |5        |12.7                |387.6               |5.326               |6.46                 |
|Steel Syringes        |8        |9.538               |218.6               |3.005               |3.644                |
|Steel Syringes        |20       |19.13               |879.5               |12.09               |14.65                |
|Steel Syringes        |50       |28.6                |1965                |27.01               |32.76                |


