# Instrument design: AS7341 Colorimeter (colorimeter)

## 1. Instrument Overview

* Primary purpose: to measure light at a variety of wavelengths
* primary actions: read light channels, control background light, control gain
* periodic telemetry data:  send led status
* critical failure conditions: no communication with device

## 2. Hardware Configuration (`AS7431_CONFIG`)

``` python
AS7341_CONFIG = {
    "pins": {
        # SCL and SDA pins
        "SCL": board.SCL
        "SDA": board.SDA
    }
    # Default gain setting for sensors
    "default_gain": 8,
    # Default current for LED source
    "default_intensity": 4,
}
```

## 3. Command interface

- read
    - description: returns reading from a channel
    - arguments: channel (color)
    - success condition: Returns `SUCCESS` message with data
    - guard conditions: None
- read_all
    - description: returns an array of all channel readings
    - arguments: none
    - success condition: Returns `SUCCESS` message with data
    - guard conditions: None
- read_gain
    - description: reads the current gain setting
    - arguments: none
    - success condition: Returns `SUCCESS` message with gain value
    - guard conditions: None
- set_gain
    - description: reads the current gain setting
    - arguments: new gain value select from [0.5 1 2 4 8 16 32 64 128 256 512]
    - success condition: Returns `SUCCESS` message with gain value
    - guard conditions: None
- led
    - description: turns the source led on or off
    - arguments: boolean 
    - success condition: Returns `SUCCESS` and current LED status
    - guard conditions: None
- led_intensity
    - description: adjusts the led intensity (default is 4)
    - argumenst: intenger from 1 to 10
    - success condition: Returns `SUCCESS` and current led intensity

## 4. States

- Initialize
    - purpose: establish I2C communication, set default gain, set default led_current
    - entry actions: initialize sensor, set default values
    - internal actions: none
    - exit events:
        - success: no errors raised. Trigger transition to Idle
        - failure: an exception is raised. Trigger error message and transition to Error
    - exit actions: none
- Collecting
    - purpose: a placeholder state for data collection routines such as time series
    - entry actions: to be determined
    - internal actions: to be determined
    - exit events: to be determined
    - exit actions: to be determined