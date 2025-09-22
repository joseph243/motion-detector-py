import cv2
import time
import numpy
import smtplib
import os
from datetime import datetime

intervalSeconds = 1
camera = cv2.VideoCapture(0)
sensitivity = 100.0
throttleSeconds = 10
throttleRemaining = 0
runtimeSeconds = 0
secrets_local_file = "~/.ssh/email.key"
email_secrets = {}

def read_email_secrets(inPath):
	print("reading email secrets" + inPath)
	inPath = os.path.expanduser(inPath)
	with (open(inPath)) as file:
		for line in file:
			key, value = line.split(':', 1)
			email_secrets[key.strip()] = value.strip()
	assert "username" in email_secrets, "secrets file at " + secrets_local_file + " must contain username."
	assert "token" in email_secrets, "secrets file at " + secrets_local_file + " must contain token."
	assert "server" in email_secrets, "secrets file at " + secrets_local_file + " must contain server address."
	assert "sendto" in email_secrets, "secrets file at " + secrets_local_file + " must contain sendto email."
	assert "port" in email_secrets, "secrets file at " + secrets_local_file + " must contain port number."

def capture_and_save_image(inImage):
	timestr = datetime.now()
	filename = timestr.strftime("%Y%m%d-%H:%M:%S")
	saveLoc = "./data/" + filename + ".jpg"
	cv2.imwrite(saveLoc, inImage)

def send_notification(inImage):
	print("sending notification...")
	username = email_secrets["username"]
	token = email_secrets["token"]
	server = email_secrets["server"]
	notifyAddress = email_secrets["sendto"]
	port = int(email_secrets["port"])
	
	connection = smtplib.SMTP(server, port)
	connection.starttls()
	connection.login(username, token)
	connection.sendmail(username,notifyAddress,"Motion-Detect")
	connection.quit

read_email_secrets(secrets_local_file)

i = 0
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

while True:
	print("testing")
	print(time.time())