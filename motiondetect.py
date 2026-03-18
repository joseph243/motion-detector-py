import cv2, time, numpy, smtplib, os, requests, socket, threading, queue
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
from email.mime.text import MIMEText
from mjpegStreamer import MJPEGStreamer
from multiprocessing.managers import BaseManager

camera = cv2.VideoCapture(0)
configCameraName = "DefaultCamera000"
secrets_local_file = "~/.ssh/email.key"
telegram_secrets_local_file = "~/.ssh/telegram.key"
config_local_file = "motion.config"

def get_local_ip():
	s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
	try:
		s.connect(("8.8.8.8", 80))
		return s.getsockname()[0]
	finally:
		s.close()

def read_secrets(inPath):
	print("reading secrets from " + inPath)
	inPath = os.path.expanduser(inPath)
	output = {}
	with (open(inPath)) as file:
		for line in file:
			if ":" in line:
				key, value = line.split(':', 1)
				output[key.strip()] = value.strip()
	return output

def read_config_file(inPath):
	print("reading configuration from " + inPath)
	expectedFields = [
    "wakeUpAfterMinutes",
    "intervalSecondsBetweenImages",
    "throttleSecondsAfterMotion",
    "sensitivityRating",
    "shutDownAfterMinutes",
    "notificationFrequencyMinutes",
    "notificationsAllowed",
    "notifyEmail",
    "notifyTelegram",
    "cameraName",
    "savePictures",
    "logLevel",
    "streaming",
    "finalPicture"
	]
	inPath = os.path.expanduser(inPath)
	configs = {}
	with (open(inPath)) as file:
		for line in file:
			if ":" in line:
				key, value = line.split(':', 1)
				configs[key.strip()] = value.strip()
	for field in expectedFields:
		assert field in configs, f"config file at {inPath} must contain {field}."
	return configs

def capture_and_save_image(inImage):
	timestr = datetime.now()
	filename = timestr.strftime("%Y-%m-%d-%H:%M:%S")
	saveLoc = filename + ".jpg"
	cv2.imwrite(saveLoc, inImage)
	return saveLoc

def send_telegram_message(inMessage):
	secrets = read_secrets(secrets_local_file)
	chatId = secrets["telegramchatid"]
	token = secrets["telegramtoken"]
	url = f"https://api.telegram.org/bot{token}/sendMessage"
	response = requests.post(
		url,
		data={
			"chat_id": chatId,
			"text": inMessage
		},
	)
	if not response.ok:
		log(response.text)

def send_telegram(inMessage, inImageData):
	secrets = read_secrets(secrets_local_file)
	chatId = secrets["telegramchatid"]
	token = secrets["telegramtoken"]
	url = f"https://api.telegram.org/bot{token}/sendPhoto"
	datestr = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
	caption = inMessage + " at " + datestr
	try:
		response = requests.post(
			url,
			data={
				"chat_id": chatId,
				"caption": caption
			},
			files={
				"photo": ("image.jpg", inImageData, "image/jpeg")
			}
		)
		if not response.ok:
			log(response.text)
	except:
		log("EXCEPTION when sending telegram message.")

def send_email(inImageData):
	secrets = read_secrets(secrets_local_file)
	datestr = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
	username = secrets["username"]
	token = secrets["token"]
	server = secrets["server"]
	notifyAddress = secrets["sendto"]
	port = int(secrets["port"])
	message = MIMEMultipart()
	message['From'] = username
	message['To'] = notifyAddress
	message['Subject'] = configCameraName
	message.attach(MIMEText("Motion Detected at " + datestr + ": "))
	message.attach(MIMEImage(inImageData))
	connection = smtplib.SMTP(server, port)
	connection.starttls()
	connection.login(username, token)
	connection.sendmail(username,notifyAddress, message.as_string())
	connection.quit

def compareImages(inImage1, inImage2, sensitivity):
	try:
		score = numpy.sum((inImage1.astype("float") - inImage2.astype("float")) ** 2)
		score /= float(inImage1.shape[0] * inImage1.shape[1] * inImage1.shape[2])
		return score > sensitivity
	except (AttributeError):
		log("IMAGE COMPARE ERROR, CAMERA NOT DETECTED?.")
		return False

def cameraprimer():
	camera.read()
	time.sleep(1)
	camera.read()
	camera.read()
	time.sleep(5)
	camera.read()
	camera.read()
	camera.read()

def log(inLogEntry):
	dateString = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
	print(dateString + " cameraLog: " + inLogEntry)

def encodeImageWithText(inImage, inText):
	height, *_ = inImage.shape
	buffer = 10
	position = (buffer, height-buffer)
	cv2.putText(inImage, str(inText), position, cv2.FONT_HERSHEY_DUPLEX, 1, (0,0,0), 2, cv2.LINE_AA)
	return inImage

def telegramMessageWatcher(token, authorizedUser):
	global telegramCommand
	last_update_id = 0
	while True:
		try:
			log(">>telegram polling")
			r = requests.get(
        		f"https://api.telegram.org/bot{token}/getUpdates",
        		params={
            		"timeout": 30,
					"offset": last_update_id
        		},
				timeout=35
    		)
			data = r.json()
			for update in data["result"]:
				last_update_id = update["update_id"] + 1
				message = update.get("message", {})
				chat_id = message.get("chat", {}).get("id")
				text = message.get("text")
				if str(authorizedUser) == str(chat_id):
					telegramCommand = text.lower()
		except Exception as e:
			log(">>telegram polling error" + str(e))
			time.sleep(5)

def heartbeat():
	heartbeatSeconds = 60
	nextHeartbeat = time.time() - 1
	while(True):
		if (time.time() >= nextHeartbeat):
			log("sending heartbeat")
			homebotSend.put({"name": configCameraName, "type": "camera", "time": time.time(), "message": "heartbeat"})
			nextHeartbeat = time.time() + heartbeatSeconds
		else:
			time.sleep(10)

def initializeMessageSend(key) -> queue.Queue:
	log("initialize network message send")
	PORT = 55555
	HOST = '10.0.0.235'
	class MessageManager(BaseManager):
		pass
	MessageManager.register('homebot')
	manager = MessageManager(address=(HOST, PORT), authkey=key)
	manager.connect()
	return manager.homebot()

def initializeMessageReceive(key) -> queue.Queue:
	LISTEN_TO_HOST = get_local_ip()
	PORT = 55556
	log("initialize network message receive")
	messages = queue.Queue()
	class MessageManager(BaseManager):
		pass
	MessageManager.register("homebotSays", callable=lambda: messages)
	manager = MessageManager(address=(LISTEN_TO_HOST,PORT), authkey=key)
	server = manager.get_server()
	thread = threading.Thread(target = server.serve_forever, daemon=True)
	thread.start()
	log(f"Listening for messages on {LISTEN_TO_HOST}:{PORT}")
	return messages

def main():
	global configCameraName
	global logLevel
	global homebotCommand
	global telegramCommand
	global homebotSend
	global homebotReceive
	global active
	configs = read_config_file(config_local_file)
	active = False
	logLevel = int(configs["logLevel"])
	configCameraName = configs["cameraName"]
	configNotificationsAllowed = ("True" in configs["notificationsAllowed"])
	configNotificationFrequency = timedelta(minutes=int(configs["notificationFrequencyMinutes"]))
	configWakeupTime = timedelta(minutes=int(configs["wakeUpAfterMinutes"]))
	configIntervalSeconds = int(configs["intervalSecondsBetweenImages"])
	configThrottleTime = timedelta(seconds=int(configs["throttleSecondsAfterMotion"]))
	configRuntimeMaximum = timedelta(minutes=int(configs["shutDownAfterMinutes"]))
	configSensitivity = int(configs["sensitivityRating"])
	configSavePictures = ("True" in configs["savePictures"])
	configStreaming = ("True" in configs["streaming"])
	configFinalPicture = ("True" in configs["finalPicture"])
	configEmailNotify = ("True" in configs["notifyEmail"])
	configTelegramNotify = ("True" in configs["notifyTelegram"])
	startTime = datetime.now()
	last_notification = datetime.now() - configNotificationFrequency
	last_throttled = datetime.now()

	NETWORKAUTH = read_secrets(telegram_secrets_local_file)["homebotqueuetoken"].encode('utf-8')
	homebotSend = initializeMessageSend(NETWORKAUTH)
	homebotReceive = initializeMessageReceive(NETWORKAUTH)

	print("")
	print("monitoring started at " + startTime.strftime("%Y-%m-%d %H:%M:%S"))
	print("-----------------------------------------")
	print("throttle time is      " + str(configThrottleTime))
	print("runtime is            " + str(configRuntimeMaximum))
	print("startup wait is       " + str(configWakeupTime))
	print("compare interval is   " + str(timedelta(seconds=configIntervalSeconds)))
	print("logLevel is           " + str(logLevel))
	print("-----------------------------------------")
	print("")

	if (configNotificationsAllowed):
		print("Notifications are enabled   with frequency of " + str(configNotificationFrequency))
		if (configEmailNotify):
			print("                                   email ON")
		if (configTelegramNotify):
			print("                                   telegram ON")
	else:
		print("Notifications are disabled")

	if (configFinalPicture and configNotificationsAllowed):
		print("Final picture is  enabled")
	else:
		print("Final picture is  disabled")

	if (configStreaming):
		print("Streaming is      enabled")
		streamer = MJPEGStreamer(camera, port=8080, path="/video", jpeg_quality=50)
		streamer.start()
	else:
		print("Streaming is      disabled")

	print("")

	log("starting Telegram Watcher thread.")
	t = threading.Thread(
		target=telegramMessageWatcher,
		daemon=True,
		args=(read_secrets(secrets_local_file)["telegramtoken"],read_secrets(secrets_local_file)["telegramchatid"])
	)
	t.start()

	log("starting heartbeat thread.")
	u = threading.Thread(
		target=heartbeat,
		daemon=True
	)
	u.start()

	log("initializing " + configCameraName)
	cameraprimer()
	telegramCommand = None
	homebotCommand = None
	command = None

	while(True):
		try:
			homebotCommand = homebotReceive.get_nowait()
		except queue.Empty:
			homebotCommand = None
			pass

		if telegramCommand != None:
			command = telegramCommand
			telegramCommand = None

		if homebotCommand != None:
			command = homebotCommand
			homebotCommand = None

		if not active and command == None:
			log("not active, no commands received.")
			time.sleep(10)
			continue

		##HANDLE COMMANDS##
		if command:
			command = command.lower()
			
		if command == "snapshot":
			image2 = encodeImageWithText(image2, current_time.strftime("%Y-%m-%d %H:%M:%S"))
			encodeImgSuccess, encoded = cv2.imencode('.jpg', image2)
			if not encodeImgSuccess:
				log("FAILURE ENCODING IMAGE FOR NOTIFICATION!!")
				continue
			log("sending snapshot as requested.")
			send_telegram("Snapshot Requested", encoded.tobytes())

		if command == "status":
			stateString = ""
			if active:
				stateString = "Active"
			else:
				stateString = "Inactive"
			message = "Running since " + startTime.strftime("%Y-%m-%d %H:%M:%S") + ". Last motion detected was at " + last_throttled.strftime("%Y-%m-%d %H:%M:%S") + ". \n" + "Camera is " + stateString
			log("sending telegram message: " + message)
			send_telegram_message(message)

		if command == "stop":
			message = "Stopping per request."
			log(message)
			break

		if command == "start":
			message = "Starting per request."
			log(message)
			send_telegram_message(message)
			active = True

		command = None
		##END COMMANDS##

		if not active:
			log("camera is not active.")
			time.sleep(10)
			continue

		camera.read()
		current_time = datetime.now()

		if (configThrottleTime > (current_time - last_throttled)):
			log("throttled...")
			time.sleep(1)
			continue

		notificationCooldown = configNotificationFrequency > (current_time - last_notification)

		if (logLevel > 0):
			log("checking for motion...")

		ret, image1 = camera.read()
		time.sleep(configIntervalSeconds)
		ret, image2 = camera.read()
		motion = compareImages(image1, image2, configSensitivity)
		if motion:
			log("MOTION DETECTED")
			last_throttled = current_time
			image2 = encodeImageWithText(image2, current_time.strftime("%Y-%m-%d %H:%M:%S"))
			encodeImgSuccess, encoded = cv2.imencode('.jpg', image2)
			if not encodeImgSuccess:
				log("FAILURE ENCODING IMAGE FOR NOTIFICATION!!")
				continue
			if configSavePictures:
				log("image saved.")
				capture_and_save_image(image2)
			if not configSavePictures:
				log("saved images are disabled.")
			if (configNotificationsAllowed and notificationCooldown):
				log("notifications are allowed, but on cooldown.")
			if not configNotificationsAllowed:
				log("notifications are disabled.")
			if (configNotificationsAllowed and not notificationCooldown):
				log("notification sending...")
				last_notification = current_time
				if (configEmailNotify):
					log("...via email")
					send_email(encoded.tobytes())
				if (configTelegramNotify):
					log("...via telegram")
					send_telegram("Motion Detected", encoded.tobytes())

	log("monitoring stopped.  checking for final photo then shutting down.")
	if (configFinalPicture and configNotificationsAllowed and configEmailNotify):
		ret, image = camera.read()
		ret, encoded = cv2.imencode('.jpg', image)
		send_email(encoded.tobytes())
	if (configFinalPicture and configNotificationsAllowed and configTelegramNotify):
		ret, image = camera.read()
		ret, encoded = cv2.imencode('.jpg', image)
		send_telegram("Final Photo", encoded.tobytes())

	exitMessage = "shutting down " + configCameraName
	log(exitMessage)
	send_telegram_message(exitMessage)
	camera.release()

if __name__ == "__main__":
	main()
