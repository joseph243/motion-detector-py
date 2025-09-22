import cv2
import time
import numpy
import smtplib
import os
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
from email.mime.text import MIMEText

#image and motion detection:
intervalSeconds = 1
camera = cv2.VideoCapture(0)
sensitivity = 100.0
cameraName = "Camera 001"
savedImagePath = ""

#time settings:
initialWakeupAfterSeconds = 300
throttleSeconds = 10
throttleRemaining = 10
runtimeSeconds = 300

#email api secrets:
secrets_local_file = "~/.ssh/email.key"
email_secrets = {}

#notification settings:
notificationFrequencyMinutes = 60
lastNotifiedTime = time.time() - (notificationFrequencyMinutes * 60)

def read_email_secrets(inPath):
	print("reading email secrets from " + inPath)
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
	return saveLoc

def send_notification(inImagePath):
	print("sending notification...")
	username = email_secrets["username"]
	token = email_secrets["token"]
	server = email_secrets["server"]
	notifyAddress = email_secrets["sendto"]
	port = int(email_secrets["port"])
	with open(inImagePath, 'rb') as file:
		img_data = file.read()
	message = MIMEMultipart()
	message['From'] = username
	message['To'] = notifyAddress
	message['Subject'] = cameraName
	message.attach(MIMEText("Motion Detected:"))
	message.attach(MIMEImage(img_data))
	connection = smtplib.SMTP(server, port)
	connection.starttls()
	connection.login(username, token)
	connection.sendmail(username,notifyAddress, message.as_string())
	connection.quit

def main():
	read_email_secrets(secrets_local_file)
	print("startup sleeping for " + str(initialWakeupAfterSeconds) + " seconds")
	time.sleep(initialWakeupAfterSeconds)
	i = 0
	while i < runtimeSeconds:
		runningMessage = "motion detector running..."
		i += 1
		throttleRemaining -= 1
		motion = False
		if throttleRemaining < 1:
			ret, image1 = camera.read()
			time.sleep(intervalSeconds)
			ret, image2 = camera.read()
			### mean squared error to compare frames:
			mse = numpy.sum((image1.astype("float") - image2.astype("float")) ** 2)
			mse /= float(image1.shape[0] * image1.shape[1] * image1.shape[2])
			###
			motion = mse > sensitivity
		else:
			runningMessage += "(throttled)"
			motion = False
			time.sleep(intervalSeconds)
		
		print(runningMessage)

		if motion:
			print("==MOTION DETECTED==")
			savedImagePath = capture_and_save_image(image2)
			throttleRemaining = throttleSeconds

		timeSinceLastNotification = (time.time() - lastNotifiedTime)
		minutesElapsed, r = divmod(timeSinceLastNotification, 60)
		if motion:
			if minutesElapsed > notificationFrequencyMinutes:
				lastNotifiedTime = time.time()
				send_notification(savedImagePath)
			else:
				print("did not notify, only " + str(minutesElapsed) + " minutes has passed.")
		
	print("closing camera and end motion detect")
	camera.release()

if __name__ == "__main__":
	main()
