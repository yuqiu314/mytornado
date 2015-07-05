#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os
import sys
import datetime
import json
import re
from tornado import ioloop,web,websocket
from pymongo import MongoClient
from bson import json_util
from bson.objectid import ObjectId
#from wechat_sdk import WechatSimple
from wesimp import WechatSimple

client = MongoClient("mongodb://localhost:27017/")
db = client["huhushuidb"]

GLOBALS={
    "sockets": []
}

class GetMenuHandler(web.RequestHandler):
	def get(self):
		return self.write(json.dumps(WechatSimple().get_menu(),ensure_ascii=False))
		
class SetMenuHandler(web.RequestHandler):
	def get(self):
		retval = WechatSimple().create_menu({
			'button':[
			{
				'type': 'view',
				'name': u'今晚速订',
				'url': 'https://open.weixin.qq.com/connect/oauth2/authorize?appid=wx57a085415d1caaed&redirect_uri=http://huhushui.club/tor/user/login?response_type=code&scope=snsapi_base&state=1#wechat_redirect'
			},
		]})
		return self.write(json.dumps(retval,ensure_ascii=False))
		
class WechatHandler(web.RequestHandler):
	def get(self):
		if WechatSimple().check_signature(
				signature=self.get_argument('signature'), 
				timestamp=self.get_argument('timestamp'), 
				nonce=self.get_argument('nonce')):
			return self.write(self.get_argument('echostr'))
	
	def post(self):
		wechat = WechatSimple()
		if wechat.check_signature(
				signature=self.get_argument('signature'), 
				timestamp=self.get_argument('timestamp'), 
				nonce=self.get_argument('nonce')):
			wechat.parse_data(self.request.body)
			message = wechat.get_message()
			response = None
			if message.type == 'subscribe':
				jsoninfo = wechat.getUserInfo(message.source)
				self._update_user(jsoninfo)
				response = wechat.response_text(jsoninfo['nickname']+u'您好，欢迎关注呼呼睡微信服务号。您可以点击按钮订房，也可以下载呼呼睡App进行订房。')
				return self.write(response)
			elif message.type == 'location':
				jsoninfo = {'openid':message.source, 'latitude':message.latitude, 'longitude':message.longitude}
				self._update_user_location(jsoninfo)
			elif message.type == 'text':
				jsoninfo = wechat.getUserInfo(message.source)
				self._update_user(jsoninfo)
				response = wechat.response_text(jsoninfo['nickname']+u'您好，请点击按钮订房，或者下载呼呼睡App。')
				return self.write(response)
			else:
				pass
	
	def _insert_default_user(self, jsoninfo):
		if db.WechatUser.find({'openid':jsoninfo['openid']}).count()==0:
			db.WechatUser.insert({'openid':jsoninfo['openid'],'phone':'phone','subscribe':0,'nickname':'nickname',
		'sex':0,'language':'zh_CN','city':'city','province':'province','country':'China',
		'headimgurl':'http://wx.qlogo.cn/mmopen/g3MonUZtNHkdmzicIlibx6iaFqAc56vxLSUfpb6n5WKSYVY0ChQKkiaJSgQ1dZuTOgvLLrhJbERQQ4eMsv84eavHiaiceqxibJxCfHe/0',
		'subscribe_time':0,'unionid':'unionid','remark':'remark','groupid':0,
		'latitude':0.0,'longitude':0.0,})
	
	def _update_user(self, jsoninfo):
		self._insert_default_user(jsoninfo)
		db.WechatUser.update({'openid':jsoninfo['openid']},{'$set':{'subscribe':jsoninfo['subscribe'],'nickname':jsoninfo['nickname'],
		'sex':jsoninfo['sex'],'language':jsoninfo['language'],'city':jsoninfo['city'],'province':jsoninfo['province'],'country':jsoninfo['country'],
		'headimgurl':jsoninfo['headimgurl'],'subscribe_time':jsoninfo['subscribe_time'],'remark':jsoninfo['remark'],'groupid':jsoninfo['groupid'],}})
	
	def _update_user_location(self, jsoninfo):
		self._insert_default_user(jsoninfo)
		db.WechatUser.update({'openid':jsoninfo['openid']},{'$set':{'latitude':jsoninfo['latitude'],'longitude':jsoninfo['longitude'],}})
		
class TestHandler(web.RequestHandler):
    def get(self):
		#打印所有bid的状态
		contents = db.Bid.find()
		output = []
		for content in contents:
			output.append(content['bidstatus'])
		outputstr = u'<br>'.join(output)
		return self.write(outputstr)

    def post(self):
        story_data = json.loads(self.request.body)
        story_id = db.stories.insert(story_data)
        print('story created with id ' + str(story_id))
        self.set_header("Content-Type", "application/json")
        self.set_status(201)

class HotelLoginHandler(web.RequestHandler):
	def get(self):
		return self.render('hotellogin.html')
	
	def post(self):
		loginame = self.get_argument('loginame')
		password = self.get_argument('password')
		if db.Hotel.find({'password':password,'loginame':loginame,}).count()==1:
			self.set_secure_cookie('hotellogin',loginame)
			self.finish('1')
		else:
			self.finish('-1')

class HotelRegHandler(web.RequestHandler):
	def get(self):
		return self.render('hotelreg.html')
	
	def post(self):
		name = self.get_argument('name')
		loginame = self.get_argument('loginame')
		password = self.get_argument('password')
		phone = self.get_argument('phone')
		if db.Hotel.find({'loginame':loginame}).count()==1:
			self.finish('-1')
		else:
			db.Hotel.insert({'name':name,'password':password,'loginame':loginame,'phone':phone,})
			self.set_secure_cookie('hotellogin',loginame)
			self.finish('1')

class HotelWaitOrderHandler(web.RequestHandler):
	def get(self):
		hotellogin = self.get_secure_cookie('hotellogin', None)
		if hotellogin is not None:
			hotel = db.Hotel.find_one({'loginame':hotellogin})
			showorders = []
			bids = db.Bid.find({'hotel_id':hotel['_id'],'bidstatus':'INIT'})
			for bid in bids:
				order = db.Order.find_one({'_id':bid['order_id']})
				showorders.append({'nickname':order['weuser_nickname'],'price':order['price'],'roomtype':order['roomtype'],
					'bidprice':order['price'],'orderid':bid['order_id'],'bidid':bid['_id'],'btnname':'首次出价',})
			initBidCnt = db.Bid.find({'hotel_id':hotel['_id'],'bidstatus':'INIT'}).count()
			updateBidCnt = db.Bid.find({'hotel_id':hotel['_id'],'bidstatus':'NEW'}).count()
			acceptedBidCnt = db.Bid.find({'hotel_id':hotel['_id'],'bidstatus':'ACCEPTED'}).count()
			abandonedBidCnt = db.Bid.find({'hotel_id':hotel['_id'],'bidstatus':'ABANDONED'}).count()
			return self.render('hotelwaitorder.html',hotel=hotel,showorders=showorders, 
				initBidCnt=initBidCnt,updateBidCnt=updateBidCnt,acceptedBidCnt=acceptedBidCnt,abandonedBidCnt=abandonedBidCnt)
		else:
			return self.redirect('/tor/hotel/login')
	
	def post(self):
		hotellogin = self.get_secure_cookie('hotellogin', None)
		if hotellogin is not None:
			hotel = db.Hotel.find_one({'loginame':hotellogin})
			orderidstr = self.get_argument('orderid')
			bidid = self.get_argument('bidid')
			bidprice = self.get_argument('bidprice')
			db.Bid.update({'_id':ObjectId(bidid)}, {'$set':{'price':bidprice,'bidstatus':'NEW'}})
			data = 'userreload'
			for socket in GLOBALS['sockets']:
				socket.write_message(data)
			self.finish('0')
		else:
			self.finish('1')

class HotelUpdateBidHandler(web.RequestHandler):
	def get(self):
		hotellogin = self.get_secure_cookie('hotellogin', None)
		if hotellogin is not None:
			hotel = db.Hotel.find_one({'loginame':hotellogin})
			showorders = []
			bids = db.Bid.find({'hotel_id':hotel['_id'],'bidstatus':'NEW'})
			for bid in bids:
				order = db.Order.find_one({'_id':bid['order_id']})
				showorders.append({'nickname':order['weuser_nickname'],'price':order['price'],'roomtype':order['roomtype'],
					'bidprice':bid['price'],'orderid':bid['order_id'],'bidid':bid['_id'],})
			initBidCnt = db.Bid.find({'hotel_id':hotel['_id'],'bidstatus':'INIT'}).count()
			updateBidCnt = db.Bid.find({'hotel_id':hotel['_id'],'bidstatus':'NEW'}).count()
			acceptedBidCnt = db.Bid.find({'hotel_id':hotel['_id'],'bidstatus':'ACCEPTED'}).count()
			abandonedBidCnt = db.Bid.find({'hotel_id':hotel['_id'],'bidstatus':'ABANDONED'}).count()
			return self.render('hotelupdatebid.html',hotel=hotel,showorders=showorders, 
				initBidCnt=initBidCnt,updateBidCnt=updateBidCnt,acceptedBidCnt=acceptedBidCnt,abandonedBidCnt=abandonedBidCnt)
		else:
			return self.redirect('/tor/hotel/login')
	
	def post(self):
		hotellogin = self.get_secure_cookie('hotellogin', None)
		if hotellogin is not None:
			hotel = db.Hotel.find_one({'loginame':hotellogin})
			orderidstr = self.get_argument('orderid')
			bidid = self.get_argument('bidid')
			bidprice = self.get_argument('bidprice')
			db.Bid.update({'_id':ObjectId(bidid)}, {'$set':{'price':bidprice}})
			data = 'userreload'
			for socket in GLOBALS['sockets']:
				socket.write_message(data)
			self.finish('0')
		else:
			self.finish('1')

class HotelAcceptedBidHandler(web.RequestHandler):
	def get(self):
		hotellogin = self.get_secure_cookie('hotellogin', None)
		if hotellogin is not None:
			hotel = db.Hotel.find_one({'loginame':hotellogin})
			showorders = []
			bids = db.Bid.find({'hotel_id':hotel['_id'],'bidstatus':'ACCEPTED'})
			for bid in bids:
				order = db.Order.find_one({'_id':bid['order_id']})
				showorders.append({'nickname':order['weuser_nickname'],'price':order['price'],'roomtype':order['roomtype'],
					'bidprice':bid['price'],'orderid':bid['order_id'],'bidid':bid['_id'],})
			initBidCnt = db.Bid.find({'hotel_id':hotel['_id'],'bidstatus':'INIT'}).count()
			updateBidCnt = db.Bid.find({'hotel_id':hotel['_id'],'bidstatus':'NEW'}).count()
			acceptedBidCnt = db.Bid.find({'hotel_id':hotel['_id'],'bidstatus':'ACCEPTED'}).count()
			abandonedBidCnt = db.Bid.find({'hotel_id':hotel['_id'],'bidstatus':'ABANDONED'}).count()
			return self.render('hotelacceptedbid.html',hotel=hotel,showorders=showorders, 
				initBidCnt=initBidCnt,updateBidCnt=updateBidCnt,acceptedBidCnt=acceptedBidCnt,abandonedBidCnt=abandonedBidCnt)
		else:
			return self.redirect('/tor/hotel/login')
			
class HotelAbandonedBidHandler(web.RequestHandler):
	def get(self):
		hotellogin = self.get_secure_cookie('hotellogin', None)
		if hotellogin is not None:
			hotel = db.Hotel.find_one({'loginame':hotellogin})
			showorders = []
			bids = db.Bid.find({'hotel_id':hotel['_id'],'bidstatus':'ABANDONED'})
			for bid in bids:
				order = db.Order.find_one({'_id':bid['order_id']})
				showorders.append({'nickname':order['weuser_nickname'],'price':order['price'],'roomtype':order['roomtype'],
					'bidprice':bid['price'],'orderid':bid['order_id'],'bidid':bid['_id'],})
			initBidCnt = db.Bid.find({'hotel_id':hotel['_id'],'bidstatus':'INIT'}).count()
			updateBidCnt = db.Bid.find({'hotel_id':hotel['_id'],'bidstatus':'NEW'}).count()
			acceptedBidCnt = db.Bid.find({'hotel_id':hotel['_id'],'bidstatus':'ACCEPTED'}).count()
			abandonedBidCnt = db.Bid.find({'hotel_id':hotel['_id'],'bidstatus':'ABANDONED'}).count()
			return self.render('hotelabandonedbid.html',hotel=hotel,showorders=showorders, 
				initBidCnt=initBidCnt,updateBidCnt=updateBidCnt,acceptedBidCnt=acceptedBidCnt,abandonedBidCnt=abandonedBidCnt)
		else:
			return self.redirect('/tor/hotel/login')
			
class HotelLogoutHandler(web.RequestHandler):
	def get(self):
		self.clear_cookie('hotellogin')
		return self.redirect('/tor/hotel/login')

class UserLoginHandler(web.RequestHandler):
	def get(self):
		wechat = WechatSimple()
		code = self.get_argument('code')
		snsret = wechat.oauth(code)
		#snsret = {'':''}
		#搞不明白为什么微信给的code为什么会失效，只看到企鹅给返回来两次code，然后尼玛code就失效了
		#只好补丁一下，尝试重连
		if 'openid' not in snsret:
			reconnectqq = self.get_cookie('reconnectqq', None)
			if reconnectqq is None:
				self.set_cookie('reconnectqq', '0', expires=datetime.datetime.utcnow() + datetime.timedelta(minutes=1))
				#print 'create cookie'
				return self.redirect('https://open.weixin.qq.com/connect/oauth2/authorize?appid=wx57a085415d1caaed&redirect_uri=http://huhushui.club/tor/user/login?response_type=code&scope=snsapi_base&state=1#wechat_redirect')
			elif reconnectqq == '0':
				self.set_cookie('reconnectqq', '1', expires=datetime.datetime.utcnow() + datetime.timedelta(minutes=1))
				#print 'reconnectqq'
				return self.redirect('https://open.weixin.qq.com/connect/oauth2/authorize?appid=wx57a085415d1caaed&redirect_uri=http://huhushui.club/tor/user/login?response_type=code&scope=snsapi_base&state=1#wechat_redirect')
			else:
				return self.write(u'对不起，我们和微信的服务器的沟通出现了一些问题。请尝试点击左上角的返回，然后再次点击按钮。')
		else:
			openid = snsret["openid"];
			weuser = db.WechatUser.find_one({'openid':openid})
			self.set_secure_cookie('openid',openid)
			self.set_cookie('nickname',weuser['nickname'])
			self.set_cookie('longitude',str(weuser['longitude']))
			self.set_cookie('latitude',str(weuser['latitude']))
			return self.redirect('/tor/user/redir')

class UserWebLoginHandler(web.RequestHandler):
	def get(self):
		#openid = 'oFlDUs4VBB_ZXGqnYOhwRkTu2clc' #qiuyu
		#openid = 'oFlDUs6-KgqgawHK2R2INF2BhI-M' #jojo
		openid = self.get_argument('u')
		weuser = db.WechatUser.find_one({'openid':openid})
		self.set_secure_cookie('openid',openid)
		self.set_cookie('nickname',weuser['nickname'])
		self.set_cookie('longitude',str(weuser['longitude']))
		self.set_cookie('latitude',str(weuser['latitude']))
		return self.redirect('/tor/user/redir')
		
class UserRedirHandler(web.RequestHandler):
	def get(self):
		openid = self.get_secure_cookie('openid', None)
		if openid is not None:
			weuser = db.WechatUser.find_one({'openid':openid})
			weuserid = weuser['_id']
			if db.Order.find({'weuser_id':weuserid,'orderstatus':'NEW'}).count() > 0:
				return self.redirect('/tor/user/wait')
			else:
				#return self.redirect('/tor/user/booking')
				return self.redirect('/getpos.php')
		else:
			return self.write(u'cookie异常，请检查设置或者尝试刷新')

class UserBookingHandler(web.RequestHandler):
	def get(self):
		openid = self.get_secure_cookie('openid', None)
		return self.render('userbooking.html')

	def post(self):
		openid = self.get_secure_cookie('openid', None)
		weuser = db.WechatUser.find_one({'openid':openid})
		#这里获取坐标其实是不对的，需要从表单里面获取，因为用户会改
		latitude = self.get_argument('latitude')
		longitude = self.get_argument('longitude')
		price = self.get_argument('price')
		roomtype = self.get_argument('roomtype')
		#创建order
		order = db.Order.insert_one({'weuser_id':weuser['_id'],'weuser_nickname':weuser['nickname'],
		'weuser_phone':weuser['phone'],'orderstatus':'NEW','price':price,
		'roomtype':roomtype,'latitude':latitude,'longitude':longitude})
		#搜索出前10家最近的酒店，然后创建bids
		for result in db.command(
			'geoNear', 'Hotel',
			near={'type': 'Point','coordinates': [float(longitude),float(latitude)]},
			spherical=True,num=10)["results"]:
			db.Bid.insert({'order_id':order.inserted_id,'hotel_id':result['obj']['_id'],
				'hotel_name':result['obj']['name'],'hotel_phone':result['obj']['phone'],
				'bidstatus':'INIT','price':0.0})
		#发通知进行更新
		data = 'hotelreload'
		for socket in GLOBALS['sockets']:
			socket.write_message(data)
		self.finish('1')

class UserWaitBidsHandler(web.RequestHandler):
	def get(self):
		openid = self.get_secure_cookie('openid', None)
		weuser = db.WechatUser.find_one({'openid':openid})
		weuserid = weuser['_id']
		orders = db.Order.find({'weuser_id':weuserid,'orderstatus':'NEW'})
		if orders.count()>0:
			order = orders[0]
			price = order['price']
			roomtype = order['roomtype']
			orderid = order['_id']
			bids = db.Bid.find({'order_id':orderid,'bidstatus':'NEW'})
			return self.render('userwaitbids.html',price=price,roomtype=roomtype,orderid=orderid,bids=bids)
		else:
			#return self.redirect('/tor/user/booking')
			return self.redirect('/getpos.php')
	
	def post(self):
		openid = self.get_secure_cookie('openid', None)
		orderid = self.get_argument('orderid')
		db.Order.update({'_id':ObjectId(orderid)},{'$set':{'orderstatus':'ABANDONED'}})
		db.Bid.update({'order_id':ObjectId(orderid)},{'$set':{'bidstatus':'ABANDONED'}},multi=True)
		data = 'hotelreload'
		for socket in GLOBALS['sockets']:
			socket.write_message(data)
		self.finish('1')

class UserDealHandler(web.RequestHandler):
	def get(self):
		openid = self.get_secure_cookie('openid', None)
		return self.render('userdeal.html')
	
	def post(self):
		openid = self.get_secure_cookie('openid', None)
		bidid = self.get_argument('bidid')
		bid = db.Bid.find_one({'_id':ObjectId(bidid)})
		orderid = bid['order_id']
		db.Order.update({'_id':orderid},{'$set':{'orderstatus':'ACCEPTED'}})
		db.Bid.update({'order_id':orderid},{'$set':{'bidstatus':'ABANDONED'}},multi=True)
		db.Bid.update({'_id':ObjectId(bidid)},{'$set':{'bidstatus':'ACCEPTED'}})
		data = 'hotelreload'
		for socket in GLOBALS['sockets']:
			socket.write_message(data)
		self.finish('0')

class HotelInfoHandler(web.RequestHandler):
	def get(self):
		hotel_id = self.get_argument('hotel_id')
		hotel = db.Hotel.find_one({'_id':ObjectId(hotel_id)})
		return self.render('hotelinfo.html',hotel=hotel)
		
class ClientSocket(websocket.WebSocketHandler):
    def open(self):
        GLOBALS['sockets'].append(self)
        #print "WebSocket opened"

    def on_close(self):
        #print "WebSocket closed"
        GLOBALS['sockets'].remove(self)
		
    def check_origin(self, origin):
       # return bool(re.match(r'^.*?\.huhuschui\.club', origin))
       return True

class Announcer(web.RequestHandler):
    def get(self, *args, **kwargs):
        data = self.get_argument('data')
        for socket in GLOBALS['sockets']:
            socket.write_message(data)
        return self.write('Posted')

class ClientHandler(web.RequestHandler):
    def get(self):
        return self.render('tclient.html')
		
settings = {
	"cookie_secret" : "6IoETzKXQaGaYdkL59EmGeJJFuYh7EQnP2XdTP1o/Vo=",
    "template_path": os.path.join(os.path.dirname(__file__), "templates"),
    
	"debug" : True,
	#"static_path": "static",
}

application = web.Application([
	(r"/tor/wechat", WechatHandler),
	(r"/tor/wechat/getmenu", GetMenuHandler),
	(r"/tor/wechat/setmenu", SetMenuHandler),
	(r"/tor/test", TestHandler),
	
	(r"/tor/hotel/login", HotelLoginHandler),
	(r"/tor/hotel/reg", HotelRegHandler),
	(r"/tor/hotel/wait", HotelWaitOrderHandler),
	(r"/tor/hotel/bid/update", HotelUpdateBidHandler),
	(r"/tor/hotel/bid/accepted", HotelAcceptedBidHandler),
	(r"/tor/hotel/bid/abandoned", HotelAbandonedBidHandler),
	(r"/tor/hotel/logout", HotelLogoutHandler),
	(r"/tor/hotel/info", HotelInfoHandler),
		
	(r"/tor/user/login", UserLoginHandler),
	(r"/tor/user/weblogin", UserWebLoginHandler),
	(r"/tor/user/redir", UserRedirHandler),
	(r"/tor/user/booking", UserBookingHandler),
	(r"/tor/user/wait", UserWaitBidsHandler),
	(r"/tor/user/deal", UserDealHandler),
	
	(r"/tor/socket", ClientSocket),
	(r"/tor/push", Announcer),
	(r"/tor/client", ClientHandler),
],**settings)

if __name__ == "__main__":
    application.listen(int(sys.argv[1]))
    ioloop.IOLoop.instance().start()
