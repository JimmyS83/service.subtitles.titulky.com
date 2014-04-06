# -*- coding: utf-8 -*- 

from utilities import log, file_size_and_hash, CaptchaInputWindow
import urllib, re, os, xbmc, xbmcgui
import urllib2, cookielib
import HTMLParser
import time,calendar

class TitulkyClient(object):

	def __init__(self,addon):
		self.server_url = 'http://www.titulky.com'
		self.addon = addon

		opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(cookielib.LWPCookieJar()))
		opener.addheaders = [('User-agent', 'Mozilla/5.0 (Windows; U; Windows NT 6.1; en-US; rv:1.9.2.3) Gecko/20100401 Firefox/3.6.3 ( .NET CLR 3.5.30729)')]
		urllib2.install_opener(opener)

	def download(self,sub_id):

		dest_dir = os.path.join(xbmc.translatePath(self.addon.getAddonInfo('profile').decode("utf-8")), 'temp')
		dest = os.path.join(dest_dir, "download.zip")

		content = self.get_subtitle_download_page_content(sub_id)
		control_img = self.get_control_image(content)
		if not control_img == None:
			log(__name__,'Found control image :(, asking user for input')
			log(__name__,'Download control image')
			captcha_contect = self.get_file(control_img)
			captcha_file = os.path.join(dest_dir, str(calendar.timegm(time.gmtime())) + "-captcha.img")
			img_file = open(captcha_file,'wb')
			img_file.write(captcha_contect)
			img_file.close()

			solver = CaptchaInputWindow(captcha = captcha_file)
			solution = solver.get()
			if solution:
				log(__name__,'Solution provided: %s' % solution)
				content = self.get_subtitle_download_page_content(sub_id, solution)
				control_img = self.get_control_image(content)
				if not control_img == None:
					log(__name__,'Invalid control text')
					xbmc.executebuiltin("XBMC.Notification(%s,%s,1000,%s)" % (
						self.addon.getAddonInfo('name'),
						"Invalid control text",
						os.path.join(xbmc.translatePath(self.addon.getAddonInfo('path')).decode("utf-8"),'icon.png')
					))
					return None
				log(__name__,'Control image OK')
			else:
				log(__name__,'Dialog was canceled')
				log(__name__,'Control text not confirmed, returning in error')
				return None

		wait_time = self.get_wait_time(content)

		link = self.get_final_download_link(content)
		log(__name__,'Got the link, wait %i seconds before download' % (wait_time))
		for i in range(wait_time + 1):
			xbmc.executebuiltin("XBMC.Notification(%s,%s,1000,%s)" % (
				self.addon.getAddonInfo('name'),
				'Download will start in %i seconds' % (wait_time - i),
				os.path.join(xbmc.translatePath(self.addon.getAddonInfo('path')).decode("utf-8"),'icon.png')
			))
			time.sleep(1)

		log(__name__,'Downloading subtitle zip from %s' % link)

		# DOWNLOAD FILE
		subtitles_data = self.get_file(link)

		log(__name__,'Saving to file %s' % dest)
		zip_file = open(dest,'wb')
		zip_file.write(subtitles_data)
		zip_file.close()

		return dest

	def get_file(self,link):
		req = urllib2.Request(link)
		req = self.add_cookies_into_header(req)
		response = urllib2.urlopen(req)

		if response.headers.get('Set-Cookie'):
			phpsessid = re.search('PHPSESSID=(\S+);', response.headers.get('Set-Cookie'), re.IGNORECASE | re.DOTALL)
			if phpsessid:
				log(__name__, "Storing PHPSessionID")
				self.cookies['PHPSESSID'] = phpsessid.group(1)

		data = response.read()
		return data

	def get_wait_time(self,content):
		for matches in re.finditer('CountDown\((\d+)\)', content, re.IGNORECASE | re.DOTALL):
			return int(matches.group(1))

	def get_final_download_link(self,content):
		for matches in re.finditer('<a.+id=\"downlink\" href="([^\"]+)\"', content, re.IGNORECASE | re.DOTALL):
			return self.server_url + str(matches.group(1))

	def get_control_image(self,content):
		for matches in re.finditer('\.\/(captcha\/captcha\.php)', content, re.IGNORECASE | re.DOTALL):
			return self.server_url + '/' + str(matches.group(1))
		return None

	def get_subtitle_download_page_content(self, subs_id, code = None):
		if code == None:
			url = self.server_url + '/idown.php?' + urllib.urlencode({
					'R':str(calendar.timegm(time.gmtime())),
					'titulky':subs_id,
					'histstamp':'',
					'zip':'z'})
			log(__name__,'Opening %s' % (url))
			req = urllib2.Request(url)

		else:
			url = self.server_url+'/idown.php'
			post_data = {
				'downkod':code,
				'titulky':subs_id,
				'zip':'z',
				'securedown':'2',
				'histstamp':''
			}
			log(__name__,'Opening %s POST:%s' % (url,str(post_data)))
			req = urllib2.Request(url,urllib.urlencode(post_data))

		req = self.add_cookies_into_header(req)
		response = urllib2.urlopen(req)
		content = response.read()
		log(__name__,'Opening done')
		response.close()
		return content
	
	def search(self,item):
		if not ((item['tvshow'] == None) or (item['tvshow'] == '')):
			title = "%s S%02dE%02d" % (item['tvshow'], int(item['season']), int(item['episode'])) # Searching TV Show
		else:
			title = item['title'] # Searching movie

		log(__name__, "Search pattern: " + title)

		found_subtitles = self.search_subtitle(title)
		log(__name__, "Parsed subtitles: %s" % found_subtitles )

		if found_subtitles.__len__() == 0:
			log(__name__, "Subtitles not found")
			return None
			
		file_size, file_hash = file_size_and_hash(item['file_original_path'], item['rar'])
		if not (file_size == -1): file_size = round(float(file_size)/(1024*1024),2)
		log(__name__, "File size: " + str(file_size))

		max_down_count = self.detect_max_download_stats(found_subtitles)

		result_subtitles = []
		for found_subtitle in found_subtitles:

			print_out_filename = (found_subtitle['version'], found_subtitle['title'])[found_subtitle['version'] == '']
			result_subtitles.append({ 
				'filename': HTMLParser.HTMLParser().unescape(print_out_filename + " by " + found_subtitle['author']),
				'id': found_subtitle['id'],
				'lang': found_subtitle['lang'],
	 			'rating': str(found_subtitle['down_count']*5/max_down_count),
				'sync': (found_subtitle['size'] == file_size),
				'lang_flag': xbmc.convertLanguage(found_subtitle['lang'],xbmc.ISO_639_1),
			})

		log(__name__,"Search RESULT")
		log(__name__,result_subtitles)
		return result_subtitles

	def detect_max_download_stats(self, subtitle_list):
		max_down_count = 0
		for subtitle in subtitle_list:
			if max_down_count < subtitle['down_count']:
				max_down_count = subtitle['down_count']

		log(__name__,"Max download count: " + str(max_down_count))
		return max_down_count


	def search_subtitle(self, title):
		url = self.server_url + '/index.php?' + urllib.urlencode({'Fulltext': title ,'FindUser':''})
		log(__name__, "Opening: %s" % url)

		req = urllib2.Request(url)
		response = urllib2.urlopen(req)
		content = response.read()
		response.close()

		log(__name__,'Parsing result page')

		subtitles = []
		for row in re.finditer('<tr class=\"r(.+?)</tr>', content, re.IGNORECASE | re.DOTALL):
			subtitle = {}
			subtitle['id'] = re.search('[^<]+<td[^<]+<a href=\"[\w-]+-(?P<data>\d+).htm\"',row.group(1),re.IGNORECASE | re.DOTALL ).group('data')
			subtitle['title'] = re.search('[^<]+<td[^<]+<a[^>]+>(<div[^>]+>)?(?P<data>[^<]+)',row.group(1),re.IGNORECASE | re.DOTALL ).group('data')
			try:
				subtitle['version'] = re.search('((.+?)</td>)[^>]+>[^<]*<a(.+?)title=\"(?P<data>[^\"]+)',row.group(1),re.IGNORECASE | re.DOTALL ).group('data')
			except:
				subtitle['version'] = None
			subtitle['season_and_episode'] = re.search('((.+?)</td>){2}[^>]+>(?P<data>[^<]+)',row.group(1),re.IGNORECASE | re.DOTALL ).group('data')
			subtitle['year'] = re.search('((.+?)</td>){3}[^>]+>(?P<data>[^<]+)',row.group(1),re.IGNORECASE | re.DOTALL ).group('data')
			subtitle['down_count'] = int(re.search('((.+?)</td>){4}[^>]+>(?P<data>[^<]+)',row.group(1),re.IGNORECASE | re.DOTALL ).group('data'))
			subtitle['lang'] = re.search('((.+?)</td>){5}[^>]+><img alt=\"(?P<data>\w{2})\"',row.group(1),re.IGNORECASE | re.DOTALL ).group('data')
			if subtitle['lang'] == "CZ": subtitle['lang'] = "Czech"
			if subtitle['lang'] == "SK": subtitle['lang'] = "Slovak"
			subtitle['num_of_dics'] = re.search('((.+?)</td>){6}[^>]+>(?P<data>[^<]+)',row.group(1),re.IGNORECASE | re.DOTALL ).group('data')
			try:
				subtitle['size'] = float(re.search('((.+?)</td>){7}[^>]+>(?P<data>[\d\.]+)',row.group(1),re.IGNORECASE | re.DOTALL ).group('data'))
			except:
				subtitle['size'] = None
			subtitle['author'] = re.search('((.+?)</td>){8}[^>]+>[^>]+<a href[^>]+>(?P<data>[^<]+)',row.group(1),re.IGNORECASE | re.DOTALL | re.MULTILINE ).group('data').strip()
			subtitles.append(subtitle)

		return subtitles

	def login(self,username,password):
		log(__name__,'Logging in to Titulky.com')
		if (username == '' or username == None): return False
		login_postdata = urllib.urlencode({'Login': username, 'Password': password, 'foreverlog': '1','Detail2':''} )
		request = urllib2.Request(self.server_url + '/index.php',login_postdata)
		response = urllib2.urlopen(request)
		log(__name__,'Got response')
		if response.read().find('BadLogin')>-1: return False

		log(__name__,'Storing Cookies')
		self.cookies = {}
		self.cookies['CRC'] = re.search('CRC=(\S+);', response.headers.get('Set-Cookie'), re.IGNORECASE | re.DOTALL).group(1)
		self.cookies['LogonLogin'] = re.search('LogonLogin=(\S+);', response.headers.get('Set-Cookie'), re.IGNORECASE | re.DOTALL).group(1)
		self.cookies['LogonId'] = re.search('LogonId=(\S+);', response.headers.get('Set-Cookie'), re.IGNORECASE | re.DOTALL).group(1)

		return True

	def add_cookies_into_header(self,request):
		cookies_string = "LogonLogin=" + self.cookies['LogonLogin'] + "; "
		cookies_string += "LogonId=" + self.cookies['LogonId'] + "; "
		cookies_string += "CRC=" + self.cookies['CRC']
		if 'PHPSESSID' in self.cookies:
			cookies_string += "; PHPSESSID=" + self.cookies['PHPSESSID']
		request.add_header('Cookie',cookies_string)
		log(__name__, "Add Cookies: %s" % cookies_string)
		return request

