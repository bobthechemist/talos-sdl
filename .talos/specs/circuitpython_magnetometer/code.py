# SPDX-FileCopyrightText: 2021 ladyada for Adafruit Industries
# SPDX-License-Identifier: MIT

import time
import board
import adafruit_tlv493d
import hmc5883

i2c = board.I2C()  # uses board.SCL and board.SDA
# i2c = board.STEMMA_I2C()  # For using the built-in STEMMA QT connector on a microcontroller
tlv = adafruit_tlv493d.TLV493D(i2c)
sensor = hmc5883.HMC5883(i2c)

# Store calibration offsets
tlv_offsets = {'x': 0, 'y': 0, 'z': 0}
hmc_offsets = {'x': 0, 'y': 0, 'z': 0}


def calibrate_sensors():
    """Calibrate sensors by taking 10 measurements and calculating offsets."""
    print("Calibrating sensors...")

    # Accumulate values for TLV493D
    tlv_x_sum = 0
    tlv_y_sum = 0
    tlv_z_sum = 0

    # Accumulate values for HMC5883
    hmc_x_sum = 0
    hmc_y_sum = 0
    hmc_z_sum = 0

    # Take 10 measurements
    for i in range(10):
        # Read TLV493D
        tlv_x, tlv_y, tlv_z = tlv.magnetic
        tlv_x_sum += tlv_x
        tlv_y_sum += tlv_y
        tlv_z_sum += tlv_z

        # Read HMC5883
        hmc_x, hmc_y, hmc_z = sensor.magnetic
        hmc_x_sum += hmc_x
        hmc_y_sum += hmc_y
        hmc_z_sum += hmc_z

        # Small delay between measurements
        time.sleep(0.05)

    # Calculate average offsets
    tlv_offsets['x'] = tlv_x_sum / 10
    tlv_offsets['y'] = tlv_y_sum / 10
    tlv_offsets['z'] = tlv_z_sum / 10

    hmc_offsets['x'] = hmc_x_sum / 10
    hmc_offsets['y'] = hmc_y_sum / 10
    hmc_offsets['z'] = hmc_z_sum / 10

    print("Calibration complete:")
    print("TLV493D offsets: X={:.2f}, Y={:.2f}, Z={:.2f} uT".format(
        tlv_offsets['x'], tlv_offsets['y'], tlv_offsets['z']))
    print("HMC5883 offsets: X={:.2f}, Y={:.2f}, Z={:.2f} Gs".format(
        hmc_offsets['x'], hmc_offsets['y'], hmc_offsets['z']))


# Run calibration on startup
calibrate_sensors()

while True:
    # TLV493D with offset correction
    raw_x, raw_y, raw_z = tlv.magnetic
    corrected_x = raw_x - tlv_offsets['x']
    corrected_y = raw_y - tlv_offsets['y']
    corrected_z = raw_z - tlv_offsets['z']
    print("TLV493 X: {:.2f}, Y: {:.2f}, Z: {:.2f} uT".format(corrected_x, corrected_y, corrected_z))

    # HMC5883 with offset correction
    raw_x, raw_y, raw_z = sensor.magnetic
    corrected_x = raw_x - hmc_offsets['x']
    corrected_y = raw_y - hmc_offsets['y']
    corrected_z = raw_z - hmc_offsets['z']
    print("HMC5883 X:{:.2f}, Y:{:.2f}, Z:{:.2f}Gs".format(corrected_x, corrected_y, corrected_z))

    time.sleep(1) 
