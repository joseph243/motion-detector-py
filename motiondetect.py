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
intervalSeconds = 5
camera = cv2.VideoCapture(0)
sensitivity = 100.0
cameraName = "Camera 001"
savedImagePath = ""

#time settings:
initialWakeupAfterSeconds = 0
throttleSeconds = 10
runtimeSeconds =  300 #28800 #28800 = 8 hours

#email api secrets:
secrets_local_file = "~/.ssh/email.key"
email_secrets = {}

#notification settings:
notificationFrequencyMinutes = 60

def find_active_camera():
	maxRange = 20
	success = False
	for i in range(-2, maxRange):
		print("trying camera " + str(i))
		camera = cv2.VideoCapture(i)
		if (camera.isOpened()):
			print("camera found at /dev/video" + str(i))
			success = True
			break
		time.sleep(1)
	assert success, "camera must be found to proceed"

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
	saveLoc = filename + ".jpg"
	cv2.imwrite(saveLoc, inImage)
	return saveLoc

def send_notification(inImageData):
	datestr = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
	print("sending notification at " + datestr)
	username = email_secrets["username"]
	token = email_secrets["token"]
	server = email_secrets["server"]
	notifyAddress = email_secrets["sendto"]
	port = int(email_secrets["port"])
	message = MIMEMultipart()
	message['From'] = username
	message['To'] = notifyAddress
	message['Subject'] = cameraName
	message.attach(MIMEText("Motion Detected at " + datestr + ": "))
	message.attach(MIMEImage(inImageData))
	connection = smtplib.SMTP(server, port)
	connection.starttls()
	connection.login(username, token)
	connection.sendmail(username,notifyAddress, message.as_string())
	connection.quit

def compareImages(inImage1, inImage2):
	score = numpy.sum((inImage1.astype("float") - inImage2.astype("float")) ** 2)
	score /= float(inImage1.shape[0] * inImage1.shape[1] * inImage1.shape[2])
	return score > sensitivity

def main():
	read_email_secrets(secrets_local_file)
	print("startup sleeping for " + str(initialWakeupAfterSeconds) + " seconds")
	time.sleep(initialWakeupAfterSeconds)
	print("startup sleep over.  running ...")
	i = 0
	throttleRemaining = 10
	lastNotifiedTime = time.time() - (notificationFrequencyMinutes * 60)
	while i < runtimeSeconds:
		runningMessage = str(i) + "motion detector running..."
		i += intervalSeconds
		throttleRemaining -= 1
		motion = False
		mse = 0.0
		if throttleRemaining < 1:
			ret, image1 = camera.read()
			time.sleep(intervalSeconds)
			ret, image2 = camera.read()
			### mean squared error to compare frames:
			#mse = numpy.sum((image1.astype("float") - image2.astype("float")) ** 2)
			#mse /= float(image1.shape[0] * image1.shape[1] * image1.shape[2])
			###
			#motion = mse > sensitivity
			motion = compareImages(image1, image2)
		else:
			runningMessage += "(throttled) "
			motion = False
			time.sleep(intervalSeconds)
		
		print(runningMessage + str(round((runtimeSeconds - i)/60)) + " minutes remain")

		if motion:
			print("==MOTION DETECTED==")
			time.sleep(2)
			throttleRemaining = throttleSeconds

		timeSinceLastNotification = (time.time() - lastNotifiedTime)
		minutesElapsed, r = divmod(timeSinceLastNotification, 60)
		if motion:
			if minutesElapsed > notificationFrequencyMinutes:
				lastNotifiedTime = time.time()
				success, buffer = cv2.imencode('.jpg', image2)
				if (success):
					print("fake notify debug")
					#send_notification(buffer.tobytes())
			else:
				print("did not notify, only " + str(minutesElapsed) + " minutes has passed.")
		
	print("closing camera and end motion detect")
	camera.release()

if __name__ == "__main__":
	main()
