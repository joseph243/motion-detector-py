import time, os, requests, socket, threading
from datetime import datetime, timedelta
from multiprocessing.managers import BaseManager

configDeviceName = "DefaultCamera000"

#api secrets:
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
    "name",
    "logLevel"
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

def log(inLogEntry):
	dateString = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
	print(dateString + " cameraLog: " + inLogEntry)

def telegramMessageWatcher(token, authorizedUser):
	global telegram_command
	telegram_command = None
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
					telegram_command = text.lower()
		except Exception as e:
			log(">>telegram polling error" + str(e))
			time.sleep(5)

def main():
	configs = read_config_file(config_local_file)
	global configDeviceName
	global logLevel
	global telegram_command
	telegram_command = None
	logLevel = int(configs["logLevel"])
	configDeviceName = configs["name"]
	startTime = datetime.now()
	heartbeatSeconds = 60

	## connection to homebot ##
	AUTH = read_secrets(telegram_secrets_local_file)["homebotqueuetoken"]
	PORT = 55555
	HOST = "10.0.0.235"
	print("debugs:  host=" + HOST + ", AUTH= " + AUTH)
	class HomebotManager(BaseManager):
		pass
	HomebotManager.register('homebot')
	manager = HomebotManager(address=(HOST, PORT), authkey=AUTH.encode('utf-8'))
	manager.connect()
	q = manager.homebot()
	## end homebot setup ##

	print("")
	print("-----------------------------------------")
	print("device started at     " + startTime.strftime("%Y-%m-%d %H:%M:%S"))
	print("logLevel is           " + str(logLevel))
	print("-----------------------------------------")
	print("")

	##print("starting Telegram Watcher thread.")
	##t = threading.Thread(
	##	target=telegramMessageWatcher,
	##	daemon=True,
	##	args=(read_secrets(secrets_local_file)["telegramtoken"],read_secrets(secrets_local_file)["telegramchatid"])
	##)
	## DISABLE TELEGRAM FOR NOW t.start()

	print("initializing " + configDeviceName)
	nextHeartbeat = time.time() - 1

	while(True):
		time.sleep(5)
		current_time = datetime.now()
		if (time.time() >= nextHeartbeat):
			log("sending heartbeat")
			q.put({"name": configDeviceName, "type": "camera", "time": startTime, "message": "heartbeat"})
			nextHeartbeat = time.time() + heartbeatSeconds
		if telegram_command == "status":
			message = "Hello!  Device is active since " + startTime.strftime("%Y-%m-%d %H:%M:%S") + "."
			log("sending telegram message: " + message)
			send_telegram_message(message)
			telegram_command = None
		if telegram_command == "stop":
			message = "Stopping per telegram request."
			log(message)
			break;

	exitMessage = "shutting down " + configDeviceName
	log(exitMessage)
	send_telegram_message(exitMessage)

if __name__ == "__main__":
	main()
