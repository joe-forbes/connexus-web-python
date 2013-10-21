import cgi
import datetime
import json
import urllib

from google.appengine.api import users
from google.appengine.api import search 
from google.appengine.api.images import get_serving_url
from google.appengine.ext import ndb
from google.appengine.ext import blobstore
from google.appengine.ext.webapp import blobstore_handlers

import webapp2

class Stream(ndb.Expando):
    name = ndb.StringProperty()
    tags = ndb.StringProperty()
    cover_url = ndb.StringProperty()
    followers = ndb.StringProperty(repeated=True)
    date = ndb.DateTimeProperty(auto_now_add=True)
    def to_dict(self):
        d = super(Stream, self).to_dict()
        d['id'] = self.key.id()
        return d

class Image(ndb.Model):
    image_url = ndb.StringProperty()
    latitude = ndb.FloatProperty()
    longitude = ndb.FloatProperty()
    date = ndb.DateTimeProperty(auto_now_add=True)
    stream_id = ndb.StringProperty()
    tags = ndb.StringProperty()
    def to_dict(self):
        d = super(Image, self).to_dict()
        d['id'] = self.key.id()
        return d
    
class ManPage(webapp2.RequestHandler):
    def get(self):
        self.response.headers['Content-Type'] = 'text/html'
        self.response.write('Hello, class!')
        self.response.write("""
<p>
Based on the Zach Whaley's excellent <a href="http://connexus-api.appspot.com">connexus-api.appspot.com</a> project. Forked from there to allow Zach and his partner to move forward on the next phase of development while my partner and I finish up work on the current phase.
</p>
<p><a href="https://github.com/joe-forbes/connexus-web-python" >Git repo</a></p>
<p><a href="/allstreams">Get all streams</a></p>
<p><a href="/mystreams?email=joe.forbes@gmail.com">Get subscribed streams</a></p>
<p>Add stream:<br>
<code>curl --data "name=greyhounds&tags=greyhound&cover_url=http://imgur.com/IcCcXYg"
connexus-jsf.appspot.com/addstream</code>
</p>
<p><a href="http://connexus-jsf.appspot.com/images?stream=5629499534213120" >Get Stream Images</a></p>
<p>
Subscribe to a stream:<br>
<code>curl --data "email=zachbwhaley@gmail.com&stream=5629499534213120" connexus-jsf.appspot.com/subscribe</code><br>
</p>
<p>
Image uploading<br>
This is a two part call<br>
<a href="/upload/geturl" >1st: get the upload URL</a><br>
2nd: Send the URL with Latitude Longitude, a Stream id, and the location of your image as multipart data<br>
<code>curl -F "latitude=30.267549" -F "longitude=-97.743645" -F "stream=5629499534213120" -F "image=@/path/to/image.jpg"
<url-given-from-above></code><br>
</p>
<p>
<a href="/nearbystreams?latitude=30.267549&longitude=-97.743645" >Nearby streams</a><br>
</p>
""")

class AddStream(webapp2.RequestHandler):
    def post(self):
        stream = Stream()
        stream.name = self.request.get('name')
        stream.tags = self.request.get('tags')
        stream.cover_url = self.request.get('cover_url')
        stream.put()

class GetUploadUrl(webapp2.RequestHandler):
    def get(self):
        upload_url = blobstore.create_upload_url('/upload/handler')
        self.response.headers['Content-Type'] = 'text/plain'
        self.response.out.write(upload_url)

class UploadImage(webapp2.RequestHandler):
    def post(self):
        upload_url = blobstore.create_upload_url('/upload/handler')
        self.response.headers['Content-Type'] = 'multipart/form-data'

class UploadHandler(blobstore_handlers.BlobstoreUploadHandler):
    def post(self):
        upload_files = self.get_uploads('image')
        blob_info = upload_files[0]
        key = blob_info.key()

        serving_url = get_serving_url(key)
        stream_id = self.request.get('stream')
        latitude = self.request.get('latitude')
        longitude = self.request.get('longitude')
        stream = Stream.get_by_id(long(stream_id))
        image = Image(parent=stream.key)
        image.image_url = serving_url
        tags = self.request.get('tags')
        if latitude != '':
            geopoint = search.GeoPoint(float(latitude), float(longitude))
            doc = search.Document(fields=[
                                          search.TextField(name='id', value=str(stream.key.id())),
                                          search.GeoField(name='loc', value=geopoint)])
            search.Index(name='geopoints').put(doc)
            image.latitude = float(latitude)
            image.longitude = float(longitude)

        image.stream_id = stream_id
        image.tags = tags
        if stream.cover_url == '':
            stream.cover_url = serving_url
            stream.put()
        image.put()
        stream.date = datetime.datetime.now()
        stream.put()
        self.response.headers['Content-Type'] = 'application/json'
        self.response.out.write(json.dumps(image.to_dict(), cls=DateSkipper))

class Subscribe(webapp2.RequestHandler):
    def post(self):
        stream_id = self.request.get('stream')
        email = self.request.get('email')
        stream = Stream.get_by_id(long(stream_id))
        stream.followers.append(email)
        stream.put()

class AllStreams(webapp2.RequestHandler):
    def get(self):
        query = Stream.query().order(-Stream.date)
        streams = [stream.to_dict() for stream in query.fetch()]
        self.response.headers['Content-Type'] = 'application/json'
        self.response.out.write(json.dumps(streams, cls=DateSkipper))

class MyStreams(webapp2.RequestHandler):
    def get(self):
        query = Stream.query().order(-Stream.date)
        email = self.request.get('email')
        streams = [stream.to_dict() for stream in query.fetch() if email in stream.followers]
        self.response.headers['Content-Type'] = 'application/json'
        self.response.out.write(json.dumps(streams, cls=DateSkipper))

class NearbyStreams(webapp2.RequestHandler):
    def get(self):
        latitude = self.request.get('latitude')
        longitude = self.request.get('longitude')
        index = search.Index('geopoints')
        query = 'distance(loc, geopoint(%s, %s)) < 1000' % (latitude, longitude)
        results = index.search(query)
        ids = [long(doc.field('id').value) for doc in results]
        streams = Stream.query().order(-Stream.date).fetch()
        streams = [s.to_dict() for s in streams if s.key.id() in ids]
        self.response.headers['Content-Type'] = 'application/json'
        self.response.out.write(json.dumps(streams, cls=DateSkipper))

class NearbyImages(webapp2.RequestHandler):
    def get(self):
        latitude = self.request.get('latitude')
        longitude = self.request.get('longitude')
        images = Image.query().order().fetch()
        images = [image.to_dict() for image in images if image.latitude is not None ]
        self.response.headers['Content-Type'] = 'application/json'
        self.response.out.write(json.dumps(images, cls=DateSkipper))

class StreamImages(webapp2.RequestHandler):
    def get(self):
        stream_id = self.request.get('stream')
        stream = Stream.get_by_id(long(stream_id))
        query = Image.query(ancestor=stream.key).order(-Image.date)
        images = [image.to_dict() for image in query.fetch()]
        self.response.headers['Content-Type'] = 'application/json'
        self.response.out.write(json.dumps(images, cls=DateSkipper))

class DateSkipper(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime.datetime):
            return
        return json.JSONEncoder.default(self, obj) 

class AddStreamIdsToImages(webapp2.RequestHandler):
    def get(self):
        stream_query = Stream.query()
        for stream in stream_query.fetch():
            image_query = Image.query(ancestor=stream.key)
            for image in image_query.fetch():
                image.stream_id = str(stream.key.id())
                image.put()

class GetStream(webapp2.RequestHandler):
    def get(self):
        stream_id = self.request.get('stream')
        stream = Stream.get_by_id(long(stream_id))
        self.response.headers['Content-Type'] = 'application/json'
        self.response.out.write(json.dumps(stream.to_dict(), cls=DateSkipper))
            
application = webapp2.WSGIApplication([
    ('/', ManPage),
    ('/addstream', AddStream),
    ('/allstreams', AllStreams),
    ('/mystreams', MyStreams),
    ('/nearbystreams', NearbyStreams),
    ('/images', StreamImages),
    ('/subscribe', Subscribe),
    ('/upload/geturl', GetUploadUrl),
    ('/upload', UploadImage),
    ('/upload/handler', UploadHandler),
    ('/addstreamidstoimages', AddStreamIdsToImages),
    ('/stream', GetStream),
    ('/nearbyimages', NearbyImages),
], debug=True)
