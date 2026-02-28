#!/bin/bash
cd /home/pi/motion-detector-py
nohup python3 -u /home/pi/motion-detector-py/motiondetect.py > /home/pi/motion-detector-py/output.log 2>&1 &
