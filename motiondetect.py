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
    "intervalSecondsBetweenImages",
    "sensitivityRating",
    "notificationFrequencyMinutes",
    "notificationsAllowed",
    "notifyTelegram",
    "cameraName",
    "savePictures",
    "logLevel",
    "streaming",
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
	url = f"https://api.telegram.org/bot{secretTelegramToken}/sendMessage"
	response = requests.post(
		url,
		data={
			"chat_id": secretTelegramChatId,
			"text": inMessage
		},
	)
	if not response.ok:
		log(response.text)

def send_telegram(inMessage, inImageData):
	url = f"https://api.telegram.org/bot{secretTelegramToken}/sendPhoto"
	datestr = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
	caption = inMessage + " at " + datestr
	try:
		response = requests.post(
			url,
			data={
				"chat_id": secretTelegramChatId,
				"caption": caption
			},
			files={
				"photo": ("image.jpg", inImageData, "image/jpeg")
			}
		)
		if not response.ok:
			log(response.text)
	except Exception as e:
		log("EXCEPTION when sending telegram message:")
		log(str(e))

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
	cv2.putText(inImage, str(inText), position, cv2.FONT_HERSHEY_DUPLEX, 1, (0,0,255), 2, cv2.LINE_AA)
	return inImage

def telegramMessageWatcher(token, authorizedUser):
	global telegramCommand
	last_update_id = 0
	session = requests.Session()
	while True:
		try:
			log(">>telegram polling")
			r = session.get(
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
		time.sleep(1)

def heartbeat():
	heartbeatSeconds = 60
	nextHeartbeat = time.time() - 1
	while(True):
		if (time.time() >= nextHeartbeat):
			log("sending heartbeat")
			homebotSend.put({"ip": myip, "name": configCameraName, "type": "camera", "time": time.time(), "message": "heartbeat"})
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
	global myip
	global secretTelegramChatId
	global secretTelegramToken
	secrets = read_secrets(secrets_local_file)
	secretTelegramChatId = secrets["telegramchatid"]
	secretTelegramToken = secrets["telegramtoken"]
	NETWORKAUTH = read_secrets(telegram_secrets_local_file)["homebotqueuetoken"].encode('utf-8')

	myip = get_local_ip()
	configs = read_config_file(config_local_file)
	active = False
	logLevel = int(configs["logLevel"])
	configCameraName = configs["cameraName"]
	configNotificationsAllowed = ("True" in configs["notificationsAllowed"])
	configFrequency = timedelta(minutes=int(configs["notificationFrequencyMinutes"]))
	configIntervalSeconds = int(configs["intervalSecondsBetweenImages"])
	configSensitivity = int(configs["sensitivityRating"])
	configSavePictures = ("True" in configs["savePictures"])
	configStreaming = ("True" in configs["streaming"])
	configTelegramNotify = ("True" in configs["notifyTelegram"])
	startTime = datetime.now()
	last_motion = startTime

	homebotSend = initializeMessageSend(NETWORKAUTH)
	homebotReceive = initializeMessageReceive(NETWORKAUTH)

	print("")
	print("monitoring started at " + startTime.strftime("%Y-%m-%d %H:%M:%S"))
	print("-----------------------------------------")
	print("frequency is          " + str(configFrequency))
	print("compare interval is   " + str(timedelta(seconds=configIntervalSeconds)))
	print("logLevel is           " + str(logLevel))

	if (configNotificationsAllowed):
		print("Notifications are enabled")
	else:
		print("Notifications are disabled")

	if (configStreaming):
		print("Streaming is      enabled")
		streamer = MJPEGStreamer(camera, port=8080, path="/video", jpeg_quality=50)
		streamer.start()
	else:
		print("Streaming is      disabled")

	print("-----------------------------------------")
	print("")

	log("starting Telegram Watcher thread.")
	t = threading.Thread(
		target=telegramMessageWatcher,
		daemon=True,
		args=(secretTelegramToken,secretTelegramChatId)
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
	cooldown = True

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
			command, _, param = command.partition(" ")
			if command == "snapshot":
				cameraprimer()
				ret, snapshotimage = camera.read()
				snapshotimage = encodeImageWithText(snapshotimage, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
				encodeImgSuccess, encoded = cv2.imencode('.jpg', snapshotimage)
				if not encodeImgSuccess:
					log("FAILURE ENCODING IMAGE FOR NOTIFICATION!!")
					continue
				log("sending snapshot as requested.")
				send_telegram("Snapshot Requested", encoded.tobytes())
			elif command == "status":
				stateStr = "Active" if active else "Not Active"
				notifyStr = "enabled" if configNotificationsAllowed else "disabled"
				motionStr = str(configIntervalSeconds)
				streamStr = "Active" if configStreaming else "Not Active"
				onCoolDownStr = "On Cooldown" if cooldown else "Active"
				message = (
					"Running since " + startTime.strftime("%Y-%m-%d %H:%M:%S") + ". \n" +
					"Camera is " + stateStr + ". \n" +
					"Motion detection is " + onCoolDownStr + ". \n" +
					"Last motion at " + last_motion.strftime("%Y-%m-%d %H:%M:%S") + ". \n" +
					"Notifications are " + notifyStr + ". \n" +
					"Motion Interval is " + motionStr + " seconds. \n" +
					"Streaming is " + streamStr + ". \n" +
					"Alert frequency is " + str(configFrequency)
					)
				log("sending telegram message: " + message)
				send_telegram_message(message)
			elif command == "stop":
				message = "Stopping per request."
				log(message)
				break
			elif command == "frequency":
				if param:
					try:
						param = int(param)
						configFrequency = timedelta(minutes=int(param))
						message = "Adjusting message frequency to " + str(param) + " minutes."
					except ValueError:
						message = "You cannot set message frequency to the value " + str(param) + ". It must be a number."
				else:
					message = "This command expects a number, in minutes, to set message frequency to."
					log(message)
				send_telegram_message(message)
			elif command == "start":
				message = "Starting per request."
				log(message)
				send_telegram_message(message)
				active = True
			elif command == "sleep":
				message = "Sleeping camera per request."
				log(message)
				send_telegram_message(message)
				active = False
			else:
				message = "Unknown command " + command
				log(message)
				send_telegram_message(message)
		
		command = None
		##END COMMANDS##

		if not active:
			time.sleep(10)
			continue

		current_time = datetime.now()
		cooldown = configFrequency > (current_time - last_motion)

		if (cooldown):
			log("on cooldown...")
			time.sleep(5)
			continue

		camera.read()

		if (logLevel > 0):
			log("checking for motion...")

		ret, image1 = camera.read()
		time.sleep(configIntervalSeconds)
		ret, image2 = camera.read()
		motion = compareImages(image1, image2, configSensitivity)
		if motion:
			log("MOTION DETECTED")
			last_motion = current_time
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
			if not configNotificationsAllowed:
				log("notifications are disabled.")
			if (configNotificationsAllowed):
				log("notification sending...")
				if (configTelegramNotify):
					log("...via telegram")
					send_telegram("Motion Detected", encoded.tobytes())
	##END LOOP##

	exitMessage = "shutting down " + configCameraName
	log(exitMessage)
	send_telegram_message(exitMessage)
	camera.release()

if __name__ == "__main__":
	main()
