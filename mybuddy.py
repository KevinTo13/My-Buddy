import collections
import copy
import fnmatch
import math
import os
import re
import subprocess
import time

import pystray
import tvdb_api
from PIL import Image
from watchdog.events import PatternMatchingEventHandler
from watchdog.observers import Observer

EXIT_YES = 3
EXIT_NO = 5
CACHE = set()
DIR_CACHE = collections.deque([], maxlen=5)

def main(icon):
	icon.visible = True
	observer = None
	while icon.visible:
		if observer:
			observer.stop()
		observer = Observer()
		drive = os.getenv("SYSTEMDRIVE") + "\\"
		watchdogs = [MediaWatchDog()]
		for watchdog in watchdogs:
			observer.schedule(watchdog, path=drive, recursive=True)
		observer.start()
		print("Program Initialized")
		print("DIR CACHE:", DIR_CACHE)
		while icon.visible and not exists_data(watchdogs):
			time.sleep(1)

class MediaWatchDog(PatternMatchingEventHandler):
	patterns = ["*.mp4", "*.avi", "*.mkv", "*.flv", "*.wmv"]

	def __init__(self, size=3, data_file='userdata.txt', *args):
		PatternMatchingEventHandler.__init__(self, *args)
		self.size = size
		self.user_data_file = os.path.join(APP_DATA_PATH, data_file)
		self.event_stack = collections.deque([], maxlen=size)
		self.undo_buffer = collections.deque([], maxlen=size)

	def get_data(self):
		if len(self.event_stack) == self.size:
			data = copy.copy(self.event_stack)
			self.event_stack.clear()
			return self.process(data)
		return

	# Don't make calls on event threads
	def on_moved(self, event):
		if not event.is_directory and not event.dest_path in CACHE:
			last_path = None
			current_path = os.path.abspath(os.path.dirname(event.src_path))
			if current_path in DIR_CACHE:
				pass
			if self.event_stack:
				last_path = os.path.abspath(os.path.dirname(self.event_stack[-1].src_path))
				if last_path == current_path:
					self.event_stack.append(event)
				else:
					self.event_stack.clear()
					self.event_stack.append(event)
			else:
				self.event_stack.append(event)
			print("MediaWatchDog on_moved ocurred")
			print("Source:", event.src_path)
			print("Dest:", event.dest_path)

	def process(self, data):
		print("Data received:", data)
		target_path = os.path.abspath(os.path.dirname(data[-1].src_path))
		files = list(filter(lambda file: os.path.isfile(os.path.join(target_path, file)), os.listdir(target_path)))
		files = set(filter(lambda file: matches_pattern(self.patterns, file), files))
		print(files)
		exclusions = set([item.dest_path.split("\\")[-1] for item in data])
		files = list(files - exclusions - CACHE)
		if not files:
			return
		files.sort()
		with open(self.user_data_file, 'w+') as user_data:
			for file in files:
				user_data.write(file + "\n")
		# Prompt asking if you want to continue
		prompt = subprocess.call(('".\\assets\\rename\\rename.exe"'))
		if prompt == EXIT_NO:
			return

		files = []
		with open(self.user_data_file, 'r') as user_data:
			for line in user_data:
				files.append(line.strip())
		print("Files from prompt:", files)
		if not files:
			return
		# {newfilename:oldfilename}
		undo_data = {}
		# Path that you are working on
		size = len(files)
		count = 0
		# Loading bar prompt
		load_status = subprocess.Popen([".\\assets\\load\\load.exe"])
		time.sleep(1)
		for file in files:
			try:
				new_file_name = get_new_show_filename(file)
				new_file_path = os.path.join(target_path, new_file_name)
				old_file_path = os.path.join(target_path, file)
				os.rename(old_file_path, new_file_path)
				undo_data[new_file_path] = old_file_path
				CACHE.add(new_file_name)
			except Exception as e:
				print(e)
				print("Failed to rename", file)
				pass
			count += 1
			percentage = min(math.floor(count / size * 100), 99)
			with open(self.user_data_file, 'w+') as user_data:
				user_data.write(str(percentage))
			time.sleep(0.5)
		with open(self.user_data_file, 'w+') as user_data:
			user_data.write("99")
		time.sleep(0.5)
		with open(self.user_data_file, 'w+') as user_data:
			user_data.write("100")
		print("LOAD STATUS", load_status.poll())
		# Verify that the load window has properly terminated
		while not load_status.poll():
			time.sleep(1)
		self.undo_buffer.append(undo_data)
		# Pipe this to the prompt
		target_files = list(undo_data.keys())
		target_files.sort()
		print(target_files)
		with open(self.user_data_file, 'w+') as user_data:
			for file in target_files:
				text = file.split("\\")[-1]
				user_data.write(" " + text + "\n")
		prompt = subprocess.call(('".\\assets\\undo\\undo.exe"'))
		if prompt == EXIT_NO:
			DIR_CACHE.append(target_path)
			print("Target path cached:", target_path)
			#self.event_stack.clear()
			return True
		data = self.undo_buffer.pop()
		files_to_undo = []
		with open(self.user_data_file, 'r') as user_data:
			for line in user_data:
				files_to_undo.append(target_path + "\\" + line.strip())
		print("Files to undo:", files_to_undo)
		for key in data:
			try:
				temp = key
				if temp in files_to_undo:
					os.rename(key, undo_data[key])
					pass
			except Exception as e:
				print(e)
				pass
		#self.event_stack.clear()
		return True

class TextWatchDog(PatternMatchingEventHandler):
	patterns = ["*.txt"]

	def __init__(self, size=6, data_file='userdata.txt', *args):
		PatternMatchingEventHandler.__init__(self, *args)
		self.size = size
		self.user_data_file = os.path.join(APP_DATA_PATH, data_file)
		self.event_stack = collections.deque([], maxlen=size)
		self.undo_buffer = collections.deque([], maxlen=size)

	def get_data(self):
		if len(self.event_stack) == self.size:
			data = copy.copy(self.event_stack)
			self.event_stack.clear()
			ret = self.process(data)
			self.event_stack.clear()
			return ret
		return

	# Don't make calls on event threads
	def on_modified(self, event):
		if not event.is_directory:
			if self.event_stack:
				last_path = self.event_stack[-1].src_path
				if event.src_path == last_path:
					self.event_stack.append(event)
				else:
					self.event_stack.clear()
					self.event_stack.append(event)
			else:
				self.event_stack.append(event)
			print("TextWatchDog occurred")
			print("Source:", event.src_path)

	def process(self, data):
		print("Hmm")
		print(self.event_stack)
		return True

class Show():
	def __init__(self, name, season, episode):
		self.name = name
		self.season = season
		self.episode = episode

def matches_pattern(patterns, file):
	for pattern in patterns:
		if fnmatch.fnmatch(file, pattern):
			return True
	return False

def is_file(path, file):
	return os.path.isfile(os.path.join(path, file))

def exists_data(watchdogs):
	for watchdog in watchdogs:
		data = watchdog.get_data()
		if data:
			return True
	return False

def get_pdf_title(pdf_file_path):
	try:
		pdf_reader = PdfFileReader(open(pdf_file_path, "rb"))
		return pdf_reader.getDocumentInfo()['/Title']
	except Exception as e:
		print(e)
		pass

def get_episode_name(name, s, e):
	database = tvdb_api.Tvdb()
	data = None
	try:
		show = database[name]
		data = show[int(s)][int(e)]
	except Exception as e:
		print(e)
		Exception("Data for show {} not found".format(name))
	return data['episodename']

def replace_invalid_chars(title):
	invalids = '/\:*?"<>|'
	for char in invalids:
		title = title.replace(char, " ")
	title = ' '.join(title.split())
	return title

def extract_num(string):
	result = re.findall('[1-9][0-9]*$', string)
	if not result:
		raise Exception("Valid number not found when calling extract_num")
	return result[0]

def get_new_show_filename(filename):
	title = filename[:]
	title = title.replace(".", " ")
	title = title.replace("-", " ")
	title = title.replace(",", " ")
	results = title.split()
	results = ' '.join(results)
	season = re.findall('(?i)s[0-9]*', title)
	season = list(filter(lambda x: len(x) > len("S"), season))
	if not season:
		season = re.findall("(?i)season*[0-9]*", title)
		season = list(filter(lambda x: len(x) > len("S"), season))
		if not season:
			raise Exception("Season not found")
	episode = re.findall("(?i)e[0-9]*", title)
	episode = list(filter(lambda x: len(x) > len("E"), episode))
	if not episode:
		episode = re.findall('(?i)episode*[0-9]*', title)
		episode = list(filter(lambda x: len(x) > len("E"), episode))
		if not episode:
			raise Exception("Episode not found")
	# Assume the show name will appear before the episode name
	print("results", results)
	season_index = results.find(season[0])
	show_candidate = results[:season_index].strip()
	episode_index = results.find(episode[0])

	raw_season = season[0].strip()
	raw_episode = episode[0].strip()
	season = extract_num(raw_season)
	episode = extract_num(raw_episode)
	episode_name = get_episode_name(show_candidate, season, episode)
	episode_name = replace_invalid_chars(episode_name)
	non_garbage = filename[:episode_index + len(raw_episode)]
	file_extension = os.path.splitext(filename)[1]
	new_filename = non_garbage + "." + episode_name + file_extension
	print("Show:", show_candidate)
	print("Season:", season)
	print("Episode:", episode)
	print("Episode Name:", episode_name)
	print("Filename:", filename)
	# Remove garbage from filename (splice until episode)
	# print("Non-garbage: ", non_garbage)
	print("Old filename:", filename)
	print("New filename:", new_filename)
	return new_filename

if __name__ == "__main__":
	def icon_exit(icon):
		icon.visible = False
		icon.stop()
	def setup(icon):
		icon.visible = True

	ICON = pystray.Icon("My Buddy")
	ICON.menu = pystray.Menu(
		pystray.MenuItem("Exit", lambda: icon_exit(ICON))
		)
	ICON.icon = Image.open(".\\assets\\tray.ico")
	ICON.title = "My Buddy"
	APP_DATA_PATH = os.path.join(os.environ["APPDATA"], "MyBuddy")
	print(APP_DATA_PATH)
	if not os.path.exists(APP_DATA_PATH):
		os.mkdir(APP_DATA_PATH)
	try:
		ICON.run(main)
	except Exception as e:
		icon_exit(ICON)
