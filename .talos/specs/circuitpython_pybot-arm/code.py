# CircuitPython Test for PyBot SCARA v1p2
# Raspberry Pi Pico Implementation
#
# This file demonstrates the basic functionality of the PyBotArm library.

import time
from PyBotArm_SCARA_v1p2 import PyBotArm

# Create robot instance
myRobot = PyBotArm()

# Connect to robot
print("Connecting to robot...")
status = myRobot.connect(verbose=True)

if not status:
    print("Failed to connect to robot!")
    while True:
        pass  # Halt execution

# Set the movement speed to default
print('Set default speed')
myRobot.setSpeedDefault()
#time.sleep(0.5)
  
# Read sensor value
sensorval = myRobot.SensorRead()
sensorval = myRobot.SensorRead()
print(f'Sensor Value: {sensorval}')
 
# Initialize the robot arm
print('Initialize robot')
myRobot.Init()
#time.sleep(2)  # Wait for homing to complete

# Move to test positions
print('Move to center position')
myRobot.moveXYZ(0, 150, 10, 0)
#time.sleep(2)

print('Box 1')
myRobot.moveXYZ(-50, 150, 10, 45)
#time.sleep(2)

print('Box 2')
myRobot.moveXYZ(50, 150, 10, -45)
#time.sleep(2)

print('Box 3')
myRobot.moveXYZ(50, 100, 10, 45)
#time.sleep(2)

print('Box 4')
myRobot.moveXYZ(-50, 100, 10, -45)
#time.sleep(2)

print('Box 5')
myRobot.moveXYZ(-50, 150, 10, 45)
#time.sleep(2)

print('Center')
myRobot.moveXYZ(0, 150, 10, 0)
#time.sleep(2)

print('Lower to base')
myRobot.moveXYZ(0, 150, 0, 0)
#time.sleep(2) 

print('Unlock motors')
myRobot.Unlock()

print('Test complete!')

# Keep loop running (CircuitPython requirement)
while True:
    pass
