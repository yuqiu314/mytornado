# -*- coding: utf-8 -*-

import hashlib
import requests
import time
import json
import cgi
from StringIO import StringIO
from xml.dom import minidom, Node

import weglobal

class NeedParamError(Exception):
	"""
	构造参数提供不全异常
	"""
	pass


class ParseError(Exception):
	"""
	解析微信服务器数据异常
	"""
	pass


class NeedParseError(Exception):
	"""
	尚未解析微信服务器请求数据异常
	"""
	pass


class OfficialAPIError(Exception):
	"""
	微信官方API请求出错异常
	"""
	pass


class UnOfficialAPIError(Exception):
	"""
	微信非官方API请求出错异常
	"""
	pass


class NeedLoginError(UnOfficialAPIError):
	"""
	微信非官方API请求出错异常 - 需要登录
	"""
	pass


class LoginError(UnOfficialAPIError):
	"""
	微信非官方API请求出错异常 - 登录出错
	"""
	pass


class LoginVerifyCodeError(LoginError):
	"""
	微信非官方API请求出错异常 - 登录出错 - 验证码错误
	"""
	pass

MESSAGE_TYPES = {}


def handle_for_type(type):
	def register(f):
		MESSAGE_TYPES[type] = f
		return f
	return register


class WechatMessage(object):
	def __init__(self, message):
		self.id = int(message.pop('MsgId', 0))
		self.target = message.pop('ToUserName', None)
		self.source = message.pop('FromUserName', None)
		self.time = int(message.pop('CreateTime', 0))
		self.__dict__.update(message)


@handle_for_type('text')
class TextMessage(WechatMessage):
	def __init__(self, message):
		self.content = message.pop('Content', '')
		super(TextMessage, self).__init__(message)


@handle_for_type('image')
class ImageMessage(WechatMessage):
	def __init__(self, message):
		try:
			self.picurl = message.pop('PicUrl')
			self.media_id = message.pop('MediaId')
		except KeyError:
			raise ParseError()
		super(ImageMessage, self).__init__(message)


@handle_for_type('video')
class VideoMessage(WechatMessage):
	def __init__(self, message):
		try:
			self.media_id = message.pop('MediaId')
			self.thumb_media_id = message.pop('ThumbMediaId')
		except KeyError:
			raise ParseError()
		super(VideoMessage, self).__init__(message)


@handle_for_type('shortvideo')
class ShortVideoMessage(WechatMessage):
	def __init__(self, message):
		try:
			self.media_id = message.pop('MediaId')
			self.thumb_media_id = message.pop('ThumbMediaId')
		except KeyError:
			raise ParseError()
		super(ShortVideoMessage, self).__init__(message)


@handle_for_type('location')
class LocationMessage(WechatMessage):
	def __init__(self, message):
		try:
			location_x = message.pop('Location_X')
			location_y = message.pop('Location_Y')
			self.location = (float(location_x), float(location_y))
			self.scale = int(message.pop('Scale'))
			self.label = message.pop('Label')
		except KeyError:
			raise ParseError()
		super(LocationMessage, self).__init__(message)


@handle_for_type('link')
class LinkMessage(WechatMessage):
	def __init__(self, message):
		try:
			self.title = message.pop('Title')
			self.description = message.pop('Description')
			self.url = message.pop('Url')
		except KeyError:
			raise ParseError()
		super(LinkMessage, self).__init__(message)


@handle_for_type('event')
class EventMessage(WechatMessage):
	def __init__(self, message):
		message.pop('type')
		try:
			self.type = message.pop('Event').lower()
			if self.type == 'subscribe' or self.type == 'scan':
				self.key = message.pop('EventKey', None)
				self.ticket = message.pop('Ticket', None)
			elif self.type in ['click', 'view', 'scancode_push', 'scancode_waitmsg',
							   'pic_sysphoto', 'pic_photo_or_album', 'pic_weixin', 'location_select']:
				self.key = message.pop('EventKey')
			elif self.type == 'location':
				self.latitude = float(message.pop('Latitude'))
				self.longitude = float(message.pop('Longitude'))
				self.precision = float(message.pop('Precision'))
			elif self.type == 'templatesendjobfinish':
				self.status = message.pop('Status')
		except KeyError:
			raise ParseError()
		super(EventMessage, self).__init__(message)


@handle_for_type('voice')
class VoiceMessage(WechatMessage):
	def __init__(self, message):
		try:
			self.media_id = message.pop('MediaId')
			self.format = message.pop('Format')
			self.recognition = message.pop('Recognition', None)
		except KeyError:
			raise ParseError()
		super(VoiceMessage, self).__init__(message)


class UnknownMessage(WechatMessage):
	def __init__(self, message):
		self.type = 'unknown'
		super(UnknownMessage, self).__init__(message)

class WechatReply(object):
	def __init__(self, message=None, **kwargs):
		if 'source' not in kwargs and isinstance(message, WechatMessage):
			kwargs['source'] = message.target
		if 'target' not in kwargs and isinstance(message, WechatMessage):
			kwargs['target'] = message.source
		if 'time' not in kwargs:
			kwargs['time'] = int(time.time())

		self._args = dict()
		for k, v in kwargs.items():
			self._args[k] = v

	def render(self):
		raise NotImplementedError()


class TextReply(WechatReply):
	"""
	回复文字消息
	"""
	TEMPLATE = u"""
	<xml>
	<ToUserName><![CDATA[{target}]]></ToUserName>
	<FromUserName><![CDATA[{source}]]></FromUserName>
	<CreateTime>{time}</CreateTime>
	<MsgType><![CDATA[text]]></MsgType>
	<Content><![CDATA[{content}]]></Content>
	</xml>
	"""

	def __init__(self, message, content):
		"""
		:param message: WechatMessage 对象
		:param content: 文字回复内容
		"""
		super(TextReply, self).__init__(message=message, content=content)

	def render(self):
		return TextReply.TEMPLATE.format(**self._args)


class ImageReply(WechatReply):
	"""
	回复图片消息
	"""
	TEMPLATE = u"""
	<xml>
	<ToUserName><![CDATA[{target}]]></ToUserName>
	<FromUserName><![CDATA[{source}]]></FromUserName>
	<CreateTime>{time}</CreateTime>
	<MsgType><![CDATA[image]]></MsgType>
	<Image>
	<MediaId><![CDATA[{media_id}]]></MediaId>
	</Image>
	</xml>
	"""

	def __init__(self, message, media_id):
		"""
		:param message: WechatMessage 对象
		:param media_id: 图片的 MediaID
		"""
		super(ImageReply, self).__init__(message=message, media_id=media_id)

	def render(self):
		return ImageReply.TEMPLATE.format(**self._args)


class VoiceReply(WechatReply):
	"""
	回复语音消息
	"""
	TEMPLATE = u"""
	<xml>
	<ToUserName><![CDATA[{target}]]></ToUserName>
	<FromUserName><![CDATA[{source}]]></FromUserName>
	<CreateTime>{time}</CreateTime>
	<MsgType><![CDATA[voice]]></MsgType>
	<Voice>
	<MediaId><![CDATA[{media_id}]]></MediaId>
	</Voice>
	</xml>
	"""

	def __init__(self, message, media_id):
		"""
		:param message: WechatMessage 对象
		:param media_id: 语音的 MediaID
		"""
		super(VoiceReply, self).__init__(message=message, media_id=media_id)

	def render(self):
		return VoiceReply.TEMPLATE.format(**self._args)


class VideoReply(WechatReply):
	"""
	回复视频消息
	"""
	TEMPLATE = u"""
	<xml>
	<ToUserName><![CDATA[{target}]]></ToUserName>
	<FromUserName><![CDATA[{source}]]></FromUserName>
	<CreateTime>{time}</CreateTime>
	<MsgType><![CDATA[video]]></MsgType>
	<Video>
	<MediaId><![CDATA[{media_id}]]></MediaId>
	<Title><![CDATA[{title}]]></Title>
	<Description><![CDATA[{description}]]></Description>
	</Video>
	</xml>
	"""

	def __init__(self, message, media_id, title=None, description=None):
		"""
		:param message: WechatMessage对象
		:param media_id: 视频的 MediaID
		:param title: 视频消息的标题
		:param description: 视频消息的描述
		"""
		title = title or ''
		description = description or ''
		super(VideoReply, self).__init__(message=message, media_id=media_id, title=title, description=description)

	def render(self):
		return VideoReply.TEMPLATE.format(**self._args)


class MusicReply(WechatReply):
	"""
	回复音乐消息
	"""
	TEMPLATE_THUMB = u"""
	<xml>
	<ToUserName><![CDATA[{target}]]></ToUserName>
	<FromUserName><![CDATA[{source}]]></FromUserName>
	<CreateTime>{time}</CreateTime>
	<MsgType><![CDATA[music]]></MsgType>
	<Music>
	<Title><![CDATA[{title}]]></Title>
	<Description><![CDATA[{description}]]></Description>
	<MusicUrl><![CDATA[{music_url}]]></MusicUrl>
	<HQMusicUrl><![CDATA[{hq_music_url}]]></HQMusicUrl>
	<ThumbMediaId><![CDATA[{thumb_media_id}]]></ThumbMediaId>
	</Music>
	</xml>
	"""

	TEMPLATE_NOTHUMB = u"""
	<xml>
	<ToUserName><![CDATA[{target}]]></ToUserName>
	<FromUserName><![CDATA[{source}]]></FromUserName>
	<CreateTime>{time}</CreateTime>
	<MsgType><![CDATA[music]]></MsgType>
	<Music>
	<Title><![CDATA[{title}]]></Title>
	<Description><![CDATA[{description}]]></Description>
	<MusicUrl><![CDATA[{music_url}]]></MusicUrl>
	<HQMusicUrl><![CDATA[{hq_music_url}]]></HQMusicUrl>
	</Music>
	</xml>
	"""

	def __init__(self, message, title='', description='', music_url='', hq_music_url='', thumb_media_id=None):
		title = title or ''
		description = description or ''
		music_url = music_url or ''
		hq_music_url = hq_music_url or music_url
		super(MusicReply, self).__init__(message=message, title=title, description=description,
										 music_url=music_url, hq_music_url=hq_music_url, thumb_media_id=thumb_media_id)

	def render(self):
		if self._args['thumb_media_id']:
			return MusicReply.TEMPLATE_THUMB.format(**self._args)
		else:
			return MusicReply.TEMPLATE_NOTHUMB.format(**self._args)


class Article(object):
	def __init__(self, title=None, description=None, picurl=None, url=None):
		self.title = title or ''
		self.description = description or ''
		self.picurl = picurl or ''
		self.url = url or ''


class ArticleReply(WechatReply):
	TEMPLATE = u"""
	<xml>
	<ToUserName><![CDATA[{target}]]></ToUserName>
	<FromUserName><![CDATA[{source}]]></FromUserName>
	<CreateTime>{time}</CreateTime>
	<MsgType><![CDATA[news]]></MsgType>
	<ArticleCount>{count}</ArticleCount>
	<Articles>{items}</Articles>
	</xml>
	"""

	ITEM_TEMPLATE = u"""
	<item>
	<Title><![CDATA[{title}]]></Title>
	<Description><![CDATA[{description}]]></Description>
	<PicUrl><![CDATA[{picurl}]]></PicUrl>
	<Url><![CDATA[{url}]]></Url>
	</item>
	"""

	def __init__(self, message, **kwargs):
		super(ArticleReply, self).__init__(message, **kwargs)
		self._articles = []

	def add_article(self, article):
		if len(self._articles) >= 10:
			raise AttributeError("Can't add more than 10 articles in an ArticleReply")
		else:
			self._articles.append(article)

	def render(self):
		items = []
		for article in self._articles:
			items.append(ArticleReply.ITEM_TEMPLATE.format(
				title=article.title,
				description=article.description,
				picurl=article.picurl,
				url=article.url,
			))
		self._args["items"] = ''.join(items)
		self._args["count"] = len(items)
		return ArticleReply.TEMPLATE.format(**self._args)

def disable_urllib3_warning():
	"""
	https://urllib3.readthedocs.org/en/latest/security.html#insecurerequestwarning
	InsecurePlatformWarning 警告的临时解决方案
	"""
	try:
		import requests.packages.urllib3
		requests.packages.urllib3.disable_warnings()
	except Exception:
		pass


class XMLStore(object):
	"""
	XML 存储类，可方便转换为 Dict
	"""
	def __init__(self, xmlstring):
		self._raw = xmlstring
		self._doc = minidom.parseString(xmlstring)

	@property
	def xml2dict(self):
		"""
		将 XML 转换为 dict
		"""
		self._remove_whitespace_nodes(self._doc.childNodes[0])
		return self._element2dict(self._doc.childNodes[0])

	def _element2dict(self, parent):
		"""
		将单个节点转换为 dict
		"""
		d = {}
		for node in parent.childNodes:
			if not isinstance(node, minidom.Element):
				continue
			if not node.hasChildNodes():
				continue

			if node.childNodes[0].nodeType == minidom.Node.ELEMENT_NODE:
				try:
					d[node.tagName]
				except KeyError:
					d[node.tagName] = []
				d[node.tagName].append(self._element2dict(node))
			elif len(node.childNodes) == 1 and node.childNodes[0].nodeType in [minidom.Node.CDATA_SECTION_NODE, minidom.Node.TEXT_NODE]:
				d[node.tagName] = node.childNodes[0].data
		return d

	def _remove_whitespace_nodes(self, node, unlink=True):
		"""
		删除空白无用节点
		"""
		remove_list = []
		for child in node.childNodes:
			if child.nodeType == Node.TEXT_NODE and not child.data.strip():
				remove_list.append(child)
			elif child.hasChildNodes():
				self._remove_whitespace_nodes(child, unlink)
		for node in remove_list:
			node.parentNode.removeChild(node)
			if unlink:
				node.unlink()

class WechatSimple(object):
	def __init__(self, checkssl=False):
		if not checkssl:
			disable_urllib3_warning()  # 可解决 InsecurePlatformWarning 警告
		self.__is_parse = False
		self.__message = None

	def check_signature(self, signature, timestamp, nonce):
		if not signature or not timestamp or not nonce:
			return False
		tmp_list = [weglobal.TOKEN, timestamp, nonce]
		tmp_list.sort()
		tmp_str = ''.join(tmp_list)
		if signature == hashlib.sha1(tmp_str.encode('utf-8')).hexdigest():
			return True
		else:
			return False
			
	def parse_data(self, data):
		result = {}
		if type(data) == unicode:
			data = data.encode('utf-8')
		elif type(data) == str:
			pass
		else:
			raise ParseError()

		try:
			xml = XMLStore(xmlstring=data)
		except Exception:
			raise ParseError()

		result = xml.xml2dict
		result['raw'] = data
		result['type'] = result.pop('MsgType').lower()

		message_type = MESSAGE_TYPES.get(result['type'], UnknownMessage)
		self.__message = message_type(result)
		self.__is_parse = True
			
	def get_message(self):
		return self.__message

	def response_text(self, content, escape=False):
		if self.__is_parse:
			content = self._transcoding(content)
			if escape:
				content = cgi.escape(content)
			return TextReply(message=self.__message, content=content).render()
			
	def _transcoding(self, data):
		if not data:
			return data
		result = None
		if isinstance(data, str):
			result = data.decode('utf-8')
		else:
			result = data
		return result
		
	def _transcoding_list(self, data):
		if not isinstance(data, list):
			raise ValueError('Parameter data must be list object.')
		result = []
		for item in data:
			if isinstance(item, dict):
				result.append(self._transcoding_dict(item))
			elif isinstance(item, list):
				result.append(self._transcoding_list(item))
			else:
				result.append(item)
		return result
		
	def _transcoding_dict(self, data):
		if not isinstance(data, dict):
			raise ValueError('Parameter data must be dict object.')
		result = {}
		for k, v in data.items():
			k = self._transcoding(k)
			if isinstance(v, dict):
				v = self._transcoding_dict(v)
			elif isinstance(v, list):
				v = self._transcoding_list(v)
			else:
				v = self._transcoding(v)
			result.update({k: v})
		return result

	def _check_official_error(self, json_data):
		if "errcode" in json_data and json_data["errcode"] != 0:
			raise OfficialAPIError("{}: {}".format(json_data["errcode"], json_data["errmsg"]))

	def _request(self, method, url, **kwargs):
		if "params" not in kwargs:
			kwargs["params"] = {
				"access_token": self.get_accesstoken(),
			}
		if isinstance(kwargs.get("data", ""), dict):
			body = json.dumps(kwargs["data"], ensure_ascii=False)
			body = body.encode('utf8')
			kwargs["data"] = body

		r = requests.request(
			method=method,
			url=url,
			**kwargs
		)
		r.raise_for_status()
		response_json = r.json()
		self._check_official_error(response_json)
		return response_json
		
	def _get(self, url, **kwargs):
		return self._request(
			method="get",
			url=url,
			**kwargs
		)

	def _post(self, url, **kwargs):
		return self._request(
			method="post",
			url=url,
			**kwargs
		)
		
	def get_accesstoken(self):
		if not weglobal.ACCESS_TOKEN or int(time.time()) >=  weglobal.ACCESS_TOKEN_EXPIRES_AT:
			response_json = self._get(
				url="https://api.weixin.qq.com/cgi-bin/token",
				params={
					"grant_type": "client_credential",
					"appid": weglobal.APP_ID,
					"secret": weglobal.APP_SECRET,
				}
			)
			weglobal.ACCESS_TOKEN = response_json['access_token']
			weglobal.ACCESS_TOKEN_EXPIRES_AT = int(time.time()) + response_json['expires_in']
		return weglobal.ACCESS_TOKEN
		
	def create_menu(self, menu_data):
		menu_data = self._transcoding_dict(menu_data)
		return self._post(
			url='https://api.weixin.qq.com/cgi-bin/menu/create',
			data=menu_data
		)
		
	def get_menu(self):
		return self._get('https://api.weixin.qq.com/cgi-bin/menu/get')
		
	def oauth(self, code):
		#换取网页授权access_token页面的构造方式：
		#https://api.weixin.qq.com/sns/oauth2/access_token?appid=APPID&secret=SECRET&code=CODE&grant_type=authorization_code
		response_json = self._get(
			url="https://api.weixin.qq.com/sns/oauth2/access_token",
			params={
				"grant_type": "authorization_code",
				"appid": weglobal.APP_ID,
				"secret": weglobal.APP_SECRET,
				"code": code,
			}
		)
		return response_json
		
	def getUserInfo(self, openid):
		#获取用户基本信息(UnionID机制)：
		#https://api.weixin.qq.com/cgi-bin/user/info?access_token=ACCESS_TOKEN&openid=OPENID&lang=zh_CN
		response_json = self._get(
			url="https://api.weixin.qq.com/cgi-bin/user/info",
			params={
				"access_token": self.get_accesstoken(),
				"openid": openid,
				"lang": "zh_CN",
			}
		)
		return response_json
		