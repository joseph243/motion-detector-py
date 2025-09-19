import cv2
import time
import numpy
from datetime import datetime

print("begin motion detect")
intervalSeconds = 1
camera = cv2.VideoCapture(0)
sensitivity = 100.0
throttleSeconds = 10
throttleRemaining = 0
runtimeSeconds = 20
i = 0

def capture_and_save_image(inImage):
	timestr = datetime.now()
	filename = timestr.strftime("%Y%m%d-%H:%M:%S")
	saveLoc = "./data/" + filename + ".jpg"
	cv2.imwrite(saveLoc, inImage)

def send_notification(inImage):
	print("sending notification...")

while i < runtimeSeconds:
	print("motion detector running...")
	i += 1
	throttleRemaining -= 1
	motion = False
	if throttleRemaining < 1:
		ret, image1 = camera.read()
		time.sleep(intervalSeconds)
		ret, image2 = camera.read()
		### mean square something to compare frames:
		mse = numpy.sum((image1.astype("float") - image2.astype("float")) ** 2)
		mse /= float(image1.shape[0] * image1.shape[1] * image1.shape[2])
		###
		motion = mse > sensitivity
	else:
		time.sleep(intervalSeconds)

	if motion and throttleRemaining < 1:
		print("==MOTION DETECTED==")
		capture_and_save_image(image2)
		throttleRemaining = throttleSeconds

print("closing camera and end motion detect")
camera.release()

