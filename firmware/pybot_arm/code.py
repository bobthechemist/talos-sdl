# type: ignore
# code.py for PyBot Arm SCARA v1p2
from firmware.pybot_arm import machine
from time import sleep

# Use numerical value to avoid having to do an import
#  DEBUG:10, INFO: 20, ...
machine.log.setLevel(10)
machine.run()
while True:
    machine.update()
    sleep(0.005)
