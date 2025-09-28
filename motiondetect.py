import cv2, time, numpy, smtplib, os
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
from email.mime.text import MIMEText

camera = cv2.VideoCapture(0)
cameraName = "Camera 001"

#email api secrets:
secrets_local_file = "~/.ssh/email.key"
config_local_file = "motion.config"

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
	output = {}
	with (open(inPath)) as file:
		for line in file:
			key, value = line.split(':', 1)
			output[key.strip()] = value.strip()
	assert "username" in output, "secrets file at " + secrets_local_file + " must contain username."
	assert "token" in output, "secrets file at " + secrets_local_file + " must contain token."
	assert "server" in output, "secrets file at " + secrets_local_file + " must contain server address."
	assert "sendto" in output, "secrets file at " + secrets_local_file + " must contain sendto email."
	assert "port" in output, "secrets file at " + secrets_local_file + " must contain port number."
	return output

def read_config_file(inPath):
	print("reading configuration from " + inPath)
	inPath = os.path.expanduser(inPath)
	configs = {}
	with (open(inPath)) as file:
		for line in file:
			key, value = line.split(':', 1)
			configs[key.strip()] = value.strip()
	assert "wakeUpAfterMinutes" in configs, "config file at " + inPath + " must contain wakeUpAfterMinutes."
	assert "intervalSecondsBetweenImages" in configs, "config file at " + inPath + " must contain intervalSecondsBetweenImages."
	assert "throttleSecondsAfterMotion" in configs, "config file at " + inPath + " must contain throttleSecondsAfterMotion."
	assert "sensitivityRating" in configs, "config file at " + inPath + " must contain sensitivityRating."
	assert "shutDownAfterMinutes" in configs, "config file at " + inPath + " must contain shutDownAfterMinutes."
	assert "notificationFrequencyMinutes" in configs, "config file at " + inPath + " must contain notificationFrequencyMinutes"
	return configs

def capture_and_save_image(inImage):
	timestr = datetime.now()
	filename = timestr.strftime("%Y%m%d-%H:%M:%S")
	saveLoc = filename + ".jpg"
	cv2.imwrite(saveLoc, inImage)
	return saveLoc

def send_notification(inImageData):
	email_secrets = read_email_secrets(secrets_local_file)
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

def compareImages(inImage1, inImage2, sensitivity):
	score = numpy.sum((inImage1.astype("float") - inImage2.astype("float")) ** 2)
	score /= float(inImage1.shape[0] * inImage1.shape[1] * inImage1.shape[2])
	return score > sensitivity

def cameraprimer():
	camera.read()
	time.sleep(1)
	camera.read()
	camera.read()
	camera.read()

def main():
	configs = read_config_file(config_local_file)
	notificationFrequency = timedelta(minutes=int(configs["notificationFrequencyMinutes"]))
	wakeupTime = timedelta(minutes=int(configs["wakeUpAfterMinutes"]))
	intervalTime = timedelta(seconds=int(configs["intervalSecondsBetweenImages"]))
	throttleTime = timedelta(seconds=int(configs["throttleSecondsAfterMotion"]))
	runtimeMaximum = timedelta(minutes=int(configs["shutDownAfterMinutes"]))
	sensitivity = int(configs["sensitivityRating"])

	startTime = datetime.now()
	last_notification = datetime.now()
	last_throttled = datetime.now()

	print("started at " + str(startTime))
	print("throttle time is " + str(throttleTime))
	print("runtime is " + str(runtimeMaximum))
	print("notification frequency is " + str(notificationFrequency))
	print("startup wait is " + str(wakeupTime))
	print("compare interval is " + str(intervalTime))

	while(True):
		current_time = datetime.now()
		if (runtimeMaximum < (current_time - startTime)):
			print("total runtime expired, exiting.")
			break
		if (wakeupTime > (current_time - startTime)):
			print("waking up...")
			time.sleep(60)
			continue
		if (throttleTime > (current_time - last_throttled)):
			print("throttled...")
			time.sleep(1)
			continue
		if (notificationFrequency > (current_time - last_notification)):
			print("notifications blocked...")
			time.sleep(60)
			continue
		cameraprimer()
		print("checking for motion...")
		ret, image1 = camera.read()
		time.sleep(int(configs["intervalSecondsBetweenImages"]))
		ret, image2 = camera.read()
		motion = compareImages(image1, image2, sensitivity)
		if (motion):
			print("MOTION DETECTED")
			last_throttled = current_time
			last_notification = current_time
			success, buffer = cv2.imencode('.jpg', image2)
			if (success):
					#print("==============NOTIFY SENT !")
					send_notification(buffer.tobytes())

	print("closing camera and end motion detect")
	camera.release()

if __name__ == "__main__":
	main()
